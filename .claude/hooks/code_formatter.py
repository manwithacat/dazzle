#!/usr/bin/env python3
"""PostToolUse hook: `ruff format` edited Python files with the repo venv's ruff.

Only Python. The repo has no JS/TS formatter configured (no prettier config in
Dazzle or HaTchi-MaXchi), and `npx prettier` would try to download one.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_io import (  # noqa: E402
    EDIT_TOOLS,
    file_path_from,
    safe_main,
    tool_input,
    tool_name,
    venv_tool,
)


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    if tool_name(input_data) not in EDIT_TOOLS:
        sys.exit(0)

    file_path = file_path_from(tool_input(input_data))
    path = Path(file_path) if file_path else None
    if path is None or path.suffix.lower() != ".py" or not path.exists():
        sys.exit(0)

    try:
        result = subprocess.run(
            [venv_tool("ruff"), "format", "--quiet", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            print(f"ruff format warning: {result.stderr[:200]}", file=sys.stderr)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    sys.exit(0)


if __name__ == "__main__":
    safe_main(main)
