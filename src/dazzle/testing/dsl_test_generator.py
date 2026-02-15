"""
DAZZLE DSL-Driven Test Generator

Generates executable test designs directly from parsed DSL/AppSpec without
requiring a running server. Tests are derived from:

1. Entity definitions → CRUD tests, validation tests
2. State machines → Transition tests, invalid transition tests
3. Personas → Access control tests, goal verification tests
4. Workspaces → Navigation tests, component tests
5. Events → Event emission tests, handler tests
6. Processes → Workflow execution tests, compensation tests
7. Messages/Channels → Delivery tests, throttle tests

Tests are versioned based on DSL hash for change tracking.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from dazzle.core.ir import AppSpec
from dazzle.core.ir.domain import EntitySpec
from dazzle.core.ir.eventing import EventSpec
from dazzle.core.ir.fields import FieldSpec
from dazzle.core.ir.personas import PersonaSpec
from dazzle.core.ir.process import ProcessSpec
from dazzle.core.ir.workspaces import WorkspaceSpec
from dazzle.core.project import load_project


def _invariant_required_fields(entity: EntitySpec) -> list[str]:
    """Extract field names that must be populated to satisfy OR-clause invariants.

    For invariants like ``uprn != null or canonical_text != null``, returns
    the first field from each OR clause so that at least one is non-null.
    """
    from dazzle.core.ir.invariant import LogicalExpr

    fields: list[str] = []
    for inv in entity.invariants:
        expr = inv.expression
        # Match: field != null OR field != null
        if isinstance(expr, LogicalExpr) and expr.operator.value == "or":
            field_name = _extract_not_null_field(expr.left)
            if field_name:
                fields.append(field_name)
    return fields


def _extract_not_null_field(expr: Any) -> str | None:
    """Extract the field name from a ``field != null`` comparison."""
    from dazzle.core.ir.invariant import ComparisonExpr, InvariantFieldRef, InvariantLiteral

    if not isinstance(expr, ComparisonExpr):
        return None
    if expr.operator.value in ("!=", "is not"):
        left, right = expr.left, expr.right
        if (
            isinstance(left, InvariantFieldRef)
            and isinstance(right, InvariantLiteral)
            and right.value is None
        ):
            return left.path[0] if left.path else None
        if (
            isinstance(right, InvariantFieldRef)
            and isinstance(left, InvariantLiteral)
            and left.value is None
        ):
            return right.path[0] if right.path else None
    return None


def _entity_has_forbid_create(entity: EntitySpec) -> bool:
    """Check whether all create operations are forbidden for this entity."""
    if not entity.access or not entity.access.permissions:
        return False
    from dazzle.core.ir.domain import PolicyEffect

    for perm in entity.access.permissions:
        if perm.operation.value == "create" and perm.effect == PolicyEffect.FORBID:
            return True
    return False


@dataclass
class TestCoverage:
    """Tracks test coverage for the DSL."""

    # Covered items (sets)
    entities_covered: set[str] = field(default_factory=set)
    state_machines_covered: set[str] = field(default_factory=set)
    personas_covered: set[str] = field(default_factory=set)
    workspaces_covered: set[str] = field(default_factory=set)
    events_covered: set[str] = field(default_factory=set)
    processes_covered: set[str] = field(default_factory=set)
    auth_personas_covered: set[str] = field(default_factory=set)
    # Total counts
    entities_total: int = 0
    state_machines_total: int = 0
    personas_total: int = 0
    workspaces_total: int = 0
    events_total: int = 0
    processes_total: int = 0
    auth_personas_total: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "entities": sorted(self.entities_covered),
            "entities_total": self.entities_total,
            "state_machines": sorted(self.state_machines_covered),
            "state_machines_total": self.state_machines_total,
            "personas": sorted(self.personas_covered),
            "personas_total": self.personas_total,
            "workspaces": sorted(self.workspaces_covered),
            "workspaces_total": self.workspaces_total,
            "events": sorted(self.events_covered),
            "events_total": self.events_total,
            "processes": sorted(self.processes_covered),
            "processes_total": self.processes_total,
            "auth_personas": sorted(self.auth_personas_covered),
            "auth_personas_total": self.auth_personas_total,
        }


@dataclass
class GeneratedTestSuite:
    """Complete generated test suite with metadata."""

    version: str
    dsl_hash: str
    generated_at: str
    project_name: str
    designs: list[dict[str, Any]]
    coverage: TestCoverage

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "dsl_hash": self.dsl_hash,
            "generated_at": self.generated_at,
            "project_name": self.project_name,
            "coverage": self.coverage.to_dict(),
            "designs": self.designs,
        }


def compute_dsl_hash(appspec: AppSpec) -> str:
    """Compute a hash representing the DSL structure for change detection."""
    # Create a deterministic representation of the DSL structure
    structure = {
        "entities": sorted([e.name for e in appspec.domain.entities]),
        "personas": sorted([p.id for p in appspec.personas]) if appspec.personas else [],
        "workspaces": sorted([w.name for w in appspec.workspaces]) if appspec.workspaces else [],
        "events": sorted([e.name for e in appspec.event_model.events])
        if appspec.event_model
        else [],
        "processes": sorted([p.name for p in appspec.processes]) if appspec.processes else [],
    }
    content = json.dumps(structure, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


class DSLTestGenerator:
    """Generate tests directly from AppSpec."""

    def __init__(self, appspec: AppSpec):
        self.appspec = appspec
        self.coverage = TestCoverage()
        self._test_id_counter = 0
        # Build entity lookup and dependency graph
        self._entity_map: dict[str, EntitySpec] = {e.name: e for e in appspec.domain.entities}
        self._entity_deps = self._build_dependency_graph()

    def _next_id(self, prefix: str) -> str:
        """Generate next test ID with prefix."""
        self._test_id_counter += 1
        return f"{prefix}_{self._test_id_counter:03d}"

    def _build_dependency_graph(self) -> dict[str, list[str]]:
        """Build a graph of entity dependencies (which entities depend on which).

        Returns a dict mapping entity name -> list of entity names it depends on
        (i.e., entities it has required ref fields pointing to).
        """
        from dazzle.core.ir.fields import FieldTypeKind

        deps: dict[str, list[str]] = {}
        for entity in self.appspec.domain.entities:
            entity_deps: list[str] = []
            for fld in entity.fields:
                if fld.type.kind == FieldTypeKind.REF and fld.is_required:
                    # Extract target entity name from ref type
                    target = fld.type.ref_entity
                    if target and target in self._entity_map:
                        entity_deps.append(target)
            deps[entity.name] = entity_deps
        return deps

    def _get_required_refs(self, entity: EntitySpec) -> list[tuple[str, str, str]]:
        """Get required ref fields for an entity.

        Returns list of (field_name, target_entity, pk_field_name) tuples.
        """
        from dazzle.core.ir.fields import FieldTypeKind

        refs: list[tuple[str, str, str]] = []
        for fld in entity.fields:
            if fld.type.kind == FieldTypeKind.REF and fld.is_required:
                target = fld.type.ref_entity
                if target and target in self._entity_map:
                    # Find the PK field of the target entity
                    target_entity = self._entity_map[target]
                    pk_field = "id"  # Default
                    for tf in target_entity.fields:
                        if tf.is_primary_key:
                            pk_field = tf.name
                            break
                    refs.append((fld.name, target, pk_field))
        return refs

    def generate_all(self) -> GeneratedTestSuite:
        """Generate complete test suite from AppSpec."""
        designs = []

        # Set totals
        self.coverage.entities_total = len(self.appspec.domain.entities)
        self.coverage.state_machines_total = sum(
            1 for e in self.appspec.domain.entities if e.state_machine
        )
        self.coverage.personas_total = len(self.appspec.personas) if self.appspec.personas else 0
        self.coverage.workspaces_total = (
            len(self.appspec.workspaces) if self.appspec.workspaces else 0
        )
        self.coverage.events_total = (
            len(self.appspec.event_model.events) if self.appspec.event_model else 0
        )
        self.coverage.processes_total = len(self.appspec.processes) if self.appspec.processes else 0

        # Entity tests (CRUD + validation)
        for entity in self.appspec.domain.entities:
            if _entity_has_forbid_create(entity):
                continue  # Skip CRUD tests for entities where create is forbidden
            designs.extend(self._generate_entity_tests(entity))
            self.coverage.entities_covered.add(entity.name)

        # State machine tests
        for entity in self.appspec.domain.entities:
            if entity.state_machine:
                designs.extend(self._generate_state_machine_tests(entity))
                self.coverage.state_machines_covered.add(entity.name)

        # Persona tests
        if self.appspec.personas:
            for persona in self.appspec.personas:
                designs.extend(self._generate_persona_tests(persona))
                self.coverage.personas_covered.add(persona.id)

        # Auth lifecycle tests (login, session, logout per persona)
        if self.appspec.personas:
            self.coverage.auth_personas_total = len(self.appspec.personas)
            for persona in self.appspec.personas:
                designs.extend(self._generate_auth_lifecycle_tests(persona))
                self.coverage.auth_personas_covered.add(persona.id)

        # Workspace tests
        if self.appspec.workspaces:
            for workspace in self.appspec.workspaces:
                designs.extend(self._generate_workspace_tests(workspace))
                self.coverage.workspaces_covered.add(workspace.name)

        # Event tests
        if self.appspec.event_model:
            for event in self.appspec.event_model.events:
                designs.extend(self._generate_event_tests(event))
                self.coverage.events_covered.add(event.name)

        # Process/workflow tests
        if self.appspec.processes:
            for process in self.appspec.processes:
                designs.extend(self._generate_process_tests(process))
                self.coverage.processes_covered.add(process.name)

        return GeneratedTestSuite(
            version="2.0",
            dsl_hash=compute_dsl_hash(self.appspec),
            generated_at=datetime.now().isoformat(),
            project_name=self.appspec.name,
            designs=designs,
            coverage=self.coverage,
        )

    # =========================================================================
    # Entity Tests
    # =========================================================================

    def _generate_entity_tests(self, entity: EntitySpec) -> list[dict[str, Any]]:
        """Generate CRUD and validation tests for an entity."""
        tests = []

        # Get required references for this entity
        required_refs = self._get_required_refs(entity)

        # Build setup steps for parent entities (recursive — includes transitive deps)
        setup_steps = self._generate_parent_setup_steps(required_refs)
        related_entities = [entity.name] + [
            step["target"].removeprefix("entity:") for step in setup_steps
        ]

        # Generate entity data with ref placeholders
        entity_data = self._generate_entity_data_with_refs(entity, required_refs)

        # CRUD Create test
        create_steps = setup_steps + [
            {
                "action": "create",
                "target": f"entity:{entity.name}",
                "data": entity_data,
                "rationale": f"Create valid {entity.title or entity.name}",
            },
            {
                "action": "assert_count",
                "target": f"entity:{entity.name}",
                "data": {"min": 1},
                "rationale": "Verify entity was created",
            },
        ]
        tests.append(
            self._create_test(
                test_id=f"CRUD_{entity.name.upper()}_CREATE",
                title=f"Create {entity.title or entity.name}",
                description=f"Test creating a new {entity.title or entity.name}",
                trigger="api_call",
                steps=create_steps,
                entities=related_entities,
                tags=["crud", "create", "generated", "dsl-derived"],
            )
        )

        # CRUD Read test
        read_steps = setup_steps + [
            {
                "action": "create",
                "target": f"entity:{entity.name}",
                "data": entity_data,
                "rationale": "Seed test data",
            },
            {
                "action": "read_list",
                "target": f"entity:{entity.name}",
                "rationale": f"Fetch {entity.title or entity.name} list",
            },
            {
                "action": "assert_count",
                "target": f"entity:{entity.name}",
                "data": {"min": 1},
                "rationale": "Verify list has data",
            },
        ]
        tests.append(
            self._create_test(
                test_id=f"CRUD_{entity.name.upper()}_READ",
                title=f"Read {entity.title or entity.name} list",
                description=f"Test reading {entity.title or entity.name} list",
                trigger="api_call",
                steps=read_steps,
                entities=related_entities,
                tags=["crud", "read", "generated", "dsl-derived"],
            )
        )

        # Validation test for required fields
        required_fields = [
            f
            for f in entity.fields
            if f.is_required and f.name not in ("id", "created_at", "updated_at")
        ]
        if required_fields:
            tests.append(
                self._create_test(
                    test_id=f"VAL_{entity.name.upper()}_REQUIRED",
                    title=f"Validate required fields for {entity.title or entity.name}",
                    description="Test that missing required fields are rejected",
                    trigger="api_call",
                    steps=[
                        {
                            "action": "create_expect_error",
                            "target": f"entity:{entity.name}",
                            "data": {},  # Empty data
                            "rationale": "Attempt create without required fields",
                        },
                        {
                            "action": "assert_error",
                            "target": "last_response",
                            "data": {"type": "validation_error"},
                            "rationale": "Verify validation error returned",
                        },
                    ],
                    entities=[entity.name],
                    tags=["validation", "required", "generated", "dsl-derived"],
                )
            )

        # Unique constraint tests
        unique_fields = [f for f in entity.fields if f.is_unique and f.name != "id"]
        for uf in unique_fields:
            tests.append(
                self._create_test(
                    test_id=f"VAL_{entity.name.upper()}_{uf.name.upper()}_UNIQUE",
                    title=f"Validate {uf.name} uniqueness for {entity.title or entity.name}",
                    description=f"Test that duplicate {uf.name} values are rejected",
                    trigger="api_call",
                    steps=setup_steps
                    + [
                        {
                            "action": "create",
                            "target": f"entity:{entity.name}",
                            "data": entity_data,
                            "rationale": "Create first entity",
                        },
                        {
                            "action": "create_expect_error",
                            "target": f"entity:{entity.name}",
                            "data": entity_data,  # Same data — should trigger unique violation
                            "rationale": f"Attempt duplicate {uf.name}",
                        },
                        {
                            "action": "assert_error",
                            "target": "last_response",
                            "data": {"type": "unique_violation"},
                            "rationale": "Verify unique constraint enforced",
                        },
                    ],
                    entities=related_entities,
                    tags=["validation", "unique", "generated", "dsl-derived"],
                )
            )

        return tests

    # =========================================================================
    # State Machine Tests
    # =========================================================================

    def _generate_state_machine_tests(self, entity: EntitySpec) -> list[dict[str, Any]]:
        """Generate state machine transition tests."""
        tests: list[dict[str, Any]] = []
        sm = entity.state_machine
        if not sm:
            return tests

        state_field = sm.status_field or "status"

        # Build parent setup (recursive — handles transitive FK chains)
        required_refs = self._get_required_refs(entity)
        setup_steps = self._generate_parent_setup_steps(required_refs)
        entity_data = self._generate_entity_data_with_refs(entity, required_refs)
        related_entities = [entity.name] + [
            step["target"].removeprefix("entity:") for step in setup_steps
        ]

        # Valid transitions
        for trans in sm.transitions:
            tests.append(
                self._create_test(
                    test_id=f"SM_{entity.name.upper()}_{trans.from_state.upper()}_{trans.to_state.upper()}",
                    title=f"{entity.title or entity.name}: {trans.from_state} → {trans.to_state}",
                    description=f"Test valid transition from {trans.from_state} to {trans.to_state}",
                    trigger="state_change",
                    steps=setup_steps
                    + [
                        {
                            "action": "create",
                            "target": f"entity:{entity.name}",
                            "data": {
                                **entity_data,
                                state_field: trans.from_state,
                            },
                            "rationale": f"Create entity in {trans.from_state} state",
                        },
                        {
                            "action": "transition",
                            "target": f"entity:{entity.name}",
                            "data": {"to_state": trans.to_state},
                            "rationale": f"Transition to {trans.to_state}",
                        },
                        {
                            "action": "assert_state",
                            "target": f"entity:{entity.name}",
                            "data": {"field": state_field, "value": trans.to_state},
                            "rationale": "Verify new state",
                        },
                    ],
                    entities=related_entities,
                    tags=["state_machine", "transition", "generated", "dsl-derived"],
                )
            )

        # Invalid transitions (if we can detect them)
        all_states = set(sm.states)
        for state in sm.states:
            valid_next = {t.to_state for t in sm.transitions if t.from_state == state}
            invalid_next = all_states - valid_next - {state}
            for invalid_state in list(invalid_next)[:1]:  # Test one invalid per state
                tests.append(
                    self._create_test(
                        test_id=f"SM_{entity.name.upper()}_{state.upper()}_{invalid_state.upper()}_INVALID",
                        title=f"{entity.title or entity.name}: {state} → {invalid_state} (invalid)",
                        description=f"Test that invalid transition from {state} to {invalid_state} is rejected",
                        trigger="state_change",
                        steps=setup_steps
                        + [
                            {
                                "action": "create",
                                "target": f"entity:{entity.name}",
                                "data": {**entity_data, state_field: state},
                                "rationale": f"Create entity in {state} state",
                            },
                            {
                                "action": "transition_expect_error",
                                "target": f"entity:{entity.name}",
                                "data": {"to_state": invalid_state},
                                "rationale": f"Attempt invalid transition to {invalid_state}",
                            },
                            {
                                "action": "assert_state",
                                "target": f"entity:{entity.name}",
                                "data": {"field": state_field, "value": state},
                                "rationale": "Verify state unchanged",
                            },
                        ],
                        entities=related_entities,
                        tags=["state_machine", "invalid_transition", "generated", "dsl-derived"],
                    )
                )

        return tests

    # =========================================================================
    # Persona Tests
    # =========================================================================

    def _generate_persona_tests(self, persona: PersonaSpec) -> list[dict[str, Any]]:
        """Generate access control tests for a persona."""
        tests = []
        persona_id = persona.id  # PersonaSpec uses 'id' not 'name'
        persona_label = persona.label or persona_id

        # Basic access test
        tests.append(
            self._create_test(
                test_id=f"ACL_{persona_id.upper()}_ACCESS",
                title=f"{persona_label} can authenticate",
                description=f"Test that {persona_label} persona can authenticate",
                trigger="authentication",
                persona=persona_id,
                steps=[
                    {
                        "action": "login_as",
                        "target": persona_id,
                        "rationale": f"Authenticate as {persona_label}",
                    },
                    {
                        "action": "assert_authenticated",
                        "target": persona_id,
                        "rationale": "Verify authentication succeeded",
                    },
                ],
                tags=["persona", "authentication", "generated", "dsl-derived"],
            )
        )

        # Goal-based tests
        if persona.goals:
            for goal in persona.goals:
                tests.append(
                    self._create_test(
                        test_id=f"GOAL_{persona_id.upper()}_{self._slugify(goal)[:20].upper()}",
                        title=f"{persona_label}: {goal}",
                        description=f"Test that {persona_label} can achieve goal: {goal}",
                        trigger="user_action",
                        persona=persona_id,
                        steps=[
                            {
                                "action": "login_as",
                                "target": persona_id,
                                "rationale": f"Authenticate as {persona_label}",
                            },
                            {
                                "action": "achieve_goal",
                                "target": goal,
                                "rationale": f"Work towards goal: {goal}",
                            },
                        ],
                        tags=["persona", "goal", "generated", "dsl-derived"],
                    )
                )

        return tests

    # =========================================================================
    # Auth Lifecycle Tests
    # =========================================================================

    def _generate_auth_lifecycle_tests(self, persona: PersonaSpec) -> list[dict[str, Any]]:
        """Generate auth lifecycle tests (login, session, logout) for a persona."""
        tests = []
        persona_id = persona.id
        persona_label = persona.label or persona_id

        # AUTH_LOGIN_VALID — successful login
        tests.append(
            self._create_test(
                test_id=f"AUTH_LOGIN_VALID_{persona_id.upper()}",
                title=f"Login as {persona_label} with valid credentials",
                description=f"Test that {persona_label} can log in with correct credentials",
                trigger="api_call",
                persona=persona_id,
                steps=[
                    {
                        "action": "post",
                        "target": "/auth/login",
                        "data": {
                            "email": f"{persona_id}@example.com",
                            "password": "valid_password",
                        },
                        "rationale": f"Login as {persona_label}",
                    },
                    {
                        "action": "assert_status",
                        "target": "last_response",
                        "data": {"status": 200},
                        "rationale": "Verify login succeeded",
                    },
                    {
                        "action": "assert_cookie_set",
                        "target": "last_response",
                        "data": {"cookie": "dazzle_session"},
                        "rationale": "Verify session cookie is set",
                    },
                ],
                tags=["auth", "login", "generated", "dsl-derived"],
            )
        )

        # AUTH_LOGIN_INVALID_PASSWORD — wrong password rejected
        tests.append(
            self._create_test(
                test_id=f"AUTH_LOGIN_INVALID_{persona_id.upper()}",
                title=f"Reject invalid password for {persona_label}",
                description=f"Test that {persona_label} cannot log in with wrong password",
                trigger="api_call",
                persona=persona_id,
                steps=[
                    {
                        "action": "post",
                        "target": "/auth/login",
                        "data": {
                            "email": f"{persona_id}@example.com",
                            "password": "wrong_password",
                        },
                        "rationale": f"Attempt login as {persona_label} with wrong password",
                    },
                    {
                        "action": "assert_status",
                        "target": "last_response",
                        "data": {"status": 401},
                        "rationale": "Verify login rejected",
                    },
                    {
                        "action": "assert_no_cookie",
                        "target": "last_response",
                        "data": {"cookie": "dazzle_session"},
                        "rationale": "Verify no session cookie is set",
                    },
                ],
                tags=["auth", "login", "negative", "generated", "dsl-derived"],
            )
        )

        # AUTH_REDIRECT — post-login redirect to persona's default_route
        redirect_route = persona.default_route or "/app"
        tests.append(
            self._create_test(
                test_id=f"AUTH_REDIRECT_{persona_id.upper()}",
                title=f"{persona_label} redirects to {redirect_route} after login",
                description=(
                    f"Test that {persona_label} is directed to "
                    f"{redirect_route} after successful login"
                ),
                trigger="api_call",
                persona=persona_id,
                steps=[
                    {
                        "action": "post",
                        "target": "/auth/login",
                        "data": {
                            "email": f"{persona_id}@example.com",
                            "password": "valid_password",
                        },
                        "rationale": f"Login as {persona_label}",
                    },
                    {
                        "action": "assert_redirect_url",
                        "target": "last_response",
                        "data": {"redirect_url": redirect_route},
                        "rationale": f"Verify redirect to {redirect_route}",
                    },
                ],
                tags=["auth", "redirect", "generated", "dsl-derived"],
            )
        )

        # AUTH_SESSION_VALID — authenticated request succeeds
        tests.append(
            self._create_test(
                test_id=f"AUTH_SESSION_VALID_{persona_id.upper()}",
                title=f"Authenticated request succeeds for {persona_label}",
                description=f"Test that requests with a valid session cookie succeed for {persona_label}",
                trigger="api_call",
                persona=persona_id,
                steps=[
                    {
                        "action": "login_as",
                        "target": persona_id,
                        "rationale": f"Authenticate as {persona_label}",
                    },
                    {
                        "action": "get",
                        "target": redirect_route,
                        "rationale": f"Access {redirect_route} with session",
                    },
                    {
                        "action": "assert_status",
                        "target": "last_response",
                        "data": {"status": 200},
                        "rationale": "Verify access granted",
                    },
                ],
                tags=["auth", "session", "generated", "dsl-derived"],
            )
        )

        # AUTH_SESSION_EXPIRED — expired session rejected
        tests.append(
            self._create_test(
                test_id=f"AUTH_SESSION_EXPIRED_{persona_id.upper()}",
                title=f"Expired session rejected for {persona_label}",
                description="Test that an expired or invalid session cookie is rejected",
                trigger="api_call",
                persona=persona_id,
                steps=[
                    {
                        "action": "get_with_cookie",
                        "target": redirect_route,
                        "data": {"cookie": "dazzle_session", "value": "invalid-token"},
                        "rationale": "Access page with invalid session",
                    },
                    {
                        "action": "assert_unauthenticated",
                        "target": "last_response",
                        "data": {"expect": [401, 302]},
                        "rationale": "Verify 401 or redirect to login",
                    },
                ],
                tags=["auth", "session", "negative", "generated", "dsl-derived"],
            )
        )

        # AUTH_LOGOUT — logout clears session
        tests.append(
            self._create_test(
                test_id=f"AUTH_LOGOUT_{persona_id.upper()}",
                title=f"Logout clears session for {persona_label}",
                description=f"Test that logout invalidates the session for {persona_label}",
                trigger="api_call",
                persona=persona_id,
                steps=[
                    {
                        "action": "login_as",
                        "target": persona_id,
                        "rationale": f"Authenticate as {persona_label}",
                    },
                    {
                        "action": "post",
                        "target": "/auth/logout",
                        "rationale": "Logout",
                    },
                    {
                        "action": "assert_cookie_cleared",
                        "target": "last_response",
                        "data": {"cookie": "dazzle_session"},
                        "rationale": "Verify session cookie is cleared",
                    },
                    {
                        "action": "get",
                        "target": redirect_route,
                        "rationale": "Attempt access after logout",
                    },
                    {
                        "action": "assert_unauthenticated",
                        "target": "last_response",
                        "data": {"expect": [401, 302]},
                        "rationale": "Verify session is invalid after logout",
                    },
                ],
                tags=["auth", "logout", "generated", "dsl-derived"],
            )
        )

        return tests

    # =========================================================================
    # Workspace Tests
    # =========================================================================

    def _generate_workspace_tests(self, workspace: WorkspaceSpec) -> list[dict[str, Any]]:
        """Generate navigation and access tests for a workspace.

        Workspace tests use Playwright for browser-based testing but are Tier 1
        (scripted, deterministic). They do NOT require LLM agent involvement.

        Test Tiers:
        - tier1: Scripted tests (API or Playwright) - fast, deterministic, free
        - tier2: Agent tests (LLM-driven) - adaptive, slow, costs money

        Workspace navigation is tier1 because the steps are predictable and
        don't require visual judgment or adaptive decision-making.
        """
        tests = []

        workspace_label = workspace.title or workspace.name

        # Determine the route for this workspace
        # Workspaces typically have routes like /workspace_name or derive from their name
        workspace_route = f"/app/workspaces/{workspace.name}"

        # Tier 1 Playwright navigation test - scripted, no LLM needed
        tests.append(
            self._create_test(
                test_id=f"WS_{workspace.name.upper()}_NAV",
                title=f"Navigate to {workspace_label}",
                description=f"Verify {workspace_label} workspace loads and displays correctly",
                trigger="playwright",  # Tier 1: Scripted Playwright test
                steps=[
                    {
                        "action": "navigate_to",
                        "target": f"workspace:{workspace.name}",
                        "data": {"route": workspace_route},
                        "rationale": f"Navigate to {workspace_label} workspace",
                    },
                    {
                        "action": "wait_for_load",
                        "target": "page",
                        "rationale": "Wait for workspace to fully load",
                    },
                    {
                        "action": "assert_visible",
                        "target": f"[data-dazzle-workspace='{workspace.name}']",
                        "rationale": "Verify workspace container is visible",
                    },
                    {
                        "action": "assert_no_errors",
                        "target": "console",
                        "rationale": "Verify no JavaScript errors in console",
                    },
                ],
                tags=["workspace", "navigation", "playwright", "tier1", "generated", "dsl-derived"],
            )
        )

        # API-based workspace route check (can run without browser)
        tests.append(
            self._create_test(
                test_id=f"WS_{workspace.name.upper()}_ROUTE",
                title=f"Workspace {workspace_label} route exists",
                description=f"Verify {workspace_label} workspace route is configured",
                trigger="api_call",
                steps=[
                    {
                        "action": "check_route",
                        "target": f"workspace:{workspace.name}",
                        "data": {"route": workspace_route},
                        "rationale": f"Verify route for {workspace_label} is defined",
                    }
                ],
                tags=["workspace", "route", "generated", "dsl-derived"],
            )
        )

        return tests

    # =========================================================================
    # Event Tests
    # =========================================================================

    def _generate_event_tests(self, event: EventSpec) -> list[dict[str, Any]]:
        """Generate event emission and handling tests."""
        tests = []

        # Event emission test
        tests.append(
            self._create_test(
                test_id=f"EVT_{event.name.upper()}_EMIT",
                title=f"Emit {event.name} event",
                description=f"Test that {event.name} event is emitted correctly",
                trigger="event_emission",
                steps=[
                    {
                        "action": "emit_event",
                        "target": f"event:{event.name}",
                        "data": self._generate_event_payload(event),
                        "rationale": f"Emit {event.name} event",
                    },
                    {
                        "action": "assert_event_logged",
                        "target": f"topic:{event.topic}",
                        "data": {"event_type": event.name},
                        "rationale": "Verify event was logged",
                    },
                ],
                tags=["event", "emission", "generated", "dsl-derived"],
            )
        )

        # Event structure validation
        tests.append(
            self._create_test(
                test_id=f"EVT_{event.name.upper()}_SCHEMA",
                title=f"Validate {event.name} schema",
                description=f"Test that {event.name} event payload is validated",
                trigger="event_emission",
                steps=[
                    {
                        "action": "emit_event_expect_error",
                        "target": f"event:{event.name}",
                        "data": {},  # Invalid payload
                        "rationale": f"Emit invalid {event.name} event",
                    },
                    {
                        "action": "assert_error",
                        "target": "last_response",
                        "data": {"type": "event_validation_error"},
                        "rationale": "Verify validation error",
                    },
                ],
                tags=["event", "validation", "generated", "dsl-derived"],
            )
        )

        return tests

    # =========================================================================
    # Process Tests
    # =========================================================================

    def _generate_process_tests(self, process: ProcessSpec) -> list[dict[str, Any]]:
        """Generate workflow execution tests."""
        tests = []

        # Process trigger test
        tests.append(
            self._create_test(
                test_id=f"PROC_{process.name.upper()}_TRIGGER",
                title=f"Trigger {process.title or process.name}",
                description=f"Test that {process.name} process starts correctly",
                trigger="process_start",
                steps=[
                    {
                        "action": "trigger_process",
                        "target": f"process:{process.name}",
                        "data": self._generate_process_inputs(process),
                        "rationale": f"Start {process.name} process",
                    },
                    {
                        "action": "assert_process_started",
                        "target": f"process:{process.name}",
                        "rationale": "Verify process started",
                    },
                ],
                tags=["process", "trigger", "generated", "dsl-derived"],
            )
        )

        # Process completion test (happy path)
        tests.append(
            self._create_test(
                test_id=f"PROC_{process.name.upper()}_COMPLETE",
                title=f"Complete {process.title or process.name}",
                description=f"Test that {process.name} process completes successfully",
                trigger="process_completion",
                steps=[
                    {
                        "action": "trigger_process",
                        "target": f"process:{process.name}",
                        "data": self._generate_process_inputs(process),
                        "rationale": f"Start {process.name} process",
                    },
                    {
                        "action": "wait_for_process",
                        "target": f"process:{process.name}",
                        "data": {"timeout_seconds": process.timeout_seconds or 60},
                        "rationale": "Wait for process completion",
                    },
                    {
                        "action": "assert_process_completed",
                        "target": f"process:{process.name}",
                        "rationale": "Verify process completed",
                    },
                ],
                tags=["process", "completion", "generated", "dsl-derived"],
            )
        )

        # Step execution tests
        for step in process.steps or []:
            tests.append(
                self._create_test(
                    test_id=f"PROC_{process.name.upper()}_STEP_{step.name.upper()}",
                    title=f"{process.name}: Step {step.name}",
                    description=f"Test that step {step.name} executes correctly",
                    trigger="process_step",
                    steps=[
                        {
                            "action": "execute_step",
                            "target": f"process:{process.name}",
                            "data": {"step": step.name},
                            "rationale": f"Execute step {step.name}",
                        },
                        {
                            "action": "assert_step_completed",
                            "target": f"step:{step.name}",
                            "rationale": "Verify step completed",
                        },
                    ],
                    tags=["process", "step", "generated", "dsl-derived"],
                )
            )

        return tests

    # =========================================================================
    # Helpers
    # =========================================================================

    def _create_test(
        self,
        test_id: str,
        title: str,
        description: str,
        trigger: str,
        steps: list[dict[str, Any]],
        entities: list[str] | None = None,
        persona: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        """Create a test design dict."""
        return {
            "test_id": test_id,
            "title": title,
            "description": description,
            "trigger": trigger,
            "persona": persona,
            "scenario": None,
            "steps": steps,
            "expected_outcomes": [f"{title} succeeds"],
            "entities": entities or [],
            "surfaces": [],
            "tags": tags or [],
            "status": "accepted",
            "source": "dsl-derived",
            "created_at": datetime.now().isoformat(),
        }

    def _generate_entity_data(self, entity: EntitySpec) -> dict[str, Any]:
        """Generate valid test data for an entity."""
        from dazzle.core.ir.fields import FieldTypeKind

        data = {}
        timestamp = int(datetime.now().timestamp() * 1000) % 100000

        for fld in entity.fields:
            if fld.name in ("id", "created_at", "updated_at"):
                continue
            if not fld.is_required:
                continue

            # Handle reference fields
            if fld.type.kind == FieldTypeKind.REF:
                continue  # Skip refs for now - handled by _generate_entity_data_with_refs

            data[fld.name] = self._generate_field_value(fld, timestamp)

        # Satisfy invariant OR clauses that require at least one optional field
        # e.g. invariant: uprn != null or canonical_text != null
        for field_name in _invariant_required_fields(entity):
            if field_name not in data:
                inv_field = next((f for f in entity.fields if f.name == field_name), None)
                if inv_field and inv_field.type.kind != FieldTypeKind.REF:
                    data[field_name] = self._generate_field_value(inv_field, timestamp)

        return data

    def _generate_parent_setup_steps(
        self, required_refs: list[tuple[str, str, str]]
    ) -> list[dict[str, Any]]:
        """Generate setup steps that create parent entities for required refs.

        Recursively creates ancestor entities for transitive FK chains
        (e.g. A → B → C creates C first, then B with ref to C, then A with ref to B).
        Circular dependencies are detected and skipped.

        Args:
            required_refs: List of (field_name, target_entity, pk_field) tuples

        Returns:
            List of step dictionaries for creating parent entities in dependency order
        """
        steps: list[dict[str, Any]] = []
        created: set[str] = set()
        visiting: set[str] = set()

        def _create_ancestors(entity_name: str) -> None:
            if entity_name in created or entity_name not in self._entity_map:
                return
            if entity_name in visiting:
                # Circular dependency — skip to avoid infinite recursion
                return

            visiting.add(entity_name)
            parent = self._entity_map[entity_name]
            parent_refs = self._get_required_refs(parent)

            # Recursively create this parent's own dependencies first
            for _fn, target, _pk in parent_refs:
                _create_ancestors(target)

            # Now create this entity — all its ancestors already exist
            parent_data = self._generate_entity_data(parent)
            for fn, target, pk in parent_refs:
                if target in created:
                    parent_data[fn] = f"$ref:parent_{target.lower()}.{pk}"

            steps.append(
                {
                    "action": "create",
                    "target": f"entity:{entity_name}",
                    "data": parent_data,
                    "store_result": f"parent_{entity_name.lower()}",
                    "rationale": f"Create parent {parent.title or entity_name}",
                }
            )
            created.add(entity_name)
            visiting.discard(entity_name)

        for _fn, target_entity, _pk in required_refs:
            _create_ancestors(target_entity)

        return steps

    def _generate_entity_data_with_refs(
        self, entity: EntitySpec, required_refs: list[tuple[str, str, str]]
    ) -> dict[str, Any]:
        """Generate entity data including reference field placeholders.

        Args:
            entity: The entity to generate data for
            required_refs: List of (field_name, target_entity, pk_field) tuples

        Returns:
            Dictionary with entity data, including $ref placeholders for foreign keys
        """
        # Start with base data (without refs)
        data = self._generate_entity_data(entity)

        # Add ref placeholders that reference stored parent IDs
        for field_name, target_entity, pk_field in required_refs:
            # Use $ref: syntax to reference the stored parent ID
            data[field_name] = f"$ref:parent_{target_entity.lower()}.{pk_field}"

        return data

    def _generate_field_value(self, field: FieldSpec, unique_suffix: int = 0) -> Any:
        """Generate a test value for a field."""
        import uuid as uuid_module

        from dazzle.core.ir.fields import FieldTypeKind

        type_kind = field.type.kind
        name = field.name.lower()
        # Use timestamp-based suffixes for unique fields to avoid collisions
        # across test runs (e.g. on staging servers without DB resets)
        if field.is_unique:
            import time

            ts = int(time.time() * 1000) % 1_000_000
            suffix = f"_{ts}_{unique_suffix}"
        else:
            suffix = ""

        # Enum handling
        if type_kind == FieldTypeKind.ENUM:
            if field.type.enum_values:
                return field.type.enum_values[0]
            return "default"

        # Common field name patterns
        if name == "email" or type_kind == FieldTypeKind.EMAIL:
            return f"test{suffix}@example.com"
        if name == "version":
            return f"1.0.{unique_suffix}"
        if name in ("serial_number", "serialnumber"):
            return f"SN{unique_suffix or 1}"

        # Type-based generation
        if type_kind == FieldTypeKind.UUID:
            return str(uuid_module.uuid4())
        elif type_kind == FieldTypeKind.STR:
            value = f"Test {field.name}{suffix}"
            max_len = field.type.max_length
            if max_len and len(value) > max_len:
                # Truncate but keep suffix for uniqueness
                if suffix and max_len >= len(suffix) + 1:
                    value = value[: max_len - len(suffix)] + suffix
                else:
                    value = value[:max_len]
            return value
        elif type_kind == FieldTypeKind.TEXT:
            return f"Test description for {field.name}{suffix}"
        elif type_kind == FieldTypeKind.INT:
            return 1
        elif type_kind == FieldTypeKind.DECIMAL:
            return 10.0
        elif type_kind == FieldTypeKind.BOOL:
            return True
        elif type_kind == FieldTypeKind.DATE:
            return datetime.now().strftime("%Y-%m-%d")
        elif type_kind == FieldTypeKind.DATETIME:
            return datetime.now().isoformat()
        elif type_kind == FieldTypeKind.URL:
            return f"https://example.com/{field.name}{suffix}"
        elif type_kind == FieldTypeKind.FILE:
            return f"test_file{suffix}.txt"
        elif type_kind == FieldTypeKind.MONEY:
            # Money fields expand to _minor + _currency per #131
            currency = field.type.currency_code or "USD"
            return {"_minor": 10000, "_currency": currency}
        elif type_kind == FieldTypeKind.JSON:
            return {"key": f"value{suffix}"}
        else:
            return f"test_{field.name}{suffix}"

    def _generate_event_payload(self, event: EventSpec) -> dict[str, Any]:
        """Generate test payload for an event."""
        payload = {}

        for ef in event.custom_fields or []:
            payload[ef.name] = self._generate_event_field_value(ef)

        return payload

    def _generate_event_field_value(self, field: Any) -> Any:
        """Generate test value for an event field."""
        import uuid as uuid_module

        # EventFieldSpec uses 'field_type', FieldSpec uses 'type'
        type_name: Any = getattr(field, "field_type", None) or getattr(field, "type", "str")
        if type_name is not None and hasattr(type_name, "kind"):
            type_name = type_name.kind.value
        type_name = str(type_name).lower()

        if "uuid" in type_name:
            return str(uuid_module.uuid4())
        elif "str" in type_name:
            return f"test_{field.name}"
        elif "int" in type_name:
            return 1
        elif "bool" in type_name:
            return True
        elif "date" in type_name:
            return datetime.now().strftime("%Y-%m-%d")
        else:
            return f"test_{field.name}"

    def _generate_process_inputs(self, process: ProcessSpec) -> dict[str, Any]:
        """Generate test inputs for a process."""
        import uuid as uuid_module

        inputs: dict[str, Any] = {}

        for inp in process.inputs or []:
            # Process inputs may use 'field_type' or 'type'
            type_name: Any = getattr(inp, "field_type", None) or getattr(inp, "type", "str")
            if type_name is not None and hasattr(type_name, "kind"):
                type_name = type_name.kind.value
            type_name = str(type_name).lower()

            if "uuid" in type_name:
                inputs[inp.name] = str(uuid_module.uuid4())
            elif "str" in type_name:
                inputs[inp.name] = f"test_{inp.name}"
            elif "int" in type_name:
                inputs[inp.name] = 1
            elif "bool" in type_name:
                inputs[inp.name] = True
            else:
                inputs[inp.name] = f"test_{inp.name}"

        return inputs

    def _slugify(self, text: str) -> str:
        """Convert text to slug."""
        return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def generate_tests_from_dsl(project_path: Path) -> GeneratedTestSuite:
    """Generate tests from a project's DSL files."""
    appspec = load_project(project_path)
    generator = DSLTestGenerator(appspec)
    return generator.generate_all()


def save_generated_tests(project_path: Path, suite: GeneratedTestSuite) -> Path:
    """Save generated tests to the project."""
    output_dir = project_path / "dsl" / "tests"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "dsl_generated_tests.json"
    with open(output_file, "w") as f:
        json.dump(suite.to_dict(), f, indent=2, default=str)

    print(f"Generated {len(suite.designs)} tests from DSL")
    print(f"DSL hash: {suite.dsl_hash}")
    print(
        f"Coverage: {len(suite.coverage.entities_covered)} entities, "
        f"{len(suite.coverage.state_machines_covered)} state machines, "
        f"{len(suite.coverage.events_covered)} events, "
        f"{len(suite.coverage.processes_covered)} processes"
    )
    print(f"Saved to: {output_file}")

    return output_file


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m dazzle.testing.dsl_test_generator <project_path>")
        sys.exit(1)

    project_path = Path(sys.argv[1]).resolve()
    suite = generate_tests_from_dsl(project_path)
    save_generated_tests(project_path, suite)
