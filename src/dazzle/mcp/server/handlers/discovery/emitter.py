"""Discovery emit handler — DSL generation from observations."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from dazzle.core.appspec_loader import load_project_appspec

from ..common import extract_progress, wrap_handler_errors
from ._helpers import deserialize_observations, load_report_data

logger = logging.getLogger("dazzle.mcp.handlers.discovery")


def discovery_emit_impl(
    project_path: Path,
    session_id: str | None = None,
    persona: str = "user",
    proposal_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Generate valid DSL code from compiled discovery proposals.

    Pure function — no MCP types. Loads the saved discovery report, compiles
    observations into proposals, then emits DSL for each (or for the subset
    specified by *proposal_ids*).

    Args:
        project_path: Root directory of the Dazzle project.
        session_id: Discovery session to emit from (``None`` → latest report).
        persona: Persona name used for narrative framing during compile.
        proposal_ids: Optional list of proposal IDs to restrict emission to.

    Returns:
        Plain dict with keys ``session_id``, ``total_proposals``,
        ``total_emitted``, ``valid_count``, ``results``, ``report_markdown``,
        and ``_meta``.

    Raises:
        ValueError: Propagated from :func:`load_report_data` when the report
            cannot be found or parsed.
    """
    from dazzle.agent.compiler import NarrativeCompiler
    from dazzle.agent.emitter import DslEmitter, build_emit_context

    t0 = time.monotonic()

    loaded = load_report_data(project_path, session_id)
    if isinstance(loaded, str):
        raise ValueError(json.loads(loaded).get("error", "Could not load report"))
    data, resolved_session_id = loaded

    raw_observations = data.get("observations", [])
    if not raw_observations:
        return {
            "session_id": resolved_session_id,
            "results": [],
            "message": "No observations to emit from",
        }

    observations = deserialize_observations(raw_observations)

    compiler = NarrativeCompiler(persona=persona)
    proposals = compiler.compile(observations)

    # Filter to specific proposals if requested
    if proposal_ids:
        id_set = set(proposal_ids)
        proposals = [p for p in proposals if p.id in id_set]

    if not proposals:
        return {
            "session_id": resolved_session_id,
            "results": [],
            "message": "No matching proposals to emit",
        }

    # Load appspec for emit context
    appspec = load_project_appspec(project_path)
    context = build_emit_context(appspec)

    # Emit DSL for each proposal
    emitter = DslEmitter()
    emit_results = emitter.emit_batch(proposals, context)
    valid_count = sum(1 for r in emit_results if r.valid)

    wall_ms = (time.monotonic() - t0) * 1000
    return {
        "session_id": resolved_session_id,
        "total_proposals": len(proposals),
        "total_emitted": len(emit_results),
        "valid_count": valid_count,
        "results": [r.to_json() for r in emit_results],
        "report_markdown": emitter.emit_report(emit_results),
        "_meta": {
            "wall_time_ms": round(wall_ms, 1),
            "proposals_emitted": len(emit_results),
            "valid_dsl_count": valid_count,
        },
    }


@wrap_handler_errors
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
    progress = extract_progress(args)
    persona = args.get("persona", "user")
    proposal_ids = args.get("proposal_ids")
    session_id = args.get("session_id")

    progress.log_sync("Emitting DSL from proposals...")

    loaded = load_report_data(project_path, session_id)
    if isinstance(loaded, str):
        return loaded
    _data, _sid = loaded
    raw_count = len(_data.get("observations", []))

    if not raw_count:
        return json.dumps(
            {"session_id": _sid, "results": [], "message": "No observations to emit from"}
        )

    progress.log_sync(f"Generating DSL for session {_sid}...")

    result = discovery_emit_impl(
        project_path=project_path,
        session_id=session_id,
        persona=persona,
        proposal_ids=proposal_ids,
    )

    valid_count = result.get("valid_count", 0)
    total_emitted = result.get("total_emitted", 0)
    progress.log_sync(f"Emitted {total_emitted} blocks ({valid_count} valid)")

    return json.dumps(result, indent=2)
