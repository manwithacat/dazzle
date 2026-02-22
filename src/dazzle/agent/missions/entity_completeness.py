"""
Entity completeness mission: static CRUD coverage analysis + targeted verification.

Unlike the open-ended persona walkthrough, this mode:
1. Statically analyzes the DSL to find missing CRUD surfaces and state machine UI
2. Builds a focused mission that guides the agent to verify specific gaps

The static pre-pass is deterministic. The agent verification is non-deterministic
but bounded — it only checks what the static analysis flagged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from dazzle.core.patterns import SYSTEM_MANAGED_PATTERNS

from ..core import AgentTool, Mission
from ._shared import (
    build_dsl_summary,
    get_surface_entity,
    is_step_kind,
    make_observe_gap_tool,
    make_query_dsl_tool,
    make_stagnation_completion,
)

logger = logging.getLogger("dazzle.agent.missions.entity_completeness")


# =============================================================================
# Static Analysis Types
# =============================================================================


@dataclass
class EntityCoverageGap:
    """A gap in CRUD coverage or state machine UI for an entity."""

    entity_name: str
    gap_type: str  # "no_surface", "missing_list", "missing_create", "missing_edit", "missing_view", "no_transition_ui", "process_referenced"
    severity: str  # "critical", "high", "medium", "low"
    description: str
    process_name: str | None = None  # For process_referenced gaps


@dataclass
class EntityCompletenessReport:
    """Result of static entity completeness analysis."""

    gaps: list[EntityCoverageGap] = field(default_factory=list)
    entity_coverage: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def gap_count(self) -> int:
        return len(self.gaps)

    def to_summary(self) -> str:
        """Build a compact summary for embedding in system prompts."""
        if not self.gaps:
            return "No entity coverage gaps found."

        lines: list[str] = [f"Found {self.gap_count} entity coverage gaps:\n"]
        for gap in self.gaps:
            lines.append(f"- [{gap.severity.upper()}] {gap.entity_name}: {gap.description}")
        return "\n".join(lines)


# =============================================================================
# Static Analysis
# =============================================================================


def _is_system_managed(entity: Any) -> bool:
    """Check if an entity is system-managed (read-only) based on patterns or name.

    Wraps the patterns check with getattr safety so SimpleNamespace test fixtures
    (which lack .patterns) don't crash.
    """
    # Check explicit patterns
    entity_patterns = {p.lower() for p in getattr(entity, "patterns", [])}
    if entity_patterns & SYSTEM_MANAGED_PATTERNS:
        return True

    # Heuristic: check entity name for common system-managed patterns
    name_lower = getattr(entity, "name", "").lower()
    name_hints = ["log", "event", "audit", "notification", "history", "activity"]
    return any(hint in name_lower for hint in name_hints)


def _is_operation_forbidden(entity: Any, operation: str) -> bool:
    """Check if an entity has a blanket forbid rule for a given operation.

    Returns True when the entity's access spec contains a FORBID rule for the
    operation that applies to all personas (empty personas list).

    Args:
        entity: EntitySpec or SimpleNamespace with optional .access attribute
        operation: One of "create", "update", "delete"
    """
    access = getattr(entity, "access", None)
    if not access:
        return False
    permissions = getattr(access, "permissions", []) or []
    for rule in permissions:
        rule_op = str(getattr(rule, "operation", ""))
        rule_effect = str(getattr(rule, "effect", ""))
        rule_personas = getattr(rule, "personas", []) or []
        if (
            rule_op == operation
            and rule_effect in ("forbid", "FORBID", "PolicyEffect.FORBID")
            and not rule_personas
        ):
            return True
    return False


def _static_entity_analysis(appspec: Any) -> EntityCompletenessReport:
    """
    Analyze DSL spec for entity CRUD coverage gaps.

    Builds a map of entity -> {mode: [surface_names]} from surfaces,
    then checks each entity for completeness.
    """
    report = EntityCompletenessReport()

    entities = appspec.domain.entities
    surfaces = appspec.surfaces
    processes = appspec.processes

    # Build entity -> surface coverage map
    entity_surface_map: dict[str, dict[str, list[str]]] = {}
    for entity in entities:
        entity_surface_map[entity.name] = {}

    for surface in surfaces:
        entity_ref = get_surface_entity(surface)
        if not entity_ref or entity_ref not in entity_surface_map:
            continue
        mode = str(surface.mode)
        entity_surface_map[entity_ref].setdefault(mode, []).append(surface.name)

    # Track entities referenced by process human_task steps
    process_referenced_entities: dict[str, list[str]] = {}  # entity -> [process_names]
    for proc in processes:
        for step in proc.steps:
            if is_step_kind(step, "human_task"):
                human_task = step.human_task
                if human_task:
                    surface_name = human_task.surface
                    # Find entity for this surface
                    for s in surfaces:
                        if s.name == surface_name:
                            eref = get_surface_entity(s)
                            if eref:
                                process_referenced_entities.setdefault(eref, []).append(proc.name)

    # Check each entity
    for entity in entities:
        coverage = entity_surface_map.get(entity.name, {})
        has_any_surface = bool(coverage)
        is_sys = _is_system_managed(entity)

        # Store coverage info
        report.entity_coverage[entity.name] = {
            "list": bool(coverage.get("list")),
            "create": bool(coverage.get("create")),
            "edit": bool(coverage.get("edit")),
            "view": bool(coverage.get("view")),
            "surfaces": [s for modes in coverage.values() for s in modes],
            "is_system_managed": is_sys,
        }

        # Check: no surface at all
        if not has_any_surface:
            severity = "critical"
            if entity.name in process_referenced_entities:
                severity = "critical"
            report.gaps.append(
                EntityCoverageGap(
                    entity_name=entity.name,
                    gap_type="no_surface",
                    severity=severity,
                    description=f"Entity '{entity.name}' has no surfaces at all",
                )
            )
            continue

        # Check individual CRUD modes
        if not coverage.get("list"):
            report.gaps.append(
                EntityCoverageGap(
                    entity_name=entity.name,
                    gap_type="missing_list",
                    severity="high",
                    description=f"Entity '{entity.name}' has no list surface",
                )
            )

        # Skip create/edit gaps for system-managed entities or RBAC-forbidden ops
        skip_create = is_sys or _is_operation_forbidden(entity, "create")
        skip_edit = is_sys or _is_operation_forbidden(entity, "update")

        if not coverage.get("create") and not skip_create:
            report.gaps.append(
                EntityCoverageGap(
                    entity_name=entity.name,
                    gap_type="missing_create",
                    severity="high",
                    description=f"Entity '{entity.name}' has no create surface",
                )
            )

        if not coverage.get("edit") and not skip_edit:
            report.gaps.append(
                EntityCoverageGap(
                    entity_name=entity.name,
                    gap_type="missing_edit",
                    severity="medium",
                    description=f"Entity '{entity.name}' has no edit surface",
                )
            )

        if not coverage.get("view"):
            report.gaps.append(
                EntityCoverageGap(
                    entity_name=entity.name,
                    gap_type="missing_view",
                    severity="low",
                    description=f"Entity '{entity.name}' has no view surface",
                )
            )

        # Check state machine UI
        sm = entity.state_machine
        if sm and sm.transitions:
            # Check if any surface for this entity has actions (transition UI)
            has_transition_ui = False
            for surface in surfaces:
                if get_surface_entity(surface) == entity.name:
                    actions = surface.actions
                    if actions:
                        has_transition_ui = True
                        break
            if not has_transition_ui:
                report.gaps.append(
                    EntityCoverageGap(
                        entity_name=entity.name,
                        gap_type="no_transition_ui",
                        severity="medium",
                        description=f"Entity '{entity.name}' has state machine but no surface with transition actions",
                    )
                )

    # Check process-referenced entities with no surfaces
    for entity_name, proc_names in process_referenced_entities.items():
        if entity_name not in entity_surface_map or not entity_surface_map[entity_name]:
            # Already caught as no_surface above, but add process context
            report.gaps.append(
                EntityCoverageGap(
                    entity_name=entity_name,
                    gap_type="process_referenced",
                    severity="critical",
                    description=f"Entity '{entity_name}' referenced in process human_task but has no surfaces",
                    process_name=proc_names[0],
                )
            )

    return report


# =============================================================================
# Mission Tools
# =============================================================================


def _make_check_crud_coverage_tool(appspec: Any) -> AgentTool:
    """Tool: check_crud_coverage — returns CRUD coverage for an entity."""
    surfaces = appspec.surfaces

    def check_crud_coverage(entity_name: str = "") -> dict[str, Any]:
        if not entity_name:
            return {"error": "entity_name is required"}

        coverage: dict[str, list[str]] = {}
        for surface in surfaces:
            if get_surface_entity(surface) == entity_name:
                mode = str(surface.mode)
                coverage.setdefault(mode, []).append(surface.name)

        return {
            "entity": entity_name,
            "list": bool(coverage.get("list")),
            "create": bool(coverage.get("create")),
            "edit": bool(coverage.get("edit")),
            "view": bool(coverage.get("view")),
            "surfaces": [s for modes in coverage.values() for s in modes],
        }

    return AgentTool(
        name="check_crud_coverage",
        description=(
            "Check CRUD surface coverage for an entity. Returns which CRUD modes "
            "(list, create, edit, view) have surfaces and lists all surfaces for the entity."
        ),
        schema={
            "type": "object",
            "properties": {
                "entity_name": {
                    "type": "string",
                    "description": "Entity name to check coverage for",
                },
            },
            "required": ["entity_name"],
        },
        handler=check_crud_coverage,
    )


def _make_check_state_transitions_tool(appspec: Any) -> AgentTool:
    """Tool: check_state_transitions — returns state transitions with UI status."""
    entities = appspec.domain.entities
    surfaces = appspec.surfaces

    def check_state_transitions(entity_name: str = "") -> dict[str, Any]:
        if not entity_name:
            return {"error": "entity_name is required"}

        # Find entity
        entity = None
        for e in entities:
            if e.name == entity_name:
                entity = e
                break
        if entity is None:
            return {"error": f"Entity '{entity_name}' not found"}

        sm = entity.state_machine
        if not sm:
            return {"entity": entity_name, "has_state_machine": False, "transitions": []}

        # Check for surface actions
        entity_surface_actions: set[str] = set()
        for surface in surfaces:
            if get_surface_entity(surface) == entity_name:
                for action in surface.actions:
                    if action.name:
                        entity_surface_actions.add(action.name)

        transitions = []
        for t in sm.transitions:
            from_state = t.from_state
            to_state = t.to_state
            transitions.append(
                {
                    "from": from_state,
                    "to": to_state,
                    "has_ui": bool(entity_surface_actions),
                }
            )

        states = [s if isinstance(s, str) else s.name for s in sm.states]

        return {
            "entity": entity_name,
            "has_state_machine": True,
            "states": states,
            "transitions": transitions,
            "has_any_transition_ui": bool(entity_surface_actions),
        }

    return AgentTool(
        name="check_state_transitions",
        description=(
            "Check state machine transitions for an entity and whether they have UI. "
            "Returns transition list with from/to states and UI availability."
        ),
        schema={
            "type": "object",
            "properties": {
                "entity_name": {
                    "type": "string",
                    "description": "Entity name to check transitions for",
                },
            },
            "required": ["entity_name"],
        },
        handler=check_state_transitions,
    )


# =============================================================================
# System Prompt
# =============================================================================

ENTITY_COMPLETENESS_PROMPT = """You are an entity completeness verification agent for a Dazzle application.

Your mission is to verify CRUD coverage and state machine UI for entities in the DSL.
A static analysis has already identified potential gaps. Your job is to verify them
against the running application.

## Static Analysis Results
{gap_summary}

## DSL Specification Summary
{dsl_summary}

## Verification Strategy
1. **Review gaps**: Use `check_crud_coverage` for each flagged entity to confirm coverage
2. **Check state machines**: Use `check_state_transitions` for entities with state machines
3. **Verify in app**: Navigate to surfaces and check they actually work
4. **Record findings**: Use `observe_gap` for confirmed gaps with accurate severity
5. **Query DSL**: Use `query_dsl` to get field details when needed

## Severity Guidelines
- **critical**: Entity has no CRUD surfaces at all; process references missing surface
- **high**: Entity missing list or create surface; state machine has no transition UI
- **medium**: Entity missing edit surface; transition UI incomplete
- **low**: Entity missing dedicated view surface (often acceptable if list has detail)

## Output Format
Respond with ONLY a single JSON object for each action. No extra text."""


# =============================================================================
# Mission Builder
# =============================================================================


def build_entity_completeness_mission(
    appspec: Any,
    base_url: str = "http://localhost:3000",
    kg_store: Any | None = None,
    max_steps: int = 30,
    token_budget: int = 150_000,
) -> Mission:
    """
    Build a Mission for entity completeness verification.

    Runs static analysis first, then builds a focused mission to verify gaps.

    Args:
        appspec: Parsed AppSpec from the DSL
        base_url: Base URL of the running application
        kg_store: Optional KnowledgeGraphStore for adjacency checks
        max_steps: Maximum verification steps
        token_budget: Token budget for the LLM

    Returns:
        Mission configured for entity completeness verification
    """
    # Run static analysis
    report = _static_entity_analysis(appspec)

    # Build system prompt
    dsl_summary = build_dsl_summary(appspec)
    system_prompt = ENTITY_COMPLETENESS_PROMPT.format(
        gap_summary=report.to_summary(),
        dsl_summary=dsl_summary,
    )

    # Build tools
    tools = [
        make_observe_gap_tool(kg_store),
        make_query_dsl_tool(appspec),
        _make_check_crud_coverage_tool(appspec),
        _make_check_state_transitions_tool(appspec),
    ]

    return Mission(
        name="entity_completeness",
        system_prompt=system_prompt,
        tools=tools,
        completion_criteria=make_stagnation_completion(6, "Entity completeness"),
        max_steps=max_steps,
        token_budget=token_budget,
        start_url=base_url,
        context={
            "mode": "entity_completeness",
            "app_name": appspec.name,
            "static_analysis": {
                "gaps_found": report.gap_count,
                "entities_analyzed": len(report.entity_coverage),
            },
        },
    )
