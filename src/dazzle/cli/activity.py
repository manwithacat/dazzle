"""CLI activity logging — writes CLI tool invocations to the shared activity store.

Provides a context manager that mirrors what ``dispatch_consolidated_tool()``
does for MCP: logs ``tool_start``, yields a :class:`ProgressContext`, and
logs ``tool_end`` with timing and success/error information.

Usage::

    from dazzle.cli.activity import cli_activity

    with cli_activity(root, "pipeline", "run") as progress:
        args["_progress"] = progress
        result = run_pipeline_handler(root, args)
"""

from __future__ import annotations

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dazzle.mcp.server.progress import ProgressContext

logger = logging.getLogger("dazzle.cli.activity")


@contextmanager
def cli_activity(
    root: Path,
    tool: str,
    operation: str | None = None,
) -> Generator[ProgressContext, None, None]:
    """Context manager that logs CLI activity to the shared activity store.

    Initialises the knowledge graph and activity store (both idempotent),
    creates a :class:`ProgressContext` with ``source="cli"``, and bookends
    the wrapped block with ``tool_start`` / ``tool_end`` events.

    The yielded :class:`ProgressContext` has a ``result_context`` dict that
    callers can populate before the block exits.  The dict is serialised as
    ``context_json`` on the ``tool_end`` event so the workshop can display
    structured result annotations (e.g. test pass/fail counts).

    Args:
        root: Project root directory (must contain ``dazzle.toml``).
        tool: Consolidated tool name (e.g. ``"pipeline"``).
        operation: Operation within the tool (e.g. ``"run"``).

    Yields:
        A :class:`ProgressContext` that handlers can use for progress updates.
    """
    from dazzle.mcp.server.progress import ProgressContext
    from dazzle.mcp.server.state import (
        get_activity_store,
        get_knowledge_graph,
        init_activity_store,
        init_knowledge_graph,
    )

    # Idempotent init — reuses existing globals if already set up
    if get_knowledge_graph() is None:
        try:
            init_knowledge_graph(root)
        except Exception:
            logger.debug("KG init failed in CLI activity", exc_info=True)

    if get_activity_store() is None:
        try:
            init_activity_store(root)
        except Exception:
            logger.debug("Activity store init failed in CLI activity", exc_info=True)

    activity_store = get_activity_store()

    progress = ProgressContext(
        session=None,
        activity_store=activity_store,
        tool_name=tool,
        operation=operation,
        source="cli",
    )

    # Log tool_start
    if activity_store is not None:
        try:
            activity_store.log_event("tool_start", tool, operation, source="cli")
        except Exception:
            pass

    t0 = time.monotonic()
    call_ok = True
    call_error: str | None = None

    try:
        yield progress
    except Exception:
        call_ok = False
        import traceback

        call_error = traceback.format_exc()[-500:]
        raise
    finally:
        duration_ms = (time.monotonic() - t0) * 1000

        # Serialise result_context if populated
        ctx_json: str | None = None
        if progress.result_context:
            import json

            try:
                ctx_json = json.dumps(progress.result_context)
            except Exception:
                pass

        if activity_store is not None:
            try:
                activity_store.log_event(
                    "tool_end",
                    tool,
                    operation,
                    success=call_ok,
                    duration_ms=duration_ms,
                    error=call_error,
                    context_json=ctx_json,
                    source="cli",
                )
            except Exception:
                pass
