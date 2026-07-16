"""#1605 MCP thin wrapper around ``dazzle.agent_loop`` (pure core).

Logic lives in ``dazzle.agent_loop`` so CLI works without the ``mcp`` extra.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dazzle.agent_loop import build_context, build_playbook, prove_stories
from dazzle.mcp.server.handlers.common import (
    error_response,
    extract_progress,
    wrap_handler_errors,
)


@wrap_handler_errors
def agent_context_handler(project_root: Path, args: dict[str, Any]) -> str:
    progress = extract_progress(args)
    progress.log_sync("Building agent_context…")
    return json.dumps(build_context(project_root), indent=2, default=str)


@wrap_handler_errors
def agent_prove_handler(project_root: Path, args: dict[str, Any]) -> str:
    story_id = args.get("story_id") or args.get("name")
    payload = prove_stories(project_root, story_id=story_id)
    return json.dumps(payload, indent=2, default=str)


@wrap_handler_errors
def agent_playbook_handler(project_root: Path, args: dict[str, Any]) -> str:
    name = (args.get("name") or "domain_logic").strip()
    payload = build_playbook(name)
    if not payload.get("ok"):
        return error_response(str(payload.get("error") or "unknown playbook"))
    return json.dumps(payload, indent=2)


def handle_agent(arguments: dict[str, Any]) -> str:
    """Dispatch agent tool operations (wired from handlers_consolidated)."""
    try:
        from dazzle.mcp.server.handlers_consolidated import _dispatch_project_ops

        return _dispatch_project_ops(
            arguments,
            {
                "context": agent_context_handler,
                "prove": agent_prove_handler,
                "playbook": agent_playbook_handler,
            },
            "agent",
        )
    except Exception:
        op = arguments.get("operation") or "context"
        root = arguments.get("project_root") or arguments.get("_resolved_project_path")
        if root is None:
            return error_response("project path required")
        project_path = Path(root)
        if op == "context":
            return agent_context_handler(project_path, arguments)
        if op == "prove":
            return agent_prove_handler(project_path, arguments)
        if op == "playbook":
            return agent_playbook_handler(project_path, arguments)
        return error_response(f"Unknown agent operation: {op}")
