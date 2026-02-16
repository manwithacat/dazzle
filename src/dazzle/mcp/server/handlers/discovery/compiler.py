"""Discovery compile and report handlers."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from dazzle.mcp.server.paths import project_discovery_dir, project_kg_db

from ..common import handler_error_json
from ..utils import deserialize_observations, load_report_data

logger = logging.getLogger("dazzle.mcp.handlers.discovery")


@handler_error_json
def get_discovery_report_handler(project_path: Path, args: dict[str, Any]) -> str:
    """
    Get the latest discovery report from a project.

    Reports are stored in .dazzle/discovery/ as JSON files.
    """
    report_dir = project_discovery_dir(project_path)
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


@handler_error_json
def compile_discovery_handler(project_path: Path, args: dict[str, Any]) -> str:
    """
    Compile observations from a discovery report into prioritized proposals.

    Requires a session_id pointing to a saved discovery report that contains
    observations. Returns the compiled proposals as JSON.
    """
    from dazzle.agent.compiler import NarrativeCompiler

    persona = args.get("persona", "user")
    t0 = time.monotonic()

    loaded = load_report_data(project_path, args.get("session_id"))
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
