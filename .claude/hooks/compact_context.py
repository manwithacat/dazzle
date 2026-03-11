#!/usr/bin/env python3
"""PreCompact hook: Preserve critical session state before context compaction.

Injects must-preserve context: current branch, modified files, ralph-loop
state, so that compaction doesn't lose important working state.
"""

import json
import subprocess
import sys
from pathlib import Path


def _get_git_branch(cwd: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else "unknown"
    except Exception:
        return "unknown"


def _get_modified_files(cwd: Path) -> list[str]:
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip().splitlines()[:20]
    except Exception:
        pass
    return []


def _get_ralph_state(project_root: Path) -> str | None:
    state_file = project_root / ".claude" / ".ralph_state"
    try:
        if state_file.exists():
            return state_file.read_text().strip()
    except Exception:
        pass
    return None


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    cwd = Path(input_data.get("cwd", "."))
    project_root = Path.cwd()

    context_parts = [
        f"Branch: {_get_git_branch(cwd)}",
    ]

    modified = _get_modified_files(cwd)
    if modified:
        context_parts.append(f"Modified files: {', '.join(modified)}")

    ralph_state = _get_ralph_state(project_root)
    if ralph_state:
        context_parts.append(f"Ralph-loop iteration: {ralph_state}")

    output = {
        "hookSpecificOutput": {
            "hookEventName": "PreCompact",
            "additionalContext": "SESSION STATE TO PRESERVE:\n" + "\n".join(context_parts),
        }
    }
    print(json.dumps(output))
    sys.exit(0)


if __name__ == "__main__":
    main()
