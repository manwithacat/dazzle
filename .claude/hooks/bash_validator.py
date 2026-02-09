#!/usr/bin/env python3
"""PreToolUse hook: Block dangerous bash commands.

Hard-blocks destructive operations only. No advisory warnings.
"""

import json
import re
import sys

BLOCK_RULES = [
    (r"\brm\s+-rf\s+/", "Dangerous: Recursive delete from root"),
    (r"\brm\s+-rf\s+\*", "Dangerous: Recursive wildcard delete"),
    (r">\s*/dev/sd[a-z]", "Dangerous: Writing to block device"),
]


def main():
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", {})

    if tool_name != "Bash":
        sys.exit(0)

    command = tool_input.get("command", "")
    if not command:
        sys.exit(0)

    for pattern, message in BLOCK_RULES:
        if re.search(pattern, command):
            print(f"BLOCKED: {message}", file=sys.stderr)
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
