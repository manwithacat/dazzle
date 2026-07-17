"""#1617 MCP thin wrapper — representation decide / classify / prove.

Logic in ``dazzle.representation`` (no circular MCP deps).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dazzle.mcp.server.handlers.common import (
    error_response,
    wrap_handler_errors,
)
from dazzle.representation import (
    classify_project,
    decide_representation,
    list_patterns,
    prove_representation_project,
)


@wrap_handler_errors
def representation_patterns_handler(_project_root: Path, _args: dict[str, Any]) -> str:
    return json.dumps({"ok": True, "patterns": list_patterns()}, indent=2, default=str)


@wrap_handler_errors
def representation_decide_handler(_project_root: Path, args: dict[str, Any]) -> str:
    text = args.get("text")
    signals = args.get("signals")
    if isinstance(signals, str):
        try:
            signals = json.loads(signals)
        except json.JSONDecodeError:
            return error_response("signals must be a JSON object")
    if not text and not signals:
        return error_response("provide text and/or signals")
    return json.dumps(
        decide_representation(text=text, signals=signals if isinstance(signals, dict) else None),
        indent=2,
        default=str,
    )


@wrap_handler_errors
def representation_classify_handler(project_root: Path, _args: dict[str, Any]) -> str:
    return json.dumps(classify_project(project_root), indent=2, default=str)


@wrap_handler_errors
def representation_prove_handler(project_root: Path, _args: dict[str, Any]) -> str:
    return json.dumps(prove_representation_project(project_root), indent=2, default=str)


def handle_representation(arguments: dict[str, Any]) -> str:
    """Dispatch representation tool operations.

    ``patterns`` / ``decide`` do not require a project path; ``classify`` /
    ``prove`` do. Does not import handlers_consolidated (import cycle).
    """
    op = arguments.get("operation") or "patterns"
    root_raw = (
        arguments.get("project_root")
        or arguments.get("_resolved_project_path")
        or arguments.get("project_path")
    )
    if op in ("patterns", "decide"):
        root = Path(root_raw) if root_raw else Path(".")
        if op == "patterns":
            return representation_patterns_handler(root, arguments)
        return representation_decide_handler(root, arguments)

    if root_raw is None:
        return error_response("project path required for classify/prove")
    project_path = Path(root_raw)
    if op == "classify":
        return representation_classify_handler(project_path, arguments)
    if op == "prove":
        return representation_prove_handler(project_path, arguments)
    return error_response(f"Unknown representation operation: {op}")
