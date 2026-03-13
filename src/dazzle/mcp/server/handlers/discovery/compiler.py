"""Discovery compile and report handlers."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from dazzle.core.paths import project_discovery_dir, project_kg_db

from ..common import error_response, extract_progress, wrap_handler_errors
from ._helpers import deserialize_observations, load_report_data

logger = logging.getLogger("dazzle.mcp.handlers.discovery")


def discovery_report_impl(
    project_path: Path,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Return discovery report data as a plain dict.

    When *session_id* is provided, returns the full JSON content of that
    report. When omitted, returns a summary list of the ten most recent
    reports stored under the project's discovery directory.

    Args:
        project_path: Root directory of the Dazzle project.
        session_id: Optional session ID to retrieve a specific report.

    Returns:
        Plain dict — either the report content or a summaries dict with
        ``{"reports": [...], "latest": str | None, "hint": str}``.

    Raises:
        FileNotFoundError: If the requested session_id does not exist.
        ValueError: If no reports exist at all.
    """
    report_dir = project_discovery_dir(project_path)

    if session_id:
        report_file = report_dir / f"{session_id}.json"
        if not report_file.exists():
            raise FileNotFoundError(f"Report not found: {session_id}")
        result: dict[str, Any] = json.loads(report_file.read_text())
        return result

    if not report_dir.exists():
        raise ValueError("No discovery reports found. Run a discovery session first.")

    reports = sorted(report_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not reports:
        raise ValueError("No discovery reports found")

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

    return {
        "reports": report_summaries,
        "latest": reports[0].stem if reports else None,
        "hint": "Use session_id parameter to get full report details",
    }


def discovery_compile_impl(
    project_path: Path,
    session_id: str | None = None,
    persona: str = "user",
) -> dict[str, Any]:
    """Compile discovery observations into prioritized proposals.

    Pure function — no MCP types. Loads the saved discovery report identified
    by *session_id* (or the latest report when omitted), deserialises
    observations, runs :class:`~dazzle.agent.compiler.NarrativeCompiler`, and
    returns a plain result dict.

    Args:
        project_path: Root directory of the Dazzle project.
        session_id: Discovery session to compile (``None`` → latest report).
        persona: Persona name used for narrative framing.

    Returns:
        Plain dict with keys ``session_id``, ``proposals``, ``report_markdown``,
        and ``_meta``.

    Raises:
        FileNotFoundError / ValueError: Propagated from :func:`load_report_data`
            when the report cannot be located.
    """
    from dazzle.agent.compiler import NarrativeCompiler

    t0 = time.monotonic()

    loaded = load_report_data(project_path, session_id)
    if isinstance(loaded, str):
        # load_report_data returns a JSON error string on failure; surface it
        raise ValueError(json.loads(loaded).get("error", "Could not load report"))
    data, resolved_session_id = loaded

    raw_observations = data.get("observations", [])
    if not raw_observations:
        return {
            "session_id": resolved_session_id,
            "proposals": [],
            "message": "No observations to compile",
        }

    observations = deserialize_observations(raw_observations)

    # Get KG store if available
    kg_store = None
    kg_db = project_kg_db(project_path)
    if kg_db.exists():
        try:
            from dazzle.mcp.knowledge_graph.store import KnowledgeGraph

            kg_store = KnowledgeGraph(str(kg_db))
        except Exception:
            logger.debug("Knowledge graph not available for compile", exc_info=True)

    compiler = NarrativeCompiler(persona=persona, kg_store=kg_store)
    proposals = compiler.compile(observations)

    result: dict[str, Any] = compiler.to_json(proposals)
    result["session_id"] = resolved_session_id
    result["report_markdown"] = compiler.report(proposals)
    wall_ms = (time.monotonic() - t0) * 1000
    result["_meta"] = {
        "wall_time_ms": round(wall_ms, 1),
        "proposals_generated": len(proposals),
    }

    return result


@wrap_handler_errors
def get_discovery_report_handler(project_path: Path, args: dict[str, Any]) -> str:
    """
    Get the latest discovery report from a project.

    Reports are stored in .dazzle/discovery/ as JSON files.
    """
    session_id = args.get("session_id")

    try:
        result = discovery_report_impl(project_path, session_id=session_id)
    except FileNotFoundError as exc:
        return error_response(str(exc))
    except ValueError as exc:
        hint_suffix = (
            "\nRun a discovery session first with operation: run"
            if "No discovery reports" in str(exc)
            else ""
        )
        return json.dumps({"error": str(exc) + hint_suffix})

    # When retrieving a specific session the impl returns the raw report dict;
    # serialise it back to a string as the MCP layer expects.
    return json.dumps(result, indent=2)


@wrap_handler_errors
def compile_discovery_handler(project_path: Path, args: dict[str, Any]) -> str:
    """
    Compile observations from a discovery report into prioritized proposals.

    Requires a session_id pointing to a saved discovery report that contains
    observations. Returns the compiled proposals as JSON.
    """
    progress = extract_progress(args)
    persona = args.get("persona", "user")
    session_id = args.get("session_id")

    progress.log_sync("Compiling discovery observations...")

    loaded = load_report_data(project_path, session_id)
    if isinstance(loaded, str):
        return loaded
    _data, _sid = loaded
    raw_count = len(_data.get("observations", []))

    progress.log_sync(f"Compiling {raw_count} observations...")

    result = discovery_compile_impl(
        project_path=project_path,
        session_id=session_id,
        persona=persona,
    )

    proposals_count = result.get("_meta", {}).get("proposals_generated", 0)
    progress.log_sync(f"Compiled into {proposals_count} proposals")

    return json.dumps(result, indent=2)
