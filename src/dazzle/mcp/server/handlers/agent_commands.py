"""MCP handler for agent_commands tool — read-only operations.

Operations: list, get, check_updates.
File writing is handled by `dazzle agent sync` CLI (ADR-0002).
"""

import json
import logging
from pathlib import Path
from typing import Any

from dazzle.cli.agent_commands.loader import load_all_commands
from dazzle.cli.agent_commands.renderer import (
    build_project_context,
    evaluate_maturity,
    render_skill,
)

logger = logging.getLogger(__name__)
COMMANDS_VERSION = "1.0.0"


def handle_list(project_path: Path, args: dict[str, Any]) -> str:
    ctx = build_project_context(project_path)
    all_commands = load_all_commands()
    commands_out = []
    for cmd in all_commands:
        available, reason = evaluate_maturity(cmd.maturity, ctx)
        commands_out.append(
            {
                "name": cmd.name,
                "version": cmd.version,
                "title": cmd.title,
                "pattern": cmd.pattern,
                "description": cmd.description,
                "available": available,
                "reason": reason,
            }
        )
    from dazzle import __version__ as dazzle_version

    return json.dumps(
        {
            "commands": commands_out,
            "dazzle_version": dazzle_version,
            "commands_version": COMMANDS_VERSION,
        },
        indent=2,
    )


def handle_get(project_path: Path, args: dict[str, Any]) -> str:
    command_name = args.get("command", "")
    ctx = build_project_context(project_path)
    all_commands = load_all_commands()
    cmd = next((c for c in all_commands if c.name == command_name), None)
    if cmd is None:
        return json.dumps({"error": f"Unknown command: {command_name}"}, indent=2)
    available, reason = evaluate_maturity(cmd.maturity, ctx)
    content = render_skill(cmd, ctx) if cmd.template_file else ""
    return json.dumps(
        {
            "name": cmd.name,
            "version": cmd.version,
            "available": available,
            "reason": reason,
            "content": content,
        },
        indent=2,
    )


def handle_check_updates(project_path: Path, args: dict[str, Any]) -> str:
    local_version = args.get("commands_version", "0.0.0")
    up_to_date = local_version == COMMANDS_VERSION
    result: dict[str, Any] = {
        "up_to_date": up_to_date,
        "commands_version": COMMANDS_VERSION,
        "local_version": local_version,
    }
    if not up_to_date:
        result["action"] = "Run `dazzle agent sync` to update agent commands."
    return json.dumps(result, indent=2)
