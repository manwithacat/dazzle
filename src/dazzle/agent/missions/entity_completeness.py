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

from ..core import AgentTool, Mission
from ..models import ActionType, AgentAction, Step

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


def _static_entity_analysis(appspec: Any) -> EntityCompletenessReport:
    """
    Analyze DSL spec for entity CRUD coverage gaps.

    Builds a map of entity -> {mode: [surface_names]} from surfaces,
    then checks each entity for completeness.
    """
    report = EntityCompletenessReport()

    entities = getattr(getattr(appspec, "domain", None), "entities", []) or []
    surfaces = getattr(appspec, "surfaces", []) or []
    processes = getattr(appspec, "processes", []) or []

    # Build entity -> surface coverage map
    entity_surface_map: dict[str, dict[str, list[str]]] = {}
    for entity in entities:
        entity_surface_map[entity.name] = {}

    for surface in surfaces:
        entity_ref = getattr(surface, "entity_ref", None) or getattr(surface, "entity", None)
        if not entity_ref or entity_ref not in entity_surface_map:
            continue
        mode = str(getattr(surface, "mode", "unknown"))
        entity_surface_map[entity_ref].setdefault(mode, []).append(surface.name)

    # Track entities referenced by process human_task steps
    process_referenced_entities: dict[str, list[str]] = {}  # entity -> [process_names]
    for proc in processes:
        for step in getattr(proc, "steps", []):
            kind = getattr(step, "kind", None)
            kind_str = str(kind) if kind is not None else ""
            if kind_str == "human_task" or kind_str == "StepKind.HUMAN_TASK":
                human_task = getattr(step, "human_task", None)
                if human_task:
                    surface_name = getattr(human_task, "surface", None)
                    # Find entity for this surface
                    for s in surfaces:
                        if s.name == surface_name:
                            eref = getattr(s, "entity_ref", None) or getattr(s, "entity", None)
                            if eref:
                                process_referenced_entities.setdefault(eref, []).append(proc.name)

    # Check each entity
    for entity in entities:
        coverage = entity_surface_map.get(entity.name, {})
        has_any_surface = bool(coverage)

        # Store coverage info
        report.entity_coverage[entity.name] = {
            "list": bool(coverage.get("list")),
            "create": bool(coverage.get("create")),
            "edit": bool(coverage.get("edit")),
            "view": bool(coverage.get("view")),
            "surfaces": [s for modes in coverage.values() for s in modes],
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

        if not coverage.get("create"):
            report.gaps.append(
                EntityCoverageGap(
                    entity_name=entity.name,
                    gap_type="missing_create",
                    severity="high",
                    description=f"Entity '{entity.name}' has no create surface",
                )
            )

        if not coverage.get("edit"):
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
        sm = getattr(entity, "state_machine", None)
        if sm and getattr(sm, "transitions", None):
            # Check if any surface for this entity has actions (transition UI)
            has_transition_ui = False
            for surface in surfaces:
                eref = getattr(surface, "entity_ref", None) or getattr(surface, "entity", None)
                if eref == entity.name:
                    actions = getattr(surface, "actions", [])
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
    surfaces = getattr(appspec, "surfaces", []) or []

    def check_crud_coverage(entity_name: str = "") -> dict[str, Any]:
        if not entity_name:
            return {"error": "entity_name is required"}

        coverage: dict[str, list[str]] = {}
        for surface in surfaces:
            eref = getattr(surface, "entity_ref", None) or getattr(surface, "entity", None)
            if eref == entity_name:
                mode = str(getattr(surface, "mode", "unknown"))
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
    entities = getattr(getattr(appspec, "domain", None), "entities", []) or []
    surfaces = getattr(appspec, "surfaces", []) or []

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

        sm = getattr(entity, "state_machine", None)
        if not sm:
            return {"entity": entity_name, "has_state_machine": False, "transitions": []}

        # Check for surface actions
        entity_surface_actions: set[str] = set()
        for surface in surfaces:
            eref = getattr(surface, "entity_ref", None) or getattr(surface, "entity", None)
            if eref == entity_name:
                for action in getattr(surface, "actions", []):
                    action_name = getattr(action, "name", "")
                    if action_name:
                        entity_surface_actions.add(action_name)

        transitions = []
        for t in getattr(sm, "transitions", []):
            from_state = getattr(t, "from_state", "?")
            to_state = getattr(t, "to_state", "?")
            transitions.append(
                {
                    "from": from_state,
                    "to": to_state,
                    "has_ui": bool(entity_surface_actions),
                }
            )

        states = [s if isinstance(s, str) else s.name for s in getattr(sm, "states", [])]

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
# Completion Criteria
# =============================================================================


def _entity_completeness_completion(action: AgentAction, history: list[Step]) -> bool:
    """Complete on DONE or 6-step stagnation (shorter than persona mode)."""
    if action.type == ActionType.DONE:
        return True

    if len(history) >= 6:
        recent = history[-6:]
        tool_calls = sum(1 for s in recent if s.action.type == ActionType.TOOL)
        if tool_calls == 0:
            logger.info("Entity completeness stagnation: no tool calls in last 6 steps")
            return True

    return False


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
    from .discovery import _build_dsl_summary, _make_observe_gap_tool, _make_query_dsl_tool

    # Run static analysis
    report = _static_entity_analysis(appspec)

    # Build system prompt
    dsl_summary = _build_dsl_summary(appspec)
    system_prompt = ENTITY_COMPLETENESS_PROMPT.format(
        gap_summary=report.to_summary(),
        dsl_summary=dsl_summary,
    )

    # Build tools
    tools = [
        _make_observe_gap_tool(kg_store),
        _make_query_dsl_tool(appspec),
        _make_check_crud_coverage_tool(appspec),
        _make_check_state_transitions_tool(appspec),
    ]

    return Mission(
        name="entity_completeness",
        system_prompt=system_prompt,
        tools=tools,
        completion_criteria=_entity_completeness_completion,
        max_steps=max_steps,
        token_budget=token_budget,
        start_url=base_url,
        context={
            "mode": "entity_completeness",
            "app_name": getattr(appspec, "name", "unknown"),
            "static_analysis": {
                "gaps_found": report.gap_count,
                "entities_analyzed": len(report.entity_coverage),
            },
        },
    )
