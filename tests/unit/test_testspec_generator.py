"""
Unit tests for the E2E TestSpec Generator.

Tests that the generator correctly produces E2ETestSpec from AppSpec.
"""

from typing import Any

import pytest

from dazzle.core.ir import (
    AppSpec,
    DomainSpec,
    EntitySpec,
    FieldModifier,
    FieldSpec,
    FieldType,
    FieldTypeKind,
    FlowAssertionKind,
    FlowPriority,
    FlowStepKind,
    SurfaceMode,
    SurfaceSpec,
)
from dazzle.core.ir.computed import (
    AggregateCall,
    AggregateFunction,
    ComputedFieldSpec,
    FieldReference,
)
from dazzle.core.ir.domain import AccessSpec, PermissionKind, PermissionRule
from dazzle.core.ir.personas import PersonaSpec
from dazzle.core.ir.state_machine import (
    StateMachineSpec,
    StateTransition,
    TransitionGuard,
)
from dazzle.testing.testspec_generator import (
    generate_access_control_flows,
    generate_computed_field_flows,
    generate_e2e_testspec,
    generate_entity_crud_flows,
    generate_entity_fixtures,
    generate_fixtures,
    generate_reference_flows,
    generate_state_machine_flows,
    generate_surface_flows,
    generate_validation_flows,
)


def _pk() -> FieldSpec:
    return FieldSpec(
        name="id", type=FieldType(kind=FieldTypeKind.UUID), modifiers=[FieldModifier.PK]
    )


def _req_str(name: str = "title", max_length: int = 200) -> FieldSpec:
    return FieldSpec(
        name=name,
        type=FieldType(kind=FieldTypeKind.STR, max_length=max_length),
        modifiers=[FieldModifier.REQUIRED],
    )


def _enum(name: str, values: list[str]) -> FieldSpec:
    return FieldSpec(name=name, type=FieldType(kind=FieldTypeKind.ENUM, enum_values=values))


def _entity(name: str, *fields: FieldSpec, **kwargs: Any) -> EntitySpec:
    return EntitySpec(name=name, title=name, fields=[_pk(), *fields], **kwargs)


def _app(name: str, *entities: EntitySpec, **kwargs: Any) -> AppSpec:
    return AppSpec(
        name=name,
        title=f"{name} app",
        domain=DomainSpec(entities=list(entities)),
        surfaces=[
            SurfaceSpec(name=f"{e.name.lower()}_list", entity_ref=e.name, mode=SurfaceMode.LIST)
            for e in entities
        ],
        **kwargs,
    )


def _asserts(flow: Any) -> list[Any]:
    return [s for s in flow.steps if s.kind == FlowStepKind.ASSERT]


@pytest.fixture
def task_entity() -> EntitySpec:
    """Create a sample Task entity for testing."""
    return _entity(
        "Task",
        _req_str(),
        FieldSpec(name="description", type=FieldType(kind=FieldTypeKind.TEXT)),
        FieldSpec(name="completed", type=FieldType(kind=FieldTypeKind.BOOL), default=False),
        _enum("priority", ["low", "medium", "high"]),
        FieldSpec(name="due_date", type=FieldType(kind=FieldTypeKind.DATE)),
    )


@pytest.fixture
def task_surfaces() -> list[SurfaceSpec]:
    """Create sample surfaces for Task entity."""
    return [
        SurfaceSpec(name="task_list", title="Tasks", entity_ref="Task", mode=SurfaceMode.LIST),
        SurfaceSpec(
            name="task_detail", title="Task Detail", entity_ref="Task", mode=SurfaceMode.VIEW
        ),
        SurfaceSpec(
            name="task_create", title="Create Task", entity_ref="Task", mode=SurfaceMode.CREATE
        ),
        SurfaceSpec(name="task_edit", title="Edit Task", entity_ref="Task", mode=SurfaceMode.EDIT),
    ]


@pytest.fixture
def simple_appspec(task_entity: EntitySpec, task_surfaces: list[SurfaceSpec]) -> AppSpec:
    """Create a simple AppSpec for testing."""
    return AppSpec(
        name="todo",
        title="Todo App",
        version="0.1.0",
        domain=DomainSpec(entities=[task_entity]),
        surfaces=task_surfaces,
    )


@pytest.fixture
def ticket_entity_with_state_machine() -> EntitySpec:
    return _entity(
        "Ticket",
        _req_str(),
        _enum("status", ["open", "in_progress", "resolved", "closed"]),
        state_machine=StateMachineSpec(
            status_field="status",
            states=["open", "in_progress", "resolved", "closed"],
            transitions=[
                StateTransition(from_state="open", to_state="in_progress"),
                StateTransition(from_state="in_progress", to_state="resolved"),
                StateTransition(from_state="resolved", to_state="closed"),
            ],
        ),
    )


@pytest.fixture
def role_guarded_ticket_entity() -> EntitySpec:
    """Ticket entity whose transition is gated by role(agent)."""
    return _entity(
        "Ticket",
        _req_str(),
        _enum("status", ["open", "in_progress"]),
        state_machine=StateMachineSpec(
            status_field="status",
            states=["open", "in_progress"],
            transitions=[
                StateTransition(
                    from_state="open",
                    to_state="in_progress",
                    guards=[TransitionGuard(requires_role="agent")],
                ),
            ],
        ),
    )


@pytest.fixture
def invoice_entity_with_computed() -> EntitySpec:
    return _entity(
        "Invoice",
        _req_str("number", 50),
        computed_fields=[
            ComputedFieldSpec(
                name="item_count",
                expression=AggregateCall(
                    function=AggregateFunction.COUNT,
                    field=FieldReference(path=["line_items"]),
                ),
            ),
            ComputedFieldSpec(
                name="total",
                expression=AggregateCall(
                    function=AggregateFunction.SUM,
                    field=FieldReference(path=["line_items", "amount"]),
                ),
            ),
        ],
    )


@pytest.fixture
def document_entity_with_access() -> EntitySpec:
    return _entity(
        "Document",
        _req_str(),
        access=AccessSpec(
            permissions=[
                PermissionRule(operation=PermissionKind.CREATE, require_auth=True),
                PermissionRule(operation=PermissionKind.UPDATE, require_auth=True),
                PermissionRule(operation=PermissionKind.DELETE, require_auth=True),
            ],
        ),
    )


@pytest.fixture
def task_entity_with_ref() -> EntitySpec:
    return _entity(
        "Task",
        _req_str(),
        FieldSpec(
            name="project_id",
            type=FieldType(kind=FieldTypeKind.REF, ref_entity="Project"),
            modifiers=[FieldModifier.REQUIRED],
        ),
    )


@pytest.fixture
def full_featured_appspec() -> AppSpec:
    """AppSpec with state machine, computed field and access rules."""
    ticket = _entity(
        "Ticket",
        _req_str(),
        _enum("status", ["open", "closed"]),
        state_machine=StateMachineSpec(
            status_field="status",
            states=["open", "closed"],
            transitions=[StateTransition(from_state="open", to_state="closed")],
        ),
        computed_fields=[
            ComputedFieldSpec(
                name="comment_count",
                expression=AggregateCall(
                    function=AggregateFunction.COUNT,
                    field=FieldReference(path=["comments"]),
                ),
            ),
        ],
        access=AccessSpec(
            permissions=[PermissionRule(operation=PermissionKind.CREATE, require_auth=True)],
        ),
    )
    return _app("support", ticket)


class TestFixtureGeneration:
    """Tests for fixture generation."""

    def test_generate_entity_fixtures(self, task_entity: EntitySpec) -> None:
        """Fixtures for an entity — IDs/data, types, PK exclusion."""
        fixtures = generate_entity_fixtures(task_entity)
        assert len(fixtures) >= 2  # valid and updated

        valid = next((f for f in fixtures if f.id == "Task_valid"), None)
        assert valid is not None
        assert valid.entity == "Task"
        assert "title" in valid.data
        assert valid.data["completed"] is True  # bool defaults to True

        updated = next((f for f in fixtures if f.id == "Task_updated"), None)
        assert updated is not None
        assert updated.entity == "Task"

        assert isinstance(valid.data["title"], str)
        assert isinstance(valid.data["completed"], bool)
        assert valid.data["priority"] in ["low", "medium", "high"]
        assert isinstance(valid.data["due_date"], str)  # date as ISO string
        assert "-" in valid.data["due_date"]
        assert "id" not in valid.data  # PK excluded

    def test_generate_fixtures_all_entities(self, simple_appspec: AppSpec) -> None:
        """Test generating fixtures for all entities in AppSpec."""
        fixtures = generate_fixtures(simple_appspec)
        assert len(fixtures) >= 2  # valid + updated for Task
        assert {f.entity for f in fixtures} == {"Task"}


class TestCRUDFlowGeneration:
    """Tests for CRUD flow generation."""

    def test_generate_crud_flows(self, task_entity: EntitySpec, simple_appspec: AppSpec) -> None:
        flows = generate_entity_crud_flows(task_entity, simple_appspec)
        assert len(flows) == 4
        assert {f.id for f in flows} == {
            "Task_create_valid",
            "Task_view_detail",
            "Task_update_valid",
            "Task_delete",
        }

    def test_create_flow_structure(self, task_entity: EntitySpec, simple_appspec: AppSpec) -> None:
        flows = generate_entity_crud_flows(task_entity, simple_appspec)
        create_flow = next((f for f in flows if f.id == "Task_create_valid"), None)

        assert create_flow is not None
        assert create_flow.priority == FlowPriority.HIGH
        assert create_flow.entity == "Task"
        assert create_flow.auto_generated is True
        assert "crud" in create_flow.tags
        assert "create" in create_flow.tags

        steps = create_flow.steps
        assert len(steps) >= 3  # navigate, click create, fill, click save, assert
        assert steps[0].kind == FlowStepKind.NAVIGATE
        assert "view:" in steps[0].target
        assert [s for s in steps if s.kind == FlowStepKind.CLICK and "create" in (s.target or "")]
        assert steps[-1].kind == FlowStepKind.ASSERT
        assert steps[-1].assertion is not None
        assert steps[-1].assertion.kind == FlowAssertionKind.ENTITY_EXISTS

    def test_update_flow_has_preconditions(
        self, task_entity: EntitySpec, simple_appspec: AppSpec
    ) -> None:
        flows = generate_entity_crud_flows(task_entity, simple_appspec)
        update_flow = next((f for f in flows if f.id == "Task_update_valid"), None)

        assert update_flow is not None
        assert update_flow.preconditions is not None
        assert "Task_valid" in update_flow.preconditions.fixtures

    def test_delete_flow_has_confirmation(
        self, task_entity: EntitySpec, simple_appspec: AppSpec
    ) -> None:
        flows = generate_entity_crud_flows(task_entity, simple_appspec)
        delete_flow = next((f for f in flows if f.id == "Task_delete"), None)

        assert delete_flow is not None
        assert [
            s
            for s in delete_flow.steps
            if s.kind == FlowStepKind.CLICK and "confirm" in (s.target or "")
        ]
        assert _asserts(delete_flow)[-1].assertion.kind == FlowAssertionKind.ENTITY_NOT_EXISTS


class TestValidationFlowGeneration:
    """Tests for validation flow generation."""

    def test_generate_validation_flows(
        self, task_entity: EntitySpec, simple_appspec: AppSpec
    ) -> None:
        """Required-field flow exists with validation_error assertion."""
        flows = generate_validation_flows(task_entity, simple_appspec)
        assert len(flows) >= 1

        title_flow = next((f for f in flows if "title" in f.id), None)
        assert title_flow is not None
        assert title_flow.priority == FlowPriority.MEDIUM
        assert "validation" in title_flow.tags

        assert_steps = _asserts(title_flow)
        assert len(assert_steps) >= 1
        assert assert_steps[0].assertion.kind == FlowAssertionKind.VALIDATION_ERROR
        assert "title" in assert_steps[0].assertion.target


class TestSurfaceFlowGeneration:
    """Tests for surface navigation flow generation."""

    def test_generate_surface_flows(
        self, task_surfaces: list[SurfaceSpec], simple_appspec: AppSpec
    ) -> None:
        """Navigation flows for surfaces — id/priority/tags + visibility assertion."""
        flows = generate_surface_flows(task_surfaces[0], simple_appspec)
        assert len(flows) >= 1

        nav_flow = flows[0]
        assert nav_flow.id == "navigate_task_list"
        assert nav_flow.priority == FlowPriority.LOW
        assert "navigation" in nav_flow.tags

        assert_steps = _asserts(nav_flow)
        assert len(assert_steps) >= 1
        assert assert_steps[0].assertion.kind == FlowAssertionKind.VISIBLE


class TestFullE2ETestSpecGeneration:
    """Tests for complete E2ETestSpec generation."""

    def test_generate_complete_testspec(self, simple_appspec: AppSpec) -> None:
        testspec = generate_e2e_testspec(simple_appspec)

        assert testspec.app_name == "todo"
        assert testspec.version == "0.1.0"
        assert len(testspec.fixtures) >= 2
        assert len(testspec.flows) >= 5  # CRUD + validation + navigation
        assert testspec.metadata["entity_count"] == 1

        # Fixture lookup by ID
        valid_fixture = testspec.get_fixture("Task_valid")
        assert valid_fixture is not None
        assert valid_fixture.entity == "Task"

        # Usability / a11y rules
        max_steps = next(
            (r for r in testspec.usability_rules if r.id == "high_priority_max_steps"), None
        )
        assert max_steps is not None
        assert max_steps.threshold == 5
        contrast = next((r for r in testspec.a11y_rules if r.id == "color-contrast"), None)
        assert contrast is not None
        assert contrast.level == "AA"

    def test_testspec_flows_have_correct_priority(self, simple_appspec: AppSpec) -> None:
        testspec = generate_e2e_testspec(simple_appspec)

        # Create and update high; validation and delete medium; navigation low
        assert len(testspec.get_flows_by_priority(FlowPriority.HIGH)) >= 2
        assert len(testspec.get_flows_by_priority(FlowPriority.MEDIUM)) >= 2
        assert len(testspec.get_flows_by_priority(FlowPriority.LOW)) >= 1

    def test_testspec_flows_by_entity(self, simple_appspec: AppSpec) -> None:
        testspec = generate_e2e_testspec(simple_appspec)
        assert len(testspec.get_flows_by_entity("Task")) >= 4  # at least CRUD flows


class TestMultiEntityGeneration:
    """Tests for generating tests with multiple entities."""

    def test_multi_entity_spec(self) -> None:
        """Fixtures, CRUD flows and metadata cover every entity."""
        task = _entity("Task", _req_str())
        user = _entity(
            "User",
            FieldSpec(
                name="email",
                type=FieldType(kind=FieldTypeKind.EMAIL),
                modifiers=[FieldModifier.REQUIRED, FieldModifier.UNIQUE],
            ),
            _req_str("name", 100),
        )
        testspec = generate_e2e_testspec(_app("multi_app", task, user))

        for entity in ("Task", "User"):
            assert len([f for f in testspec.fixtures if f.entity == entity]) >= 2
            assert len(testspec.get_flows_by_entity(entity)) >= 4  # CRUD flows
        assert testspec.metadata["entity_count"] == 2
        assert testspec.metadata["surface_count"] == 2


class TestStateMachineFlowGeneration:
    """Tests for state machine transition flow generation."""

    def test_invalid_transition_flows(self, ticket_entity_with_state_machine: EntitySpec) -> None:
        app = _app("support", ticket_entity_with_state_machine)
        flows = generate_state_machine_flows(ticket_entity_with_state_machine, app)
        assert len(flows) >= 3  # 3 valid transitions plus some invalid

        invalid_flows = [f for f in flows if "transition_invalid" in f.id]
        assert len(invalid_flows) >= 1
        assert "invalid_transition" in invalid_flows[0].tags

        assert_steps = _asserts(invalid_flows[0])
        assert len(assert_steps) >= 1
        assert assert_steps[0].assertion.kind == FlowAssertionKind.STATE_TRANSITION_BLOCKED

    def test_unguarded_transition_emits_anonymous_flow(
        self, ticket_entity_with_state_machine: EntitySpec
    ) -> None:
        """Valid, non-role-guarded transitions emit a plain flow (no user_role)."""
        app = _app("support", ticket_entity_with_state_machine)
        flows = generate_state_machine_flows(ticket_entity_with_state_machine, app)

        valid_flow = next(
            (f for f in flows if f.id == "Ticket_transition_open_to_in_progress"), None
        )
        assert valid_flow is not None
        assert valid_flow.entity == "Ticket"
        assert "state_machine" in valid_flow.tags
        assert "transition" in valid_flow.tags
        assert valid_flow.preconditions is not None
        assert valid_flow.preconditions.user_role is None
        assert valid_flow.preconditions.fixtures == ["Ticket_state_open"]
        assert "skip:no-persona" not in valid_flow.tags
        assert len(valid_flow.steps) > 0

    def test_role_guarded_transition_with_matching_persona(
        self, role_guarded_ticket_entity: EntitySpec
    ) -> None:
        """A role-guarded transition resolves to a persona-scoped flow."""
        appspec = _app(
            "support",
            role_guarded_ticket_entity,
            personas=[PersonaSpec(id="support_agent", label="Support Agent", role="agent")],
        )
        flows = generate_state_machine_flows(role_guarded_ticket_entity, appspec)

        role_flow = next(
            (f for f in flows if f.id == "Ticket_transition_open_to_in_progress_as_support_agent"),
            None,
        )
        assert role_flow is not None
        assert role_flow.preconditions is not None
        assert role_flow.preconditions.user_role == "support_agent"
        assert role_flow.preconditions.authenticated is True
        assert role_flow.preconditions.fixtures == ["Ticket_state_open"]
        assert "skip:no-persona" not in role_flow.tags
        assert len(role_flow.steps) > 0

    def test_role_guarded_transition_without_persona_emits_stub_and_warns(
        self, role_guarded_ticket_entity: EntitySpec
    ) -> None:
        """A role-guarded transition with no matching persona stubs + warns."""
        appspec = _app(
            "support",
            role_guarded_ticket_entity,
            personas=[PersonaSpec(id="customer", label="Customer", role="customer")],
        )

        with pytest.warns(UserWarning, match="role-guarded transition"):
            flows = generate_state_machine_flows(role_guarded_ticket_entity, appspec)

        stub = next((f for f in flows if "skip:no-persona" in f.tags), None)
        assert stub is not None
        assert stub.id == "Ticket_transition_open_to_in_progress_skipped_no_persona"
        assert stub.entity == "Ticket"
        assert stub.steps == []
        assert "state_machine" in stub.tags
        assert not any(f.id.endswith("_as_customer") for f in flows)


class TestComputedFieldFlowGeneration:
    """Tests for computed field verification flow generation."""

    def test_generate_computed_field_flows(self, invoice_entity_with_computed: EntitySpec) -> None:
        """Flow per computed field + COMPUTED_VALUE assertion."""
        app = _app("billing", invoice_entity_with_computed)
        flows = generate_computed_field_flows(invoice_entity_with_computed, app)
        assert len(flows) == 2

        item_count_flow = next((f for f in flows if "item_count" in f.id), None)
        assert item_count_flow is not None
        assert item_count_flow.entity == "Invoice"
        assert "computed" in item_count_flow.tags
        assert next((f for f in flows if "total" in f.id), None) is not None

        assert any(s.assertion.kind == FlowAssertionKind.COMPUTED_VALUE for s in _asserts(flows[0]))


class TestAccessControlFlowGeneration:
    """Tests for access control flow generation."""

    def test_generate_access_control_flows(self, document_entity_with_access: EntitySpec) -> None:
        """Allowed/denied pair structure + assertions."""
        app = _app("docs", document_entity_with_access)
        flows = generate_access_control_flows(document_entity_with_access, app)
        assert len(flows) >= 3  # at least one pair per operation

        allowed_flow = next((f for f in flows if "create_allowed" in f.id), None)
        assert allowed_flow is not None
        assert allowed_flow.priority == FlowPriority.HIGH
        assert allowed_flow.preconditions is not None
        assert allowed_flow.preconditions.authenticated is True
        assert "access_control" in allowed_flow.tags
        allowed_asserts = _asserts(allowed_flow)
        assert len(allowed_asserts) >= 1
        assert allowed_asserts[0].assertion.kind == FlowAssertionKind.PERMISSION_GRANTED

        denied_flow = next((f for f in flows if "_denied_anon" in f.id), None)
        assert denied_flow is not None
        assert denied_flow.preconditions is not None
        assert denied_flow.preconditions.authenticated is False
        assert "denied" in denied_flow.tags
        denied_asserts = _asserts(denied_flow)
        assert len(denied_asserts) >= 1
        assert denied_asserts[0].assertion.kind == FlowAssertionKind.PERMISSION_DENIED


class TestReferenceFlowGeneration:
    """Tests for reference integrity flow generation."""

    def test_generate_reference_flows(self, task_entity_with_ref: EntitySpec) -> None:
        """Valid/invalid pair, fixture refs, fake UUIDs."""
        project = _entity("Project", _req_str("name"))
        app = _app("projects", task_entity_with_ref, project)
        app.surfaces.append(
            SurfaceSpec(name="task_create", entity_ref="Task", mode=SurfaceMode.CREATE)
        )
        flows = generate_reference_flows(task_entity_with_ref, app)
        assert len(flows) == 2

        valid_flow = next((f for f in flows if "_valid" in f.id), None)
        assert valid_flow is not None
        assert valid_flow.entity == "Task"
        assert "reference" in valid_flow.tags
        assert "valid" in valid_flow.tags
        assert valid_flow.priority == FlowPriority.HIGH
        assert valid_flow.preconditions is not None
        assert "Project_valid" in valid_flow.preconditions.fixtures
        assert [s for s in valid_flow.steps if s.kind == FlowStepKind.FILL and s.fixture_ref]
        assert any(s.assertion.kind == FlowAssertionKind.REF_VALID for s in _asserts(valid_flow))

        invalid_flow = next((f for f in flows if "_invalid" in f.id), None)
        assert invalid_flow is not None
        assert "invalid" in invalid_flow.tags
        assert invalid_flow.priority == FlowPriority.MEDIUM
        assert [
            s
            for s in invalid_flow.steps
            if s.kind == FlowStepKind.FILL and s.value and "00000000" in s.value
        ]
        assert any(
            s.assertion.kind == FlowAssertionKind.REF_INVALID for s in _asserts(invalid_flow)
        )


@pytest.mark.parametrize(
    "generator",
    [
        generate_state_machine_flows,
        generate_computed_field_flows,
        generate_access_control_flows,
        generate_reference_flows,
    ],
    ids=["state_machine", "computed", "access_control", "reference"],
)
def test_no_flows_for_entity_without_feature(
    generator: Any, task_entity: EntitySpec, simple_appspec: AppSpec
) -> None:
    """A plain entity yields no state-machine/computed/access/ref flows."""
    assert generator(task_entity, simple_appspec) == []


class TestE2ETestSpecWithV013Features:
    """Tests for E2ETestSpec generation with v0.13.0 features."""

    def test_generate_testspec_with_all_features(self, full_featured_appspec: AppSpec) -> None:
        """Testspec includes all v0.13.0 flow types, all marked auto-generated."""
        testspec = generate_e2e_testspec(full_featured_appspec)

        for tag in ("state_machine", "computed", "access_control"):
            assert [f for f in testspec.flows if tag in f.tags], tag
        for flow in testspec.flows:
            assert flow.auto_generated is True, f"Flow {flow.id} should be auto-generated"
