#!/usr/bin/env python3
"""SubagentStop hook: Validate files modified by subagents.

Checks if the subagent modified any Python files and runs a quick ruff check.
Reports issues as additionalContext so the parent agent sees them.
"""

import json
import subprocess
import sys
from pathlib import Path


def _get_recent_modified_py(cwd: Path) -> list[str]:
    """Get Python files modified in the last 2 minutes (likely by subagent)."""
    try:
        result = subprocess.run(
            ["find", str(cwd / "src"), "-name", "*.py", "-mmin", "-2", "-type", "f"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []
        return [f for f in result.stdout.strip().splitlines() if f][:20]
    except Exception:
        return []


def main():
    try:
        json.load(sys.stdin)
    except json.JSONDecodeError:
        pass

    project_dir = Path.cwd()
    py_files = _get_recent_modified_py(project_dir)

    if not py_files:
        sys.exit(0)

    try:
        result = subprocess.run(
            ["ruff", "check", "--no-fix", "--output-format=concise"] + py_files,
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        sys.exit(0)

    if result.returncode != 0 and result.stdout.strip():
        issues = result.stdout.strip()
        lines = issues.splitlines()
        if len(lines) > 10:
            issues = "\n".join(lines[:10]) + f"\n... and {len(lines) - 10} more"

        output = {
            "hookSpecificOutput": {
                "hookEventName": "SubagentStop",
                "additionalContext": f"Subagent lint issues:\n{issues}",
            }
        }
        print(json.dumps(output))

    sys.exit(0)


if __name__ == "__main__":
    main()
