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
from ._shared import (
    build_dsl_summary,
    get_surface_entity,
    make_observe_gap_tool,
    make_query_dsl_tool,
    make_stagnation_completion,
)

logger = logging.getLogger("dazzle.agent.missions.discovery")


# =============================================================================
# Persona Context
# =============================================================================


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
# Discovery-Specific Tools
# =============================================================================


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
            entity_ref = get_surface_entity(surface)
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
    dsl_summary = build_dsl_summary(appspec)

    system_prompt = DISCOVERY_SYSTEM_PROMPT.format(
        persona_context=persona_context,
        dsl_summary=dsl_summary,
    )

    # Build mission tools
    tools = [
        make_observe_gap_tool(kg_store),
        make_query_dsl_tool(appspec),
        _make_check_adjacency_tool(kg_store),
        _make_list_surfaces_tool(appspec),
    ]

    return Mission(
        name=f"discovery:{persona_name}",
        system_prompt=system_prompt,
        tools=tools,
        completion_criteria=make_stagnation_completion(8, "Discovery"),
        max_steps=max_steps,
        token_budget=token_budget,
        start_url=base_url,
        context={
            "persona": persona_name,
            "mode": "discovery",
            "app_name": appspec.name,
        },
    )
