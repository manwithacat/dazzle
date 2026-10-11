#!/usr/bin/env python3
"""PreCompact hook: preserve live working state across context compaction.

Injects branch, the dirty worktree (staged/unstaged/untracked), and the last
commit so the post-compaction context knows where work left off.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_io import project_root, safe_main  # noqa: E402


def _git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=5)
        return result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        return ""


def main() -> None:
    try:
        json.load(sys.stdin)
    except json.JSONDecodeError:
        pass

    root = project_root()
    parts = [f"Branch: {_git(root, 'rev-parse', '--abbrev-ref', 'HEAD') or 'unknown'}"]
    head = _git(root, "log", "-1", "--format=%h %s")
    if head:
        parts.append(f"HEAD: {head}")
    status = _git(root, "status", "--porcelain", "--untracked-files=all").splitlines()
    if status:
        shown = status[:30]
        parts.append("Worktree (git status --porcelain):\n" + "\n".join(shown))
        if len(status) > len(shown):
            parts.append(f"... and {len(status) - len(shown)} more paths")

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreCompact",
                    "additionalContext": "SESSION STATE TO PRESERVE:\n" + "\n".join(parts),
                }
            }
        )
    )
    sys.exit(0)


if __name__ == "__main__":
    safe_main(main)
