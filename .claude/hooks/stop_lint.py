#!/usr/bin/env python3
"""Stop hook: batch `ruff check` on Python files changed in the worktree.

Covers unstaged, staged and untracked files (git status), using the repo
venv's ruff so results match `make lint`. Reports as systemMessage; never
blocks the turn.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_io import project_root, safe_main, venv_tool  # noqa: E402

MAX_LINES = 15


def _changed_py_files(cwd: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []
    files: list[str] = []
    for line in result.stdout.splitlines():
        if len(line) < 4 or line[:2] == " D" or line[:2] == "D ":
            continue
        path = line[3:].split(" -> ")[-1].strip()
        if path.endswith(".py") and (cwd / path).exists():
            files.append(path)
    return files[:200]


def main() -> None:
    try:
        json.load(sys.stdin)
    except json.JSONDecodeError:
        pass

    cwd = project_root()
    py_files = _changed_py_files(cwd)
    if not py_files:
        sys.exit(0)

    try:
        result = subprocess.run(
            [venv_tool("ruff"), "check", "--no-fix", "--output-format=concise", *py_files],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        sys.exit(0)

    if result.returncode != 0 and result.stdout.strip():
        lines = result.stdout.strip().splitlines()
        issues = "\n".join(lines[:MAX_LINES])
        if len(lines) > MAX_LINES:
            issues += f"\n... and {len(lines) - MAX_LINES} more issues"
        # Stop-hook schema has no hookSpecificOutput; systemMessage surfaces
        # the warning to the agent without blocking.
        print(json.dumps({"systemMessage": f"Lint issues in modified files:\n{issues}"}))

    sys.exit(0)


if __name__ == "__main__":
    safe_main(main)
