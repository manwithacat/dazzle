"""Common helpers for MCP handler functions.

Eliminates repeated boilerplate across handler files:
- DSL loading (manifest → discover → parse → appspec)
- Progress context extraction
- Error-as-JSON wrapping
- Timeout-protected execution
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from functools import wraps
from typing import Any, TypeVar

from dazzle.core.appspec_loader import load_project_appspec

from ..progress import ProgressContext
from ..progress import noop as _noop_progress

_T = TypeVar("_T")

logger = logging.getLogger("dazzle.mcp")

# Default per-step timeout in seconds.  Individual callers can override.
DEFAULT_STEP_TIMEOUT: float = 120.0

# Re-export so existing `from .common import load_project_appspec` works
__all__ = [
    "DEFAULT_STEP_TIMEOUT",
    "error_response",
    "extract_progress",
    "load_project_appspec",
    "run_with_timeout",
    "unknown_op_response",
    "wrap_handler_errors",
]


def error_response(msg: str) -> str:
    """Return a JSON error response string."""
    return json.dumps({"error": msg})


def unknown_op_response(operation: str | None, tool: str) -> str:
    """Return a JSON error for an unknown operation."""
    return json.dumps({"error": f"Unknown {tool} operation: {operation}"})


def extract_progress(args: dict[str, Any] | None) -> ProgressContext:
    """Extract progress context from handler args, falling back to noop."""
    return (args.get("_progress") if args else None) or _noop_progress()


def wrap_handler_errors(
    fn: Callable[..., str],
) -> Callable[..., str]:
    """Decorator that wraps handler exceptions into JSON error responses.

    Catches Exception, logs it, and returns ``{"error": "<message>"}``.
    The wrapped function must accept ``project_root`` as its first argument.
    """

    @wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            logger.debug("Handler %s failed: %s", fn.__name__, e, exc_info=True)
            return json.dumps({"error": str(e)}, indent=2)

    return wrapper


def wrap_async_handler_errors(
    fn: Callable[..., Any],
) -> Callable[..., Any]:
    """Async variant of :func:`wrap_handler_errors`.

    Wraps an ``async def`` handler so that any unhandled exception is caught,
    logged, and returned as ``{"error": "<message>"}``.
    """

    @wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> str:
        try:
            result: str = await fn(*args, **kwargs)
            return result
        except Exception as e:
            logger.debug("Handler %s failed: %s", fn.__name__, e, exc_info=True)
            return json.dumps({"error": str(e)}, indent=2)

    return wrapper


# Backward-compatible aliases
handler_error_json = wrap_handler_errors
async_handler_error_json = wrap_async_handler_errors


# ---------------------------------------------------------------------------
# Timeout-protected execution
# ---------------------------------------------------------------------------

# Shared single-thread pool for timeout wrapping.  Using a single worker
# prevents spawning a new thread per call while still allowing the main
# thread to enforce a wall-clock deadline via Future.result(timeout).
_timeout_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mcp-timeout")


def run_with_timeout(
    fn: Callable[..., _T],
    args: tuple[Any, ...] = (),
    kwargs: dict[str, Any] | None = None,
    *,
    timeout: float = DEFAULT_STEP_TIMEOUT,
    label: str = "",
) -> _T:
    """Run *fn* in a worker thread with a wall-clock timeout.

    If the function does not return within *timeout* seconds, raises
    ``TimeoutError`` with a descriptive message.  This prevents any
    single handler from blocking the MCP event loop indefinitely.

    Args:
        fn: Callable to execute.
        args: Positional arguments for *fn*.
        kwargs: Keyword arguments for *fn*.
        timeout: Maximum seconds to wait.
        label: Human-readable label for error messages.

    Returns:
        The return value of *fn*.

    Raises:
        TimeoutError: If *fn* does not complete within *timeout* seconds.
    """
    if kwargs is None:
        kwargs = {}
    fut = _timeout_pool.submit(fn, *args, **kwargs)
    try:
        return fut.result(timeout=timeout)
    except FuturesTimeoutError:
        fut.cancel()
        name = label or getattr(fn, "__name__", str(fn))
        raise TimeoutError(f"MCP handler '{name}' timed out after {timeout:.0f}s") from None
