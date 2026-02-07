"""
Shared utilities for discovery missions.

Contains helpers used across discovery, entity_completeness, and
workflow_coherence missions to avoid cross-module private-function
imports and code duplication.
"""

from __future__ import annotations

import logging
from typing import Any

from ..core import AgentTool
from ..models import ActionType, AgentAction, Step

logger = logging.getLogger("dazzle.agent.missions")


# =============================================================================
# IR Access Helpers
# =============================================================================


def get_surface_entity(surface: Any) -> str | None:
    """Get the entity reference from a surface, handling both IR and test mocks."""
    return getattr(surface, "entity_ref", None) or getattr(surface, "entity", None)


def is_step_kind(step: Any, kind_name: str) -> bool:
    """
    Check if a process step matches a given kind name.

    Handles both StrEnum values (StepKind.HUMAN_TASK) and plain strings
    ("human_task") as used in test mocks.
    """
    kind = getattr(step, "kind", None)
    if kind is None:
        return False
    kind_str = str(kind)
    return kind_str == kind_name or kind_str == f"StepKind.{kind_name.upper()}"


def is_trigger_kind(trigger: Any, kind_name: str) -> bool:
    """
    Check if a process trigger matches a given kind name.

    Handles both StrEnum values and plain strings.
    """
    trigger_kind = getattr(trigger, "kind", None)
    if trigger_kind is None:
        return False
    kind_str = str(trigger_kind)
    return kind_str == kind_name or kind_str == f"ProcessTriggerKind.{kind_name.upper()}"


# =============================================================================
# Completion Criteria Factory
# =============================================================================


def make_stagnation_completion(
    window: int,
    label: str = "mission",
) -> Any:
    """
    Create a completion function that triggers on DONE or stagnation.

    Args:
        window: Number of consecutive steps without tool calls before stopping
        label: Label for log messages
    """

    def completion(action: AgentAction, history: list[Step]) -> bool:
        if action.type == ActionType.DONE:
            return True
        if len(history) >= window:
            recent = history[-window:]
            tool_calls = sum(1 for s in recent if s.action.type == ActionType.TOOL)
            if tool_calls == 0:
                logger.info(f"{label} stagnation: no tool calls in last {window} steps")
                return True
        return False

    return completion


# =============================================================================
# DSL Summary Builder
# =============================================================================


def build_dsl_summary(appspec: Any) -> str:
    """
    Build a compact DSL summary for system prompts.

    Targets ~2-4k tokens. Gives the agent enough context to recognize
    what should exist without overwhelming it.
    """
    lines: list[str] = []

    # Entities with key fields
    lines.append("### Entities")
    entities = appspec.domain.entities if hasattr(appspec.domain, "entities") else []
    for entity in entities:
        field_names = [f.name for f in getattr(entity, "fields", [])][:8]
        lines.append(f"- **{entity.name}** ({entity.title}): {', '.join(field_names)}")
        sm = getattr(entity, "state_machine", None)
        if sm and getattr(sm, "states", None):
            state_names = [s if isinstance(s, str) else s.name for s in sm.states][:6]
            lines.append(f"  States: {' → '.join(state_names)}")

    # Surfaces with mode and entity
    lines.append("\n### Surfaces")
    for surface in appspec.surfaces[:40]:
        entity_ref = get_surface_entity(surface) or ""
        if entity_ref:
            entity_ref = f" → {entity_ref}"
        mode = getattr(surface, "mode", "unknown")
        lines.append(f"- **{surface.name}** ({mode}{entity_ref}): {surface.title or surface.name}")

    # Workspaces
    if appspec.workspaces:
        lines.append("\n### Workspaces")
        for ws in appspec.workspaces[:15]:
            regions = getattr(ws, "regions", [])
            region_names = [r.name for r in regions][:5]
            lines.append(f"- **{ws.name}**: regions=[{', '.join(region_names)}]")

    # Personas
    if appspec.personas:
        lines.append("\n### Personas")
        for p in appspec.personas[:10]:
            p_name = getattr(p, "name", None) or getattr(p, "id", "unknown")
            desc = getattr(p, "description", "")[:60]
            lines.append(f"- **{p_name}**: {desc}")

    # Processes
    processes = getattr(appspec, "processes", [])
    if processes:
        lines.append("\n### Processes")
        for proc in processes[:10]:
            step_count = len(getattr(proc, "steps", []))
            lines.append(f"- **{proc.name}**: {step_count} steps")

    # Experiences
    if appspec.experiences:
        lines.append("\n### Experiences")
        for exp in appspec.experiences[:10]:
            step_count = len(getattr(exp, "steps", []))
            lines.append(f"- **{exp.name}** ({exp.title or exp.name}): {step_count} steps")

    return "\n".join(lines)


# =============================================================================
# Shared Mission Tools
# =============================================================================


def make_observe_gap_tool(kg_store: Any | None) -> AgentTool:
    """
    Tool: observe_gap — record a capability gap.

    Returns an Observation dict that the agent core will add to the transcript.
    """

    def observe_gap(
        category: str = "gap",
        severity: str = "medium",
        title: str = "",
        description: str = "",
        location: str = "",
        related_entities: list[str] | None = None,
    ) -> dict[str, Any]:
        valid_severities = {"critical", "high", "medium", "low", "info"}
        if severity not in valid_severities:
            severity = "medium"

        valid_categories = {
            "missing_crud",
            "workflow_gap",
            "navigation_gap",
            "ux_issue",
            "access_gap",
            "data_gap",
            "gap",
        }
        if category not in valid_categories:
            category = "gap"

        obs: dict[str, Any] = {
            "category": category,
            "severity": severity,
            "title": title,
            "description": description,
            "location": location,
            "related_artefacts": related_entities or [],
        }

        if kg_store and related_entities:
            adjacency_notes: list[str] = []
            for entity_id in related_entities[:3]:
                if ":" not in entity_id:
                    entity_id = f"entity:{entity_id}"
                ent = kg_store.get_entity(entity_id)
                if ent:
                    adjacency_notes.append(f"{entity_id} exists in KG")
                else:
                    adjacency_notes.append(f"{entity_id} NOT in KG")
            obs["metadata"] = {"adjacency": adjacency_notes}

        return {"observation": obs, "recorded": True}

    return AgentTool(
        name="observe_gap",
        description=(
            "Record a capability gap or finding. Categories: missing_crud, workflow_gap, "
            "navigation_gap, ux_issue, access_gap, data_gap, gap. "
            "Severities: critical, high, medium, low, info."
        ),
        schema={
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": [
                        "missing_crud",
                        "workflow_gap",
                        "navigation_gap",
                        "ux_issue",
                        "access_gap",
                        "data_gap",
                        "gap",
                    ],
                },
                "severity": {
                    "type": "string",
                    "enum": ["critical", "high", "medium", "low", "info"],
                },
                "title": {"type": "string", "description": "Short title for the gap"},
                "description": {
                    "type": "string",
                    "description": "What's missing and why it matters",
                },
                "location": {
                    "type": "string",
                    "description": "URL or surface name where observed",
                },
                "related_entities": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "DSL entity/surface names related to this gap",
                },
            },
            "required": ["title", "description"],
        },
        handler=observe_gap,
    )


def make_query_dsl_tool(appspec: Any) -> AgentTool:
    """
    Tool: query_dsl — ask about DSL definitions on-demand.

    Lazy context loading: the agent can pull in more DSL detail as needed
    without it all being in the system prompt.
    """

    def query_dsl(
        entity_name: str | None = None,
        surface_name: str | None = None,
        query_type: str = "fields",
    ) -> dict[str, Any]:
        if entity_name:
            for entity in appspec.domain.entities:
                if entity.name == entity_name:
                    result: dict[str, Any] = {
                        "name": entity.name,
                        "title": entity.title,
                        "fields": [],
                    }
                    for f in getattr(entity, "fields", []):
                        field_info: dict[str, str] = {"name": f.name, "type": str(f.type)}
                        if hasattr(f, "constraints"):
                            field_info["constraints"] = str(f.constraints)
                        result["fields"].append(field_info)
                    sm = getattr(entity, "state_machine", None)
                    if sm and getattr(sm, "states", None):
                        result["states"] = [s if isinstance(s, str) else s.name for s in sm.states]
                        result["transitions"] = [
                            {"from": t.from_state, "to": t.to_state, "event": t.event}
                            for t in getattr(sm, "transitions", [])
                        ]
                    return result
            return {"error": f"Entity '{entity_name}' not found"}

        if surface_name:
            for surface in appspec.surfaces:
                if surface.name == surface_name:
                    result = {
                        "name": surface.name,
                        "title": surface.title,
                        "mode": getattr(surface, "mode", "unknown"),
                        "entity": get_surface_entity(surface),
                    }
                    sections = getattr(surface, "sections", [])
                    if sections:
                        result["sections"] = []
                        for sec in sections:
                            sec_info: dict[str, Any] = {"name": sec.name}
                            fields = getattr(sec, "fields", [])
                            sec_info["fields"] = [f.name for f in fields][:10]
                            result["sections"].append(sec_info)
                    return result
            return {"error": f"Surface '{surface_name}' not found"}

        return {"error": "Provide entity_name or surface_name"}

    return AgentTool(
        name="query_dsl",
        description=(
            "Look up DSL definition details for an entity or surface. "
            "Use this to get field lists, state machines, surface sections, etc."
        ),
        schema={
            "type": "object",
            "properties": {
                "entity_name": {
                    "type": "string",
                    "description": "Entity name to look up",
                },
                "surface_name": {
                    "type": "string",
                    "description": "Surface name to look up",
                },
                "query_type": {
                    "type": "string",
                    "enum": ["fields", "states", "sections"],
                    "description": "What aspect to query",
                },
            },
        },
        handler=query_dsl,
    )
