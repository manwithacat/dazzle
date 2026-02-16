"""Discovery emit handler — DSL generation from observations."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from ..common import handler_error_json
from ..utils import deserialize_observations, load_report_data
from ._helpers import _load_appspec

logger = logging.getLogger("dazzle.mcp.handlers.discovery")


@handler_error_json
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

    loaded = load_report_data(project_path, args.get("session_id"))
    if isinstance(loaded, str):
        return loaded
    data, session_id = loaded

    raw_observations = data.get("observations", [])
    if not raw_observations:
        return json.dumps(
            {"session_id": session_id, "results": [], "message": "No observations to emit from"}
        )

    observations = deserialize_observations(raw_observations)

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
