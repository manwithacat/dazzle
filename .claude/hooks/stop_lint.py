#!/usr/bin/env python3
"""Stop hook: Batch lint check on modified Python files at end of turn.

Runs ruff check on any unstaged Python files that were modified during the
session. Reports issues as additionalContext so Claude sees them next turn.
"""

import json
import subprocess
import sys
from pathlib import Path


def _get_modified_py_files(cwd: Path) -> list[str]:
    """Get Python files with unstaged changes."""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACM"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []
        return [
            f
            for f in result.stdout.strip().splitlines()
            if f.endswith(".py") and (cwd / f).exists()
        ]
    except Exception:
        return []


def main():
    try:
        json.load(sys.stdin)
    except json.JSONDecodeError:
        pass

    project_dir = Path.cwd()
    py_files = _get_modified_py_files(project_dir)

    if not py_files:
        sys.exit(0)

    # Batch lint all modified Python files
    try:
        result = subprocess.run(
            ["ruff", "check", "--no-fix", "--output-format=concise"] + py_files,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        sys.exit(0)

    if result.returncode != 0 and result.stdout.strip():
        issues = result.stdout.strip()
        # Cap output to avoid flooding context
        lines = issues.splitlines()
        if len(lines) > 15:
            issues = "\n".join(lines[:15]) + f"\n... and {len(lines) - 15} more issues"

        output = {
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": f"Lint issues in modified files:\n{issues}",
            }
        }
        print(json.dumps(output))

    sys.exit(0)


if __name__ == "__main__":
    main()
