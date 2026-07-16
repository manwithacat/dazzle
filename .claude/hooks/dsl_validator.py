#!/usr/bin/env python3
"""PostToolUse hook: Auto-validate DSL after editing .dazzle files.

Runs `dazzle validate` whenever a .dazzle file is modified.
Provides feedback to Claude if validation fails.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def main():
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
    # Dazzle apps use .dsl more often than legacy .dazzle
    if not (file_path.endswith(".dazzle") or file_path.endswith(".dsl")):
        sys.exit(0)

    # Find project root (where dazzle.yaml lives)
    path = Path(file_path).resolve()
    project_root = None
    for parent in [path.parent] + list(path.parents):
        if (parent / "dazzle.yaml").exists():
            project_root = parent
            break

    if not project_root:
        # Can't find project root, skip validation
        sys.exit(0)

    # Run dazzle validate
    result = subprocess.run(
        ["python", "-m", "dazzle", "validate"],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        # Validation failed - provide feedback to Claude
        error_msg = result.stderr or result.stdout
        print(
            f"DSL validation failed after editing {Path(file_path).name}:\n{error_msg}",
            file=sys.stderr,
        )

        # Return structured output for context
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": f"DSL validation error - please fix: {error_msg[:500]}",
            }
        }
        print(json.dumps(output))
        sys.exit(0)  # Don't block, but provide context

    # Validation passed
    sys.exit(0)


if __name__ == "__main__":
    main()
