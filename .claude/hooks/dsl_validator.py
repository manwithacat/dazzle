#!/usr/bin/env python3
"""PostToolUse hook: Auto-validate DSL after editing .dsl / .dazzle files.

Runs `dazzle validate` in the nearest project root (dazzle.toml).
Provides feedback if validation fails; never blocks the edit (exit 0).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def _project_root(start: Path) -> Path | None:
    """Walk up from the edited file to the app root that owns dazzle.toml."""
    for parent in [start.parent, *start.parents]:
        if (parent / "dazzle.toml").exists() or (parent / "dazzle.yaml").exists():
            return parent
    return None


def _dazzle_cmd(project_root: Path) -> list[str]:
    """Prefer project/venv dazzle over bare PATH."""
    env_root = os.environ.get("CLAUDE_PROJECT_DIR") or os.environ.get("GROK_WORKSPACE_ROOT")
    candidates = []
    if env_root:
        candidates.append(Path(env_root) / ".venv" / "bin" / "python")
    candidates.append(project_root / ".venv" / "bin" / "python")
    for py in candidates:
        if py.is_file() and os.access(py, os.X_OK):
            return [str(py), "-m", "dazzle", "validate"]
    return ["python3", "-m", "dazzle", "validate"]


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from _hook_io import EDIT_TOOLS, file_path_from
    from _hook_io import tool_input as _ti
    from _hook_io import tool_name as _tn

    if _tn(input_data) not in EDIT_TOOLS:
        sys.exit(0)

    file_path = file_path_from(_ti(input_data))
    if not (file_path.endswith(".dazzle") or file_path.endswith(".dsl")):
        sys.exit(0)

    path = Path(file_path).resolve()
    project_root = _project_root(path)
    if not project_root:
        sys.exit(0)

    try:
        result = subprocess.run(
            _dazzle_cmd(project_root),
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"DSL validate skipped: {exc}", file=sys.stderr)
        sys.exit(0)

    if result.returncode != 0:
        error_msg = (result.stderr or result.stdout or "").strip()
        print(
            f"DSL validation failed after editing {path.name}:\n{error_msg}",
            file=sys.stderr,
        )
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": f"DSL validation error - please fix: {error_msg[:500]}",
            }
        }
        print(json.dumps(output))

    sys.exit(0)


if __name__ == "__main__":
    main()
