"""Cycle 198 Path γ spike — run explore strategy through MCP sampling.

**Status:** spike-specific. Not intended to be a permanent feature.
Deletion/refactor follow-up is expected after cycle 198 evaluates the
results.

**Question this answers:** can ``DazzleAgent`` run an explore mission
through MCP sampling (Path γ in the Apr 14 dazzle-agent-robust-parser
spec), using Playwright for the browser, with LLM cognition billed to
the Claude Code host's subscription instead of the metered Anthropic
SDK — and does it produce usable output for the explore mission?

**Why this lives under ``discovery/``:** minimal surface area for the
spike. Dispatching as a new operation under the existing ``discovery``
tool lets us reuse the tool registration and progress-context plumbing
that ``discovery.coherence`` already uses. If the spike succeeds, cycle
198's full implementation will move this into a dedicated ``ux_cycle``
tool namespace.

**What the handler does:**

1. Pulls the MCP session from ``args["_progress"].session`` — same
   pattern as ``discovery.run``. If absent, returns an error telling
   the caller the tool requires an MCP host.
2. Loads the example app's ``.env`` (DATABASE_URL / REDIS_URL).
3. Spawns a ``ModeRunner`` for the example app, yielding an
   ``AppConnection``.
4. Calls ``run_explore_strategy`` with ``mcp_session`` plumbed through
   and ``use_tool_calls=False`` — forcing Path γ (text protocol, robust
   parser, MCP sampling).
5. Returns the ``ExploreOutcome`` as JSON.

**What the handler does NOT do:**

- Does not write artefacts to ``dev_docs/`` — that's cycle 198 proper's
  job once the substrate pivot is decided.
- Does not sweep multiple apps — single-example, optional single
  persona. If the spike needs multi-persona, pass ``personas=None``
  and let ``pick_explore_personas`` pick them.
- Does not clean up the ``ModeRunner`` lock state on crash — relies on
  the existing 15-minute TTL safety net.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("dazzle.mcp.handlers.discovery.explore_spike")


async def discovery_explore_spike_handler(project_path: Path, args: dict[str, Any]) -> str:
    """Cycle 198 spike: Path γ explore run.

    Called through the ``_make_project_handler_async`` factory, which
    passes the resolved project root as the first argument. Since the
    spike handler locates its target example via ``example_name`` (not
    via the active Dazzle project), the ``project_path`` arg is
    effectively ignored — but the signature has to match the dispatch
    contract.

    Args (all from the MCP tool call):
        ``project_path`` — resolved project root (unused by the spike;
            the spike picks its example via ``example_name``).
        ``example_name`` — example app name (e.g. ``"contact_manager"``).
            Defaults to ``"contact_manager"``.
        ``persona_id`` — optional persona to run as. When None, the
            strategy auto-picks business personas via
            ``pick_explore_personas``.
        ``_progress`` — MCP framework-injected progress context. The
            handler extracts ``progress_ctx.session`` and passes it to
            ``DazzleAgent`` for Path γ cognition.

    Returns:
        JSON-encoded spike outcome with the usual ``ExploreOutcome``
        fields plus a ``spike`` marker identifying this as cycle 198
        Path γ data.
    """
    del project_path  # intentionally unused — the spike uses example_name
    example_name = args.get("example_name", "contact_manager")
    persona_id = args.get("persona_id")  # None = auto-pick

    # Extract MCP session from progress context. Same pattern as
    # ``discovery.run`` — see handlers/discovery/missions.py:269-273.
    mcp_session: Any = None
    progress_ctx = args.get("_progress")
    if progress_ctx is not None:
        mcp_session = getattr(progress_ctx, "session", None)

    if mcp_session is None:
        return json.dumps(
            {
                "error": "no MCP session available in progress context",
                "hint": (
                    "This tool requires being invoked from inside an MCP host "
                    "(e.g. Claude Code). The session is injected via "
                    "args['_progress'].session."
                ),
                "spike": "cycle-198-path-gamma",
            },
            indent=2,
        )

    # Load the example app's env vars (DATABASE_URL, REDIS_URL) into the
    # current process environment so ModeRunner + the subprocess can see
    # them.
    dazzle_root = Path(os.environ.get("DAZZLE_PROJECT_ROOT", "/Volumes/SSD/Dazzle"))
    example_root = dazzle_root / "examples" / example_name
    if not example_root.exists():
        return json.dumps(
            {
                "error": f"example directory not found: {example_root}",
                "spike": "cycle-198-path-gamma",
            },
            indent=2,
        )
    env_path = example_root / ".env"
    if env_path.exists():
        for raw in env_path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            k, _, v = line.partition("=")
            os.environ[k] = v

    # Defer heavy imports so tool discovery doesn't pay for them when
    # the spike handler isn't actually called.
    from dazzle.agent.missions.ux_explore import Strategy
    from dazzle.cli.runtime_impl.ux_cycle_impl.explore_strategy import (
        run_explore_strategy,
    )
    from dazzle.e2e.modes import get_mode
    from dazzle.e2e.runner import ModeRunner

    personas_arg: list[str] | None = [persona_id] if persona_id else None

    logger.info(
        "[cycle-198-spike] starting Path γ explore: example=%s persona=%s",
        example_name,
        persona_id or "<auto-pick>",
    )

    try:
        async with ModeRunner(
            mode_spec=get_mode("a"),
            project_root=example_root,
            personas=personas_arg,
            db_policy="preserve",
        ) as conn:
            outcome = await run_explore_strategy(
                conn,
                example_root=example_root,
                strategy=Strategy.MISSING_CONTRACTS,
                personas=personas_arg,
                mcp_session=mcp_session,
                use_tool_calls=False,
            )
    except Exception as e:  # noqa: BLE001 — spike needs the full failure context
        logger.exception("[cycle-198-spike] strategy run failed")
        return json.dumps(
            {
                "error": f"strategy run failed: {e}",
                "error_type": type(e).__name__,
                "spike": "cycle-198-path-gamma",
            },
            indent=2,
        )

    return json.dumps(
        {
            "spike": "cycle-198-path-gamma",
            "example": example_name,
            "persona_arg": persona_id,
            "strategy": outcome.strategy,
            "summary": outcome.summary,
            "degraded": outcome.degraded,
            "proposals": outcome.proposals,
            "findings": outcome.findings,
            "blocked_personas": [
                {"persona_id": pid, "reason": r} for (pid, r) in outcome.blocked_personas
            ],
            "steps_run": outcome.steps_run,
            "tokens_used": outcome.tokens_used,
            "raw_proposals_by_persona": outcome.raw_proposals_by_persona,
            # Cycle 198 spike diagnostic — per-persona outcome + transcript error
            "per_persona_results": outcome.per_persona_results,
        },
        indent=2,
    )
