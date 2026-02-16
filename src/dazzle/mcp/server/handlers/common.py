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
from pathlib import Path
from typing import Any

from dazzle.core.fileset import discover_dsl_files
from dazzle.core.ir.appspec import AppSpec
from dazzle.core.linker import build_appspec
from dazzle.core.manifest import load_manifest
from dazzle.core.parser import parse_modules

from ..progress import ProgressContext
from ..progress import noop as _noop_progress

logger = logging.getLogger("dazzle.mcp")


def extract_progress(args: dict[str, Any] | None) -> ProgressContext:
    """Extract progress context from handler args, falling back to noop."""
    return (args.get("_progress") if args else None) or _noop_progress()


def load_project_appspec(project_root: Path) -> AppSpec:
    """Load and return the fully-linked AppSpec for a project.

    Combines the four-step boilerplate: manifest → discover → parse → build.
    """
    manifest = load_manifest(project_root / "dazzle.toml")
    dsl_files = discover_dsl_files(project_root, manifest)
    modules = parse_modules(dsl_files)
    return build_appspec(modules, manifest.project_root)


def handler_error_json(
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


def async_handler_error_json(
    fn: Callable[..., Any],
) -> Callable[..., Any]:
    """Async variant of :func:`handler_error_json`.

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
