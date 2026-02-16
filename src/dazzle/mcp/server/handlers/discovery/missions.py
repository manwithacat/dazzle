"""Discovery mission execution handlers (run, headless)."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from ..common import async_handler_error_json, handler_error_json
from ._helpers import (
    _get_persona_session_info,
    _load_appspec,
    _populate_kg_for_discovery,
    save_discovery_report,
)

logger = logging.getLogger("dazzle.mcp.handlers.discovery")


@async_handler_error_json
async def run_discovery_handler(project_path: Path, args: dict[str, Any]) -> str:
    """
    Build a discovery mission and execute the agent loop.

    Requires a running app at base_url and an ANTHROPIC_API_KEY env var.

    Supports four modes:
    - persona (default): Open-ended persona walkthrough
    - entity_completeness: Static CRUD coverage + targeted verification
    - workflow_coherence: Static process/story integrity + targeted verification
    - headless: Pure static analysis — no running app needed
    """
    import os

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

    # --- Preflight checks ---

    # API key is optional — when running inside an MCP host (e.g. Claude Code)
    # we can fall back to MCP sampling for LLM completions.
    api_key = os.environ.get("ANTHROPIC_API_KEY")

    # Extract MCP session from progress context for sampling fallback
    mcp_session = None
    progress_ctx = args.get("_progress")
    if progress_ctx is not None:
        mcp_session = getattr(progress_ctx, "session", None)

    from ..preflight import check_server_reachable

    server_error = check_server_reachable(base_url)
    if server_error is not None:
        return server_error

    # --- Build mission ---

    try:
        appspec = _load_appspec(project_path)
    except Exception as e:
        return json.dumps({"error": f"Failed to load DSL: {e}"}, indent=2)

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

    # --- Execute agent loop ---

    progress = args.get("_progress")

    try:
        import httpx

        from dazzle.agent.core import DazzleAgent
        from dazzle.agent.executor import HttpExecutor
        from dazzle.agent.observer import HttpObserver

        # Set up auth cookies for persona mode
        cookies: dict[str, str] = {}
        if mode == "persona":
            session_info = await _get_persona_session_info(project_path, persona, base_url)
            cookies = session_info.get("cookie", {})

        t0 = time.monotonic()

        def _on_step(step_num: int, step: Any) -> None:
            """Report step progress to the activity log."""
            if progress is not None:
                try:
                    action_type = step.action.type.value if step.action else "unknown"
                    progress.log_sync(
                        f"Step {step_num}/{mission.max_steps}: {action_type}"
                        + (f" → {step.action.target[:40]}" if step.action.target else "")
                    )
                except Exception:
                    logger.debug("Failed to log discovery step progress", exc_info=True)

        async with httpx.AsyncClient(
            base_url=base_url,
            cookies=cookies,
            follow_redirects=True,
            timeout=30.0,
        ) as client:
            observer = HttpObserver(client, base_url)
            executor = HttpExecutor(client, base_url, observer=observer)
            agent = DazzleAgent(observer, executor, api_key=api_key, mcp_session=mcp_session)

            if progress is not None:
                progress.log_sync(f"Starting {mode} discovery against {base_url}")

            transcript = await agent.run(mission, on_step=_on_step)

        wall_ms = (time.monotonic() - t0) * 1000

    except Exception as e:
        logger.exception("Discovery agent execution failed")
        return json.dumps(
            {
                "error": f"Agent execution failed: {e}",
                "hint": "Check that the app is running. LLM auth requires either ANTHROPIC_API_KEY or an MCP host that supports sampling.",
            },
            indent=2,
        )

    # --- Save report ---

    transcript_json = transcript.to_json()
    transcript_json["mode"] = mode
    if mode == "persona":
        transcript_json["persona"] = persona

    report_file = save_discovery_report(project_path, transcript_json)
    session_id = report_file.stem

    if progress is not None:
        progress.log_sync(
            f"Discovery {transcript.outcome}: {len(transcript.steps)} steps, "
            f"{len(transcript.observations)} observations → {session_id}"
        )

    result: dict[str, Any] = {
        "status": transcript.outcome,
        "mode": mode,
        "session_id": session_id,
        "outcome": transcript.outcome,
        "steps": len(transcript.steps),
        "observations": len(transcript.observations),
        "tokens_used": transcript.tokens_used,
        "summary": transcript.summary(),
        "instructions": (
            f"Discovery complete. Use session_id '{session_id}' with:\n"
            f"  discovery(operation='compile', session_id='{session_id}')  → proposals\n"
            f"  discovery(operation='emit', session_id='{session_id}')     → DSL code"
        ),
        "_meta": {
            "wall_time_ms": round(wall_ms, 1),
            "steps_executed": len(transcript.steps),
            "observations_found": len(transcript.observations),
            "tokens_used": transcript.tokens_used,
        },
    }

    if transcript.error:
        result["error"] = transcript.error

    return json.dumps(result, indent=2)


@handler_error_json
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

    appspec = _load_appspec(project_path)
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
