#!/usr/bin/env python3
"""SubagentStart hook: inject a short, always-correct orientation line.

Subagents already receive the project instructions (.claude/CLAUDE.md →
AGENTS.md). This hook only adds live state that AGENTS.md cannot carry:
branch, dirty files, and the toolchain rule. It deliberately does NOT scan
DSL files or enumerate MCP tools — those lists went stale (wrong extension,
root is not a Dazzle project) and cost ~0.7s per subagent.
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
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    dirty = [ln for ln in _git(root, "status", "--porcelain").splitlines() if ln.strip()]

    parts = [
        f"Dazzle framework repo (branch: {branch}; {len(dirty)} dirty path(s)).",
        "Toolchain: uv only — `.venv/bin` is first on PATH, so bare `dazzle`, `ruff`, "
        "`pytest`, `python` are the repo venv. Never pip/pyenv. The repo root is NOT a "
        "Dazzle project: pass `-p examples/<app>` to `dazzle validate|lint`.",
        "Before inventing structure read stems/INDEX.md; commands and gates are in AGENTS.md.",
    ]
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SubagentStart",
                    "additionalContext": "\n".join(parts),
                }
            }
        )
    )
    sys.exit(0)


if __name__ == "__main__":
    safe_main(main)
