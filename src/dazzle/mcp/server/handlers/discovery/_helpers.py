"""Shared helpers for discovery handler sub-modules."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from dazzle.mcp.server.paths import project_discovery_dir, project_kg_db

logger = logging.getLogger("dazzle.mcp.handlers.discovery")


def _load_appspec(project_path: Path) -> Any:
    """Load and return AppSpec from a project directory."""
    from ..common import load_project_appspec

    return load_project_appspec(project_path)


def _populate_kg_for_discovery(
    project_path: Path,
) -> Any | None:
    """Populate the knowledge graph with DSL artefacts. Returns the KG store or None."""
    try:
        from dazzle.mcp.knowledge_graph import KnowledgeGraphHandlers
        from dazzle.mcp.knowledge_graph.store import KnowledgeGraph

        db_path = project_kg_db(project_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        kg = KnowledgeGraph(str(db_path))
        handlers = KnowledgeGraphHandlers(kg)
        handlers.handle_populate_from_appspec(str(project_path))
        return kg
    except Exception as e:
        logger.warning(f"Could not populate knowledge graph: {e}")
        return None


def _build_mission_summary(
    mission: Any, mode: str, appspec: Any, kg_store: Any, base_url: str, persona: str | None = None
) -> dict[str, Any]:
    """Build a structured summary of a mission for the response."""
    tool_summaries = []
    for tool in mission.tools:
        tool_summaries.append(
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": list(tool.schema.get("properties", {}).keys()),
            }
        )

    entity_count = len(appspec.domain.entities) if hasattr(appspec.domain, "entities") else 0
    surface_count = len(appspec.surfaces)
    persona_count = len(appspec.personas)
    workspace_count = len(appspec.workspaces)

    result: dict[str, Any] = {
        "status": "ready",
        "mode": mode,
        "mission": {
            "name": mission.name,
            "base_url": base_url,
            "max_steps": mission.max_steps,
            "token_budget": mission.token_budget,
            "tools": tool_summaries,
        },
        "dsl_summary": {
            "entities": entity_count,
            "surfaces": surface_count,
            "personas": persona_count,
            "workspaces": workspace_count,
        },
        "kg_available": kg_store is not None,
        "system_prompt_length": len(mission.system_prompt),
    }

    if persona:
        result["mission"]["persona"] = persona

    # Add static analysis info if present
    static_analysis = mission.context.get("static_analysis")
    if static_analysis:
        result["static_analysis"] = static_analysis

    return result


async def _get_persona_session_info(
    project_path: Path, persona: str, base_url: str
) -> dict[str, Any]:
    """Load or create a persona session, returning session metadata for the response."""
    try:
        from dazzle.testing.session_manager import SessionManager

        manager = SessionManager(project_path, base_url=base_url)
        session = manager.load_session(persona)
        if session and session.session_token:
            return {
                "authenticated": True,
                "persona": persona,
                "session_source": "stored",
                "cookie": {"dazzle_session": session.session_token},
            }
        # Try to create a session
        await manager.create_session(persona)
        session = manager.load_session(persona)
        if session and session.session_token:
            return {
                "authenticated": True,
                "persona": persona,
                "session_source": "created",
                "cookie": {"dazzle_session": session.session_token},
            }
    except Exception as e:
        logger.debug("Could not load/create persona session: %s", e)
    return {"authenticated": False, "persona": persona}


def save_discovery_report(project_path: Path, transcript_json: dict[str, Any]) -> Path:
    """
    Save a discovery transcript as a report file.

    Called programmatically after agent.run() completes.
    Returns the path to the saved report.
    """
    report_dir = project_discovery_dir(project_path)
    report_dir.mkdir(parents=True, exist_ok=True)

    session_id = f"discovery_{int(time.time())}"
    report_file = report_dir / f"{session_id}.json"
    report_file.write_text(json.dumps(transcript_json, indent=2))

    return report_file
