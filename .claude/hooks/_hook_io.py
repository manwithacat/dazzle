"""Shared helpers for Claude/Grok project hooks.

Grok sends camelCase keys (toolName, toolInput); Claude Code uses snake_case
(tool_name, tool_input). Accept both. Tool names also differ (Bash vs
run_terminal_command; Edit/Write vs search_replace/write).

Exit contract (harness-visible):
  0 — allow / success
  2 — explicit deny (PreToolUse only)
  other — fail-open: tool still runs, but Grok/Claude log
          ``pre_tool_use[N] failed with exit code N`` spam.

Never let uncaught exceptions become exit 1: use ``safe_main``.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
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


def safe_main(main_fn: Callable[[], None]) -> None:
    """Run a hook entrypoint; convert unexpected errors to exit 0 (fail-open).

    Explicit ``sys.exit(2)`` denials and ``sys.exit(0)`` still propagate.
    Anything else would surface as noisy ``failed with exit code 1`` in the
    harness while still allowing the tool — prefer silent fail-open.
    """
    try:
        main_fn()
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001 — hooks must not crash the harness
        print(f"hook fail-open: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(0)
