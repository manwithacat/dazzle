"""
MCP handler for capability discovery operations.

Operations:
  run     — Start a discovery session (async, returns session ID)
  report  — Get the discovery report from a completed session
  compile — Compile observations into prioritized proposals
  emit    — Generate valid DSL code from compiled proposals
  status  — Check status of a running/completed session
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("dazzle.mcp.handlers.discovery")


def _load_appspec(project_path: Path) -> Any:
    """Load and return AppSpec from a project directory."""
    from dazzle.core.fileset import discover_dsl_files
    from dazzle.core.linker import build_appspec
    from dazzle.core.manifest import load_manifest
    from dazzle.core.parser import parse_modules

    manifest = load_manifest(project_path / "dazzle.toml")
    dsl_files = discover_dsl_files(project_path, manifest)
    modules = parse_modules(dsl_files)
    return build_appspec(modules, manifest.project_root)


def _populate_kg_for_discovery(
    project_path: Path,
) -> Any | None:
    """Populate the knowledge graph with DSL artefacts. Returns the KG store or None."""
    try:
        from dazzle.mcp.knowledge_graph import KnowledgeGraphHandlers
        from dazzle.mcp.knowledge_graph.store import KnowledgeGraph

        db_path = project_path / ".dazzle" / "knowledge_graph.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        kg = KnowledgeGraph(str(db_path))
        handlers = KnowledgeGraphHandlers(kg)
        handlers.handle_populate_from_appspec(str(project_path))
        return kg
    except Exception as e:
        logger.warning(f"Could not populate knowledge graph: {e}")
        return None


def run_discovery_handler(project_path: Path, args: dict[str, Any]) -> str:
    """
    Build and describe a discovery mission (non-executing).

    Since the discovery agent requires a live application and an LLM API key,
    this handler builds the mission configuration and returns it as a structured
    report. The actual agent execution happens via `dazzle discover` CLI or
    programmatic API.

    Returns the mission spec including system prompt, tools, and DSL summary
    so the caller can inspect or run it.
    """
    from dazzle.agent.missions.discovery import build_discovery_mission

    persona = args.get("persona", "admin")
    base_url = args.get("base_url", "http://localhost:3000")
    max_steps = args.get("max_steps", 50)
    token_budget = args.get("token_budget", 200_000)

    try:
        appspec = _load_appspec(project_path)
    except Exception as e:
        return json.dumps({"error": f"Failed to load DSL: {e}"}, indent=2)

    # Optionally populate KG for adjacency features
    kg_store = _populate_kg_for_discovery(project_path)

    mission = build_discovery_mission(
        appspec=appspec,
        persona_name=persona,
        base_url=base_url,
        kg_store=kg_store,
        max_steps=max_steps,
        token_budget=token_budget,
    )

    # Build a summary of the mission (don't include full system prompt — too large)
    tool_summaries = []
    for tool in mission.tools:
        tool_summaries.append(
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": list(tool.schema.get("properties", {}).keys()),
            }
        )

    # Count DSL artefacts for the summary
    entity_count = len(appspec.domain.entities) if hasattr(appspec.domain, "entities") else 0
    surface_count = len(appspec.surfaces)
    persona_count = len(appspec.personas)
    workspace_count = len(appspec.workspaces)

    result: dict[str, Any] = {
        "status": "ready",
        "mission": {
            "name": mission.name,
            "persona": persona,
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
        "instructions": (
            "Mission is ready. To execute, run the discovery agent against a live app:\n"
            f"  dazzle discover --persona {persona} --url {base_url}\n"
            "Or programmatically:\n"
            "  from dazzle.agent import DazzleAgent\n"
            "  from dazzle.agent.observer import HttpObserver\n"
            "  from dazzle.agent.executor import HttpExecutor\n"
            "  agent = DazzleAgent(observer, executor)\n"
            "  transcript = await agent.run(mission)"
        ),
    }

    return json.dumps(result, indent=2)


def get_discovery_report_handler(project_path: Path, args: dict[str, Any]) -> str:
    """
    Get the latest discovery report from a project.

    Reports are stored in .dazzle/discovery/ as JSON files.
    """
    report_dir = project_path / ".dazzle" / "discovery"
    session_id = args.get("session_id")

    if session_id:
        report_file = report_dir / f"{session_id}.json"
        if not report_file.exists():
            return json.dumps({"error": f"Report not found: {session_id}"})
        return report_file.read_text()

    # Get the most recent report
    if not report_dir.exists():
        return json.dumps(
            {
                "error": "No discovery reports found",
                "hint": "Run a discovery session first with operation: run",
            }
        )

    reports = sorted(report_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not reports:
        return json.dumps({"error": "No discovery reports found"})

    # Return summary of available reports
    report_summaries = []
    for report_file in reports[:10]:
        try:
            data = json.loads(report_file.read_text())
            report_summaries.append(
                {
                    "session_id": report_file.stem,
                    "mission_name": data.get("mission_name", "unknown"),
                    "outcome": data.get("outcome", "unknown"),
                    "step_count": data.get("step_count", 0),
                    "observation_count": len(data.get("observations", [])),
                    "started_at": data.get("started_at", ""),
                }
            )
        except (json.JSONDecodeError, OSError):
            continue

    return json.dumps(
        {
            "reports": report_summaries,
            "latest": reports[0].stem if reports else None,
            "hint": "Use session_id parameter to get full report details",
        },
        indent=2,
    )


def save_discovery_report(project_path: Path, transcript_json: dict[str, Any]) -> Path:
    """
    Save a discovery transcript as a report file.

    Called programmatically after agent.run() completes.
    Returns the path to the saved report.
    """
    report_dir = project_path / ".dazzle" / "discovery"
    report_dir.mkdir(parents=True, exist_ok=True)

    session_id = f"discovery_{int(time.time())}"
    report_file = report_dir / f"{session_id}.json"
    report_file.write_text(json.dumps(transcript_json, indent=2))

    return report_file


def compile_discovery_handler(project_path: Path, args: dict[str, Any]) -> str:
    """
    Compile observations from a discovery report into prioritized proposals.

    Requires a session_id pointing to a saved discovery report that contains
    observations. Returns the compiled proposals as JSON.
    """
    from dazzle.agent.compiler import NarrativeCompiler
    from dazzle.agent.transcript import Observation

    session_id = args.get("session_id")
    persona = args.get("persona", "user")

    report_dir = project_path / ".dazzle" / "discovery"

    # Find the report file
    if session_id:
        report_file = report_dir / f"{session_id}.json"
    else:
        # Use most recent
        if not report_dir.exists():
            return json.dumps({"error": "No discovery reports found"})
        reports = sorted(report_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not reports:
            return json.dumps({"error": "No discovery reports found"})
        report_file = reports[0]
        session_id = report_file.stem

    if not report_file.exists():
        return json.dumps({"error": f"Report not found: {session_id}"})

    try:
        data = json.loads(report_file.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return json.dumps({"error": f"Could not read report: {e}"})

    raw_observations = data.get("observations", [])
    if not raw_observations:
        return json.dumps(
            {
                "session_id": session_id,
                "proposals": [],
                "message": "No observations to compile",
            }
        )

    # Reconstruct Observation objects
    observations: list[Observation] = []
    for obs_dict in raw_observations:
        observations.append(
            Observation(
                category=obs_dict.get("category", "gap"),
                severity=obs_dict.get("severity", "medium"),
                title=obs_dict.get("title", ""),
                description=obs_dict.get("description", ""),
                location=obs_dict.get("location", ""),
                related_artefacts=obs_dict.get("related_artefacts", []),
                metadata=obs_dict.get("metadata", {}),
                step_number=obs_dict.get("step_number", 0),
            )
        )

    # Get KG store if available
    kg_store = None
    kg_db = project_path / ".dazzle" / "knowledge_graph.db"
    if kg_db.exists():
        try:
            from dazzle.mcp.knowledge_graph.store import KnowledgeGraph

            kg_store = KnowledgeGraph(str(kg_db))
        except Exception:
            pass

    # Compile
    compiler = NarrativeCompiler(persona=persona, kg_store=kg_store)
    proposals = compiler.compile(observations)

    result: dict[str, Any] = compiler.to_json(proposals)
    result["session_id"] = session_id
    result["report_markdown"] = compiler.report(proposals)

    return json.dumps(result, indent=2)


def emit_discovery_handler(project_path: Path, args: dict[str, Any]) -> str:
    """
    Generate valid DSL code from compiled proposals.

    Runs the compile step first (if needed), then emits DSL for each proposal
    using template-based generation with validation and retry.

    Args (via args dict):
        session_id: Discovery session to emit from (optional, uses latest)
        persona: Persona name for narrative context (default: "user")
        proposal_ids: Specific proposal IDs to emit (optional, emits all)
    """
    from dazzle.agent.compiler import NarrativeCompiler
    from dazzle.agent.emitter import DslEmitter, build_emit_context
    from dazzle.agent.transcript import Observation

    session_id = args.get("session_id")
    persona = args.get("persona", "user")
    proposal_ids = args.get("proposal_ids")

    report_dir = project_path / ".dazzle" / "discovery"

    # Find the report file
    if session_id:
        report_file = report_dir / f"{session_id}.json"
    else:
        if not report_dir.exists():
            return json.dumps({"error": "No discovery reports found"})
        reports = sorted(report_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not reports:
            return json.dumps({"error": "No discovery reports found"})
        report_file = reports[0]
        session_id = report_file.stem

    if not report_file.exists():
        return json.dumps({"error": f"Report not found: {session_id}"})

    try:
        data = json.loads(report_file.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return json.dumps({"error": f"Could not read report: {e}"})

    raw_observations = data.get("observations", [])
    if not raw_observations:
        return json.dumps(
            {"session_id": session_id, "results": [], "message": "No observations to emit from"}
        )

    # Reconstruct observations and compile into proposals
    observations: list[Observation] = []
    for obs_dict in raw_observations:
        observations.append(
            Observation(
                category=obs_dict.get("category", "gap"),
                severity=obs_dict.get("severity", "medium"),
                title=obs_dict.get("title", ""),
                description=obs_dict.get("description", ""),
                location=obs_dict.get("location", ""),
                related_artefacts=obs_dict.get("related_artefacts", []),
                metadata=obs_dict.get("metadata", {}),
                step_number=obs_dict.get("step_number", 0),
            )
        )

    compiler = NarrativeCompiler(persona=persona)
    proposals = compiler.compile(observations)

    # Filter to specific proposals if requested
    if proposal_ids:
        id_set = set(proposal_ids)
        proposals = [p for p in proposals if p.id in id_set]

    if not proposals:
        return json.dumps(
            {"session_id": session_id, "results": [], "message": "No matching proposals to emit"}
        )

    # Load appspec for emit context
    try:
        appspec = _load_appspec(project_path)
        context = build_emit_context(appspec)
    except Exception as e:
        return json.dumps({"error": f"Failed to load DSL for emit context: {e}"})

    # Emit DSL for each proposal
    emitter = DslEmitter()
    results = emitter.emit_batch(proposals, context)

    # Build response
    result: dict[str, Any] = {
        "session_id": session_id,
        "total_proposals": len(proposals),
        "total_emitted": len(results),
        "valid_count": sum(1 for r in results if r.valid),
        "results": [r.to_json() for r in results],
        "report_markdown": emitter.emit_report(results),
    }

    return json.dumps(result, indent=2)


def discovery_status_handler(project_path: Path, args: dict[str, Any]) -> str:
    """
    Check discovery infrastructure status.

    Reports whether the project has valid DSL, KG availability, etc.
    """
    result: dict[str, Any] = {
        "project_path": str(project_path),
        "dsl_valid": False,
        "kg_available": False,
        "reports_count": 0,
    }

    # Check DSL
    try:
        appspec = _load_appspec(project_path)
        result["dsl_valid"] = True
        result["entities"] = (
            len(appspec.domain.entities) if hasattr(appspec.domain, "entities") else 0
        )
        result["surfaces"] = len(appspec.surfaces)
        result["personas"] = len(appspec.personas)
    except Exception as e:
        result["dsl_error"] = str(e)

    # Check KG
    kg_db = project_path / ".dazzle" / "knowledge_graph.db"
    result["kg_available"] = kg_db.exists()

    # Check existing reports
    report_dir = project_path / ".dazzle" / "discovery"
    if report_dir.exists():
        result["reports_count"] = len(list(report_dir.glob("*.json")))

    return json.dumps(result, indent=2)
