#!/usr/bin/env python3
"""SubagentStop hook: `ruff check` Python files modified in the last 2 minutes.

Heuristic for "touched by the subagent". Uses the repo venv's ruff. Reports
as additionalContext so the parent sees issues; never blocks.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_io import project_root, safe_main, venv_tool  # noqa: E402

MAX_LINES = 10


def _recent_py(root: Path) -> list[str]:
    dirs = [str(root / d) for d in ("src", "tests", "scripts") if (root / d).is_dir()]
    if not dirs:
        return []
    try:
        result = subprocess.run(
            ["find", *dirs, "-name", "*.py", "-mmin", "-2", "-type", "f"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []
    return [f for f in result.stdout.strip().splitlines() if f][:50]


def main() -> None:
    try:
        json.load(sys.stdin)
    except json.JSONDecodeError:
        pass

    root = project_root()
    py_files = _recent_py(root)
    if not py_files:
        sys.exit(0)

    try:
        result = subprocess.run(
            [venv_tool("ruff"), "check", "--no-fix", "--output-format=concise", *py_files],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        sys.exit(0)

    if result.returncode != 0 and result.stdout.strip():
        lines = result.stdout.strip().splitlines()
        issues = "\n".join(lines[:MAX_LINES])
        if len(lines) > MAX_LINES:
            issues += f"\n... and {len(lines) - MAX_LINES} more"
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "SubagentStop",
                        "additionalContext": f"Subagent lint issues:\n{issues}",
                    }
                }
            )
        )

    sys.exit(0)


if __name__ == "__main__":
    safe_main(main)
