"""
Discovery mission: explore a running Dazzle application and identify capability gaps.

The discovery agent navigates a live app as a given persona, comparing what it
finds against the DSL specification. It records structured observations about:
- Missing CRUD operations (entity exists in DSL but no surface for create/edit/delete)
- Workflow gaps (process steps reference surfaces that don't exist)
- Navigation gaps (workspaces define regions but links are missing)
- UX issues (forms missing validation, tables missing sort/filter)
- Persona access gaps (persona should access surface but can't)

This is a frontier-model-piloted system. Non-deterministic by design.
The quality of discovery depends on the model's reasoning capability and
the richness of the DSL specification.
"""

from __future__ import annotations

import logging
from typing import Any

from ..core import AgentTool, Mission
from ..models import ActionType, AgentAction, Step

logger = logging.getLogger("dazzle.agent.missions.discovery")


# =============================================================================
# DSL Summary Builder
# =============================================================================


def _build_dsl_summary(appspec: Any) -> str:
    """
    Build a compact DSL summary for the system prompt.

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
        # Note state machine if present
        sm = getattr(entity, "state_machine", None)
        if sm and getattr(sm, "states", None):
            state_names = [s if isinstance(s, str) else s.name for s in sm.states][:6]
            lines.append(f"  States: {' → '.join(state_names)}")

    # Surfaces with mode and entity
    lines.append("\n### Surfaces")
    for surface in appspec.surfaces[:40]:
        entity_ref = ""
        if hasattr(surface, "entity") and surface.entity:
            entity_ref = f" → {surface.entity}"
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

    # Processes (brief)
    processes = getattr(appspec, "processes", [])
    if processes:
        lines.append("\n### Processes")
        for proc in processes[:10]:
            step_count = len(getattr(proc, "steps", []))
            lines.append(f"- **{proc.name}**: {step_count} steps")

    # Experiences (brief)
    if appspec.experiences:
        lines.append("\n### Experiences")
        for exp in appspec.experiences[:10]:
            step_count = len(getattr(exp, "steps", []))
            lines.append(f"- **{exp.name}** ({exp.title or exp.name}): {step_count} steps")

    return "\n".join(lines)


def _build_persona_context(
    persona_name: str,
    capability_map: dict[str, list[Any]] | None,
) -> str:
    """Build persona context for the system prompt."""
    lines = [f"You are exploring as persona **{persona_name}**."]

    if capability_map:
        ws_names = [e.name for e in capability_map.get("workspaces", [])]
        surface_names = [e.name for e in capability_map.get("surfaces", [])][:15]
        entity_names = [e.name for e in capability_map.get("entities", [])][:15]

        if ws_names:
            lines.append(f"Accessible workspaces: {', '.join(ws_names)}")
        if surface_names:
            lines.append(f"Expected surfaces: {', '.join(surface_names)}")
        if entity_names:
            lines.append(f"Related entities: {', '.join(entity_names)}")
    else:
        lines.append("No capability map available — explore freely.")

    return "\n".join(lines)


# =============================================================================
# Helpers
# =============================================================================


def _auto_prefix(kg_store: Any, node_id: str, known_prefixes: tuple[str, ...]) -> str:
    """Auto-prefix a node ID if it doesn't already have a known prefix."""
    if not node_id or any(node_id.startswith(p) for p in known_prefixes):
        return node_id
    for try_prefix in ("entity:", "surface:"):
        if kg_store.get_entity(try_prefix + node_id):
            return try_prefix + node_id
    return node_id


# =============================================================================
# Discovery Tools
# =============================================================================


def _make_observe_gap_tool(
    kg_store: Any | None,
) -> AgentTool:
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
        # Validate severity
        valid_severities = {"critical", "high", "medium", "low", "info"}
        if severity not in valid_severities:
            severity = "medium"

        # Validate category
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

        # If we have a KG, try adjacency check
        if kg_store and related_entities:
            adjacency_notes: list[str] = []
            for entity_id in related_entities[:3]:
                # Prefix if not already prefixed
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


def _make_query_dsl_tool(
    appspec: Any,
) -> AgentTool:
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
            # Find entity
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
                        "entity": getattr(surface, "entity", None),
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


def _make_check_adjacency_tool(
    kg_store: Any | None,
) -> AgentTool:
    """
    Tool: check_adjacency — verify a proposed feature is within the 2-step boundary.

    This helps the agent stay grounded: don't propose features that are unrelated
    to existing DSL artefacts.
    """

    def check_adjacency(
        node_a: str = "",
        node_b: str = "",
    ) -> dict[str, Any]:
        if not kg_store:
            return {"distance": -1, "note": "No knowledge graph available"}

        # Auto-prefix if needed
        _known_prefixes = (
            "entity:",
            "surface:",
            "persona:",
            "workspace:",
            "process:",
            "story:",
            "experience:",
            "service:",
        )
        node_a = _auto_prefix(kg_store, node_a, _known_prefixes)
        node_b = _auto_prefix(kg_store, node_b, _known_prefixes)

        distance = kg_store.compute_adjacency(node_a, node_b)
        return {
            "node_a": node_a,
            "node_b": node_b,
            "distance": distance,
            "within_boundary": distance >= 0 and distance <= 2,
        }

    return AgentTool(
        name="check_adjacency",
        description=(
            "Check the distance between two DSL artefacts in the knowledge graph. "
            "Proposed features should be within 2 steps of existing artefacts. "
            "Returns distance (0=same, 1=direct edge, 2=two hops, -1=unreachable)."
        ),
        schema={
            "type": "object",
            "properties": {
                "node_a": {
                    "type": "string",
                    "description": "First node ID (e.g. 'entity:Task' or just 'Task')",
                },
                "node_b": {
                    "type": "string",
                    "description": "Second node ID (e.g. 'surface:task_list')",
                },
            },
            "required": ["node_a", "node_b"],
        },
        handler=check_adjacency,
    )


def _make_list_surfaces_tool(
    appspec: Any,
) -> AgentTool:
    """
    Tool: list_surfaces — get all surface URLs the agent should visit.

    Helps the agent systematically cover the app.
    """

    def list_surfaces(
        entity_filter: str | None = None,
    ) -> dict[str, Any]:
        surfaces: list[dict[str, str]] = []
        for surface in appspec.surfaces:
            entity_ref = getattr(surface, "entity", None)
            if entity_filter and entity_ref != entity_filter:
                continue
            mode = getattr(surface, "mode", "unknown")
            surfaces.append(
                {
                    "name": surface.name,
                    "title": surface.title,
                    "mode": mode,
                    "entity": entity_ref or "",
                    "url_hint": f"/{surface.name.replace('_', '-')}",
                }
            )
        return {
            "total": len(surfaces),
            "surfaces": surfaces[:50],
        }

    return AgentTool(
        name="list_surfaces",
        description=(
            "List all surfaces defined in the DSL. Optionally filter by entity name. "
            "Use this to plan which pages to visit."
        ),
        schema={
            "type": "object",
            "properties": {
                "entity_filter": {
                    "type": "string",
                    "description": "Only show surfaces for this entity",
                },
            },
        },
        handler=list_surfaces,
    )


# =============================================================================
# Completion Criteria
# =============================================================================


def _discovery_completion(action: AgentAction, history: list[Step]) -> bool:
    """
    Discovery is complete when:
    1. Agent says DONE, or
    2. No new observations in last 5 steps (stagnation detection)
    """
    if action.type == ActionType.DONE:
        return True

    # Stagnation: if we've had 8+ steps with no tool invocations recently
    if len(history) >= 8:
        recent = history[-8:]
        tool_calls = sum(1 for s in recent if s.action.type == ActionType.TOOL)
        if tool_calls == 0:
            logger.info("Discovery stagnation detected: no tool calls in last 8 steps")
            return True

    return False


# =============================================================================
# Mission Builder
# =============================================================================


DISCOVERY_SYSTEM_PROMPT = """You are a capability discovery agent for a Dazzle application.

Your mission is to systematically explore a running web application and identify gaps between
what the DSL specification defines and what the application actually implements.

## Your Persona
{persona_context}

## DSL Specification Summary
{dsl_summary}

## Discovery Strategy
1. **Start with navigation**: Visit the main workspace/dashboard to understand the app structure
2. **Systematic surface coverage**: Use `list_surfaces` to get all expected surfaces, then visit each
3. **Per-surface analysis**: On each surface, check:
   - Does the page render? (navigation_gap if 404 or blank)
   - Does it show the right entity data? (data_gap)
   - Can you create/edit/delete records? (missing_crud)
   - Are form fields present and validated? (ux_issue)
   - Are expected workflow actions available? (workflow_gap)
   - Can this persona access it? (access_gap if denied but should be allowed)
4. **Use tools actively**: Call `observe_gap` for every issue found. Call `query_dsl` to check details.
5. **Stay grounded**: Use `check_adjacency` before proposing features — stay within 2 hops.

## Observation Guidelines
- **critical**: Core entity has no CRUD surface at all; key workflow is completely missing
- **high**: Create/edit exists but delete doesn't; workflow step skips a required surface
- **medium**: Surface exists but missing expected fields; form lacks validation
- **low**: Minor UX issues; optional fields missing
- **info**: Surface works as expected (positive confirmation)

## What NOT to report
- Don't report issues about styling, layout, or visual design
- Don't report about login/auth unless the persona can't access expected surfaces
- Don't report about performance or loading times

## Output Format
Respond with ONLY a single JSON object for each action. No extra text."""


def build_discovery_mission(
    appspec: Any,
    persona_name: str = "admin",
    base_url: str = "http://localhost:3000",
    kg_store: Any | None = None,
    max_steps: int = 50,
    token_budget: int = 200_000,
) -> Mission:
    """
    Build a Mission for capability discovery.

    Args:
        appspec: Parsed AppSpec from the DSL
        persona_name: Persona to explore as
        base_url: Base URL of the running application
        kg_store: Optional KnowledgeGraphStore for adjacency checks
        max_steps: Maximum exploration steps
        token_budget: Token budget for the LLM

    Returns:
        Mission configured for capability discovery
    """
    # Build persona context
    capability_map = None
    if kg_store:
        try:
            capability_map = kg_store.persona_capability_map(persona_name)
        except Exception as e:
            logger.warning(f"Could not get capability map for {persona_name}: {e}")

    persona_context = _build_persona_context(persona_name, capability_map)
    dsl_summary = _build_dsl_summary(appspec)

    system_prompt = DISCOVERY_SYSTEM_PROMPT.format(
        persona_context=persona_context,
        dsl_summary=dsl_summary,
    )

    # Build mission tools
    tools = [
        _make_observe_gap_tool(kg_store),
        _make_query_dsl_tool(appspec),
        _make_check_adjacency_tool(kg_store),
        _make_list_surfaces_tool(appspec),
    ]

    return Mission(
        name=f"discovery:{persona_name}",
        system_prompt=system_prompt,
        tools=tools,
        completion_criteria=_discovery_completion,
        max_steps=max_steps,
        token_budget=token_budget,
        start_url=base_url,
        context={
            "persona": persona_name,
            "mode": "discovery",
            "app_name": appspec.name,
        },
    )
