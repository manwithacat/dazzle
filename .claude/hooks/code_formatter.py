#!/usr/bin/env python3
"""PostToolUse hook: Auto-format code after editing Python/JS files.

Runs appropriate formatter based on file extension:
- Python: ruff format
- JavaScript: prettier (if available)
"""

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

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    if tool_name not in ("Edit", "Write"):
        sys.exit(0)

    file_path = tool_input.get("file_path", "")
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
