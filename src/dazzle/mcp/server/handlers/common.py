"""Common helpers for MCP handler functions.

Eliminates repeated boilerplate across handler files:
- DSL loading (manifest → discover → parse → appspec)
- Progress context extraction
- Error-as-JSON wrapping
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

from dazzle.core.appspec_loader import load_project_appspec

from ..progress import ProgressContext
from ..progress import noop as _noop_progress

logger = logging.getLogger("dazzle.mcp")

# Re-export so existing `from .common import load_project_appspec` works
__all__ = [
    "error_response",
    "extract_progress",
    "load_project_appspec",
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
