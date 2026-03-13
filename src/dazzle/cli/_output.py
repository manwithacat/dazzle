"""Shared CLI output formatting for MCP-migrated commands."""

from __future__ import annotations

import json


def format_output(result: dict, *, as_json: bool = False) -> str:
    """Format a handler result dict for terminal output."""
    if as_json:
        return json.dumps(result, indent=2, default=str)

    lines: list[str] = []
    for key, value in result.items():
        if isinstance(value, (list, dict)):
            lines.append(f"{key}:")
            lines.append(json.dumps(value, indent=2, default=str))
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)
