#!/usr/bin/env python3
"""PreToolUse hook: Block dangerous bash commands and rewrite dazzle commands.

Hard-blocks destructive operations. Rewrites bare `dazzle` commands to
`python -m dazzle` to avoid PATH issues (input-modifying hook, v2.0.10+).
"""

import json
import re
import sys

BLOCK_RULES = [
    (r"\brm\s+-rf\s+/", "Dangerous: Recursive delete from root"),
    (r"\brm\s+-rf\s+\*", "Dangerous: Recursive wildcard delete"),
    (r">\s*/dev/sd[a-z]", "Dangerous: Writing to block device"),
]

# Match bare `dazzle` at word boundary but not `python -m dazzle` or `python3 -m dazzle`
DAZZLE_BARE_RE = re.compile(r"(?<!-m )(?<!\w)dazzle\b")
ALREADY_MODULE_RE = re.compile(r"python[3]?\s+-m\s+dazzle\b")


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

    # Check block rules first
    for pattern, message in BLOCK_RULES:
        if re.search(pattern, command):
            print(f"BLOCKED: {message}", file=sys.stderr)
            sys.exit(2)

    # Rewrite bare `dazzle` to `python -m dazzle` if not already
    if DAZZLE_BARE_RE.search(command) and not ALREADY_MODULE_RE.search(command):
        new_command = DAZZLE_BARE_RE.sub("python -m dazzle", command)
        # Output modified tool input as JSON to stdout (input-modifying hook)
        tool_input["command"] = new_command
        json.dump(tool_input, sys.stdout)
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
