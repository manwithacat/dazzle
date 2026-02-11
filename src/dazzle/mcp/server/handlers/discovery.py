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

from dazzle.agent.transcript import Observation

logger = logging.getLogger("dazzle.mcp.handlers.discovery")


# =============================================================================
# Shared Helpers
# =============================================================================


def _load_report_data(
    project_path: Path,
    session_id: str | None,
) -> tuple[dict[str, Any], str] | str:
    """
    Find and load a discovery report.

    Returns (data_dict, session_id) on success, or an error JSON string on failure.
    """
    report_dir = project_path / ".dazzle" / "discovery"

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

    return data, session_id


def _deserialize_observations(raw_observations: list[dict[str, Any]]) -> list[Observation]:
    """Reconstruct Observation objects from serialized dicts."""
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
    return observations


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


def _get_persona_session_info(project_path: Path, persona: str, base_url: str) -> dict[str, Any]:
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
        import asyncio

        asyncio.run(manager.create_session(persona))
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


def run_discovery_handler(project_path: Path, args: dict[str, Any]) -> str:
    """
    Build and describe a discovery mission (non-executing).

    Since the discovery agent requires a live application and an LLM API key,
    this handler builds the mission configuration and returns it as a structured
    report. The actual agent execution happens via `dazzle discover` CLI or
    programmatic API.

    Supports three modes:
    - persona (default): Open-ended persona walkthrough
    - entity_completeness: Static CRUD coverage + targeted verification
    - workflow_coherence: Static process/story integrity + targeted verification

    Returns the mission spec including system prompt, tools, and DSL summary
    so the caller can inspect or run it.
    """
    mode = args.get("mode", "persona")
    persona = args.get("persona", "admin")
    base_url = args.get("base_url", "http://localhost:3000")
    max_steps = args.get("max_steps", 50)
    token_budget = args.get("token_budget", 200_000)

    valid_modes = {"persona", "entity_completeness", "workflow_coherence", "headless"}
    if mode not in valid_modes:
        return json.dumps(
            {
                "error": f"Unknown discovery mode: {mode}. Valid modes: {', '.join(sorted(valid_modes))}"
            },
            indent=2,
        )

    if mode == "headless":
        return run_headless_discovery_handler(project_path, args)

    try:
        appspec = _load_appspec(project_path)
    except Exception as e:
        return json.dumps({"error": f"Failed to load DSL: {e}"}, indent=2)

    # Optionally populate KG for adjacency features
    kg_store = _populate_kg_for_discovery(project_path)

    if mode == "persona":
        from dazzle.agent.missions.discovery import build_discovery_mission

        mission = build_discovery_mission(
            appspec=appspec,
            persona_name=persona,
            base_url=base_url,
            kg_store=kg_store,
            max_steps=max_steps,
            token_budget=token_budget,
        )
    elif mode == "entity_completeness":
        from dazzle.agent.missions.entity_completeness import build_entity_completeness_mission

        mission = build_entity_completeness_mission(
            appspec=appspec,
            base_url=base_url,
            kg_store=kg_store,
            max_steps=max_steps,
            token_budget=token_budget,
        )
    elif mode == "workflow_coherence":
        from dazzle.agent.missions.workflow_coherence import build_workflow_coherence_mission

        mission = build_workflow_coherence_mission(
            appspec=appspec,
            base_url=base_url,
            kg_store=kg_store,
            max_steps=max_steps,
            token_budget=token_budget,
        )

    result = _build_mission_summary(
        mission, mode, appspec, kg_store, base_url, persona=persona if mode == "persona" else None
    )

    # Include persona session info for authenticated discovery
    if mode == "persona":
        session_info = _get_persona_session_info(project_path, persona, base_url)
        result["session"] = session_info

    result["instructions"] = (
        "Mission is ready. To execute, run the discovery agent against a live app:\n"
        f"  dazzle discover --mode {mode} --url {base_url}"
        + (f" --persona {persona}" if mode == "persona" else "")
        + "\n"
        "Or programmatically:\n"
        "  from dazzle.agent import DazzleAgent\n"
        "  from dazzle.agent.observer import HttpObserver\n"
        "  from dazzle.agent.executor import HttpExecutor\n"
        "  agent = DazzleAgent(observer, executor)\n"
        "  transcript = await agent.run(mission)"
    )

    return json.dumps(result, indent=2)


def run_headless_discovery_handler(project_path: Path, args: dict[str, Any]) -> str:
    """
    Run headless persona journey analysis.

    Pure static analysis — no running app needed. Analyzes whether each persona
    can accomplish their stories through the surfaces and workspaces in the DSL.

    Returns a complete result immediately (no mission spec to run externally).
    The saved report enables compile and emit operations via the same session_id workflow.
    """
    from dazzle.agent.missions.persona_journey import run_headless_discovery

    persona_ids = args.get("persona_ids")
    if isinstance(persona_ids, str):
        persona_ids = [persona_ids]
    # Also accept single "persona" arg as filter
    persona_arg = args.get("persona")
    if persona_arg and not persona_ids:
        persona_ids = [persona_arg]

    t0 = time.monotonic()

    try:
        appspec = _load_appspec(project_path)
    except Exception as e:
        return json.dumps({"error": f"Failed to load DSL: {e}"}, indent=2)

    kg_store = _populate_kg_for_discovery(project_path)

    report = run_headless_discovery(
        appspec=appspec,
        persona_ids=persona_ids,
        kg_store=kg_store,
    )

    # Convert to observations for pipeline compatibility
    observations = report.to_observations()

    # Save as standard discovery report for compile/emit reuse
    transcript_json: dict[str, Any] = {
        "mission_name": "headless_discovery",
        "outcome": "completed",
        "step_count": 0,
        "observations": [
            {
                "category": obs.category,
                "severity": obs.severity,
                "title": obs.title,
                "description": obs.description,
                "location": obs.location,
                "related_artefacts": obs.related_artefacts,
                "metadata": obs.metadata,
                "step_number": obs.step_number,
            }
            for obs in observations
        ],
        "started_at": "",
        "mode": "headless",
        "headless_report": report.to_json(),
    }

    report_file = save_discovery_report(project_path, transcript_json)
    session_id = report_file.stem

    wall_ms = (time.monotonic() - t0) * 1000
    result: dict[str, Any] = {
        "status": "completed",
        "mode": "headless",
        "session_id": session_id,
        "personas_analyzed": len(report.persona_reports),
        "total_gaps": sum(len(pr.gaps) for pr in report.persona_reports),
        "observation_count": len(observations),
        "report": report.to_json(),
        "summary": report.to_summary(),
        "instructions": (
            f"Headless analysis complete. Use session_id '{session_id}' with:\n"
            f"  discovery(operation='compile', session_id='{session_id}')  → proposals\n"
            f"  discovery(operation='emit', session_id='{session_id}')     → DSL code"
        ),
        "_meta": {
            "wall_time_ms": round(wall_ms, 1),
            "personas_analyzed": len(report.persona_reports),
            "observations_generated": len(observations),
        },
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

    persona = args.get("persona", "user")
    t0 = time.monotonic()

    loaded = _load_report_data(project_path, args.get("session_id"))
    if isinstance(loaded, str):
        return loaded
    data, session_id = loaded

    raw_observations = data.get("observations", [])
    if not raw_observations:
        return json.dumps(
            {
                "session_id": session_id,
                "proposals": [],
                "message": "No observations to compile",
            }
        )

    observations = _deserialize_observations(raw_observations)

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
    wall_ms = (time.monotonic() - t0) * 1000
    result["_meta"] = {
        "wall_time_ms": round(wall_ms, 1),
        "proposals_generated": len(proposals),
    }

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

    persona = args.get("persona", "user")
    proposal_ids = args.get("proposal_ids")
    t0 = time.monotonic()

    loaded = _load_report_data(project_path, args.get("session_id"))
    if isinstance(loaded, str):
        return loaded
    data, session_id = loaded

    raw_observations = data.get("observations", [])
    if not raw_observations:
        return json.dumps(
            {"session_id": session_id, "results": [], "message": "No observations to emit from"}
        )

    observations = _deserialize_observations(raw_observations)

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
    wall_ms = (time.monotonic() - t0) * 1000
    result: dict[str, Any] = {
        "session_id": session_id,
        "total_proposals": len(proposals),
        "total_emitted": len(results),
        "valid_count": sum(1 for r in results if r.valid),
        "results": [r.to_json() for r in results],
        "report_markdown": emitter.emit_report(results),
        "_meta": {
            "wall_time_ms": round(wall_ms, 1),
            "proposals_emitted": len(results),
            "valid_dsl_count": sum(1 for r in results if r.valid),
        },
    }

    return json.dumps(result, indent=2)


def verify_all_stories_handler(project_path: Path, args: dict[str, Any]) -> str:
    """
    Batch verify all accepted stories against API tests.

    Loads all accepted stories, maps each to its entity tests via scope,
    runs them, and returns a structured pass/fail report — the automated UAT.
    """
    try:
        from dazzle.core.ir.stories import StoryStatus
        from dazzle.core.stories_persistence import get_stories_by_status

        from .dsl_test import verify_story_handler

        base_url = args.get("base_url")

        # Load accepted stories
        stories = get_stories_by_status(project_path, StoryStatus.ACCEPTED)
        if not stories:
            return json.dumps(
                {
                    "status": "no_stories",
                    "message": "No accepted stories found. Use story(operation='propose') and accept them first.",
                },
                indent=2,
            )

        # Run verify_story for all stories at once (the handler handles batching)
        all_ids = [s.story_id for s in stories]
        verify_args: dict[str, Any] = {
            "story_ids": all_ids,
        }
        if base_url:
            verify_args["base_url"] = base_url

        raw_result = verify_story_handler(project_path, verify_args)
        result_data = json.loads(raw_result)

        # Wrap with discovery-specific metadata
        if "error" in result_data:
            return raw_result

        response: dict[str, Any] = {
            "operation": "verify_all_stories",
            "total_accepted_stories": len(stories),
            **result_data,
            "summary": (
                f"{result_data.get('stories_passed', 0)}/{len(stories)} stories verified successfully"
            ),
        }

        return json.dumps(response, indent=2)

    except ImportError as e:
        return json.dumps({"error": f"Module not available: {e}"}, indent=2)
    except Exception as e:
        logger.exception("Error verifying all stories")
        return json.dumps({"error": f"Failed to verify stories: {e}"}, indent=2)


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


# =============================================================================
# App Coherence Handler
# =============================================================================

# Gap type → named coherence check + severity weight
_GAP_TO_CHECK: dict[str, tuple[str, str]] = {
    "workspace_unreachable": ("workspace_binding", "error"),
    "surface_inaccessible": ("surface_access", "error"),
    "story_no_surface": ("story_coverage", "error"),
    "process_step_no_surface": ("workflow_wiring", "error"),
    "experience_broken_step": ("experience_integrity", "error"),
    "experience_dangling_transition": ("experience_integrity", "warning"),
    "unreachable_experience": ("experience_reachable", "error"),
    "orphan_surfaces": ("dead_ends", "suggestion"),
    "cross_entity_gap": ("cross_entity_nav", "warning"),
    "nav_over_exposed": ("nav_filtering", "error"),
    "nav_under_exposed": ("nav_filtering", "warning"),
}

_SEVERITY_WEIGHTS: dict[str, int] = {
    "error": 20,
    "warning": 5,
    "suggestion": 1,
}

_PRIORITY_MULTIPLIERS: dict[str, float] = {
    "critical": 2.0,
    "high": 1.5,
    "medium": 1.0,
    "low": 0.5,
}


def _compute_coherence_score(deductions: float) -> int:
    """Compute a 0-100 coherence score from accumulated deductions."""
    return max(0, min(100, round(100 - deductions)))


def app_coherence_handler(project_path: Path, args: dict[str, Any]) -> str:
    """
    Run persona-by-persona authenticated UX coherence checks.

    Synthesizes headless discovery gaps into named checks with a coherence
    score per persona, using the same scoring model as sitespec(coherence).

    Args (via args dict):
        persona: Optional persona ID to check (default: all)
    """
    try:
        from dazzle.agent.missions.persona_journey import run_headless_discovery

        appspec = _load_appspec(project_path)
    except Exception as e:
        return json.dumps({"error": f"Failed to load project: {e}"}, indent=2)

    persona_filter = args.get("persona")
    persona_ids = [persona_filter] if persona_filter else None

    try:
        report = run_headless_discovery(
            appspec,
            persona_ids=persona_ids,
            include_entity_analysis=False,
            include_workflow_analysis=False,
        )
    except Exception as e:
        logger.exception("App coherence analysis failed")
        return json.dumps({"error": f"Analysis failed: {e}"}, indent=2)

    persona_results: list[dict[str, Any]] = []

    for pr in report.persona_reports:
        # Aggregate gaps into named checks
        checks: dict[str, dict[str, Any]] = {}

        for gap in pr.gaps:
            check_name, severity_category = _GAP_TO_CHECK.get(gap.gap_type, ("other", "warning"))

            if check_name not in checks:
                checks[check_name] = {
                    "check": check_name,
                    "status": "pass",
                    "issues": [],
                }

            # Escalate status: pass → suggestion → warn → fail
            current = checks[check_name]["status"]
            if severity_category == "error" and current != "fail":
                checks[check_name]["status"] = "fail"
            elif severity_category == "warning" and current in ("pass", "suggestion"):
                checks[check_name]["status"] = "warn"
            elif severity_category == "suggestion" and current == "pass":
                checks[check_name]["status"] = "suggestion"

            checks[check_name]["issues"].append(
                {
                    "gap_type": gap.gap_type,
                    "severity": gap.severity,
                    "description": gap.description,
                    "surface_name": gap.surface_name or "",
                }
            )

        # Compute score with priority weighting
        # Build surface → priority lookup from appspec
        surface_priority: dict[str, str] = {}
        for s in getattr(appspec, "surfaces", []) or []:
            p = str(getattr(s, "priority", "medium")).lower()
            surface_priority[s.name] = p

        total_deductions: float = 0
        for check in checks.values():
            for issue in check["issues"]:
                gap_type = issue["gap_type"]
                _, sev_cat = _GAP_TO_CHECK.get(gap_type, ("other", "warning"))
                base_weight = _SEVERITY_WEIGHTS.get(sev_cat, 5)
                # Apply priority multiplier from the surface if available
                surface_name = issue.get("surface_name", "")
                priority = surface_priority.get(surface_name, "medium")
                multiplier = _PRIORITY_MULTIPLIERS.get(priority, 1.0)
                total_deductions += base_weight * multiplier

        # Add detail summary to each check
        for check in checks.values():
            if check["issues"]:
                check["detail"] = check["issues"][0]["description"]
                if len(check["issues"]) > 1:
                    check["detail"] += f" (+{len(check['issues']) - 1} more)"
            # Remove raw issues from output to keep it concise
            del check["issues"]

        # Ensure standard checks appear even when passed
        for standard_check in [
            "workspace_binding",
            "nav_filtering",
            "experience_reachable",
            "surface_access",
            "story_coverage",
        ]:
            if standard_check not in checks:
                checks[standard_check] = {
                    "check": standard_check,
                    "status": "pass",
                }

        score = _compute_coherence_score(total_deductions)
        persona_results.append(
            {
                "persona": pr.persona_id,
                "coherence_score": score,
                "workspace": pr.default_workspace,
                "checks": list(checks.values()),
                "gap_count": len(pr.gaps),
            }
        )

    # Overall score = average of persona scores
    overall_score = (
        round(sum(p["coherence_score"] for p in persona_results) / len(persona_results))
        if persona_results
        else 100
    )

    return json.dumps(
        {
            "overall_score": overall_score,
            "personas": persona_results,
            "skipped_personas": report.skipped_personas,
            "persona_count": len(persona_results),
        },
        indent=2,
    )
