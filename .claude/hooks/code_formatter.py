#!/usr/bin/env python3
"""PostToolUse hook: Auto-format code after editing Python/JS files.

Runs appropriate formatter based on file extension:
- Python: ruff format
- JavaScript: prettier (if available)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

FORMATTERS = {
    ".py": ["ruff", "format"],
    ".js": ["npx", "prettier", "--write"],
    ".ts": ["npx", "prettier", "--write"],
    ".jsx": ["npx", "prettier", "--write"],
    ".tsx": ["npx", "prettier", "--write"],
}


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
    if not file_path:
        sys.exit(0)

    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix not in FORMATTERS:
        sys.exit(0)

    if not path.exists():
        sys.exit(0)

    formatter = FORMATTERS[suffix]

    try:
        result = subprocess.run(formatter + [str(path)], capture_output=True, text=True, timeout=30)
        # Silent success - don't clutter output
        if result.returncode != 0:
            # Log error but don't block
            print(f"Formatter warning: {result.stderr[:200]}", file=sys.stderr)
    except FileNotFoundError:
        # Formatter not installed, skip silently
        pass
    except subprocess.TimeoutExpired:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
