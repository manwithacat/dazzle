"""Shared helpers for Claude/Grok project hooks.

Grok sends camelCase keys (toolName, toolInput); Claude Code uses snake_case
(tool_name, tool_input). Accept both. Tool names also differ (Bash vs
run_terminal_command; Edit/Write vs search_replace/write).
"""

from __future__ import annotations

from typing import Any

# Edit/write family — PreToolUse matcher Edit|Write maps to these under Grok
EDIT_TOOLS = frozenset(
    {
        "Edit",
        "Write",
        "MultiEdit",
        "search_replace",
        "write",
        "StrReplace",
        "Create",
        "create",
    }
)

BASH_TOOLS = frozenset({"Bash", "run_terminal_command", "bash", "Shell"})


def tool_name(data: dict[str, Any]) -> str:
    return str(data.get("tool_name") or data.get("toolName") or "")


def tool_input(data: dict[str, Any]) -> dict[str, Any]:
    raw = data.get("tool_input") if "tool_input" in data else data.get("toolInput")
    return raw if isinstance(raw, dict) else {}


def file_path_from(inp: dict[str, Any]) -> str:
    return str(
        inp.get("file_path")
        or inp.get("filePath")
        or inp.get("path")
        or inp.get("target_file")
        or ""
    )
