"""Runtime parameter MCP handlers — read-only param inspection."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .common import error_response, load_project_appspec, wrap_handler_errors

logger = logging.getLogger("dazzle.mcp")


@wrap_handler_errors
def param_list_handler(project_root: Path, args: dict[str, Any]) -> str:
    """List all declared runtime parameters."""
    appspec = load_project_appspec(project_root)
    params = [p.model_dump(mode="json") for p in getattr(appspec, "params", [])]
    return json.dumps({"params": params, "total": len(params)}, indent=2)


@wrap_handler_errors
def param_get_handler(project_root: Path, args: dict[str, Any]) -> str:
    """Get a specific parameter's DSL declaration + default value.

    Note: MCP tools are stateless reads without tenant context, so this
    returns the declared spec and default — not the runtime-resolved value.
    Use CLI ``dazzle param get --tenant X`` for tenant-specific resolution.
    """
    key = args.get("key", "")
    if not key:
        return error_response("'key' argument is required")
    appspec = load_project_appspec(project_root)
    spec = next((p for p in getattr(appspec, "params", []) if p.key == key), None)
    if spec is None:
        return error_response(f"Unknown param: {key}")
    return json.dumps(spec.model_dump(mode="json"), indent=2)
