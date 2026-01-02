#!/usr/bin/env python3
"""PreToolUse hook: Validate bash commands for Dazzle best practices.

Suggests better alternatives for common patterns:
- Use rg instead of grep for faster searches
- Use dazzle CLI commands instead of manual operations
- Prevent destructive operations
"""

import json
import re
import sys

VALIDATION_RULES = [
    # Pattern, message, severity (block/warn)
    (r"\bgrep\s+-r\b", "Consider using 'rg' (ripgrep) for faster recursive searches", "warn"),
    (r"\bfind\s+\S+\s+-name\b", "Consider using 'rg --files -g' for faster file searches", "warn"),
    (r"\brm\s+-rf\s+/", "Dangerous: Recursive delete from root", "block"),
    (r"\brm\s+-rf\s+\*", "Dangerous: Recursive wildcard delete", "block"),
    (r">\s*/dev/sd[a-z]", "Dangerous: Writing to block device", "block"),
    (r"\bsudo\b", "Avoid sudo in automated contexts", "warn"),
    (r"\bkill\s+-9\b", "Consider graceful shutdown before SIGKILL", "warn"),
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

    warnings = []
    blocks = []

    for pattern, message, severity in VALIDATION_RULES:
        if re.search(pattern, command):
            if severity == "block":
                blocks.append(message)
            else:
                warnings.append(message)

    if blocks:
        for msg in blocks:
            print(f"BLOCKED: {msg}", file=sys.stderr)
        sys.exit(2)

    if warnings:
        # Provide warnings as context but don't block
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "permissionDecisionReason": "Allowed with suggestions: " + "; ".join(warnings),
            }
        }
        print(json.dumps(output))

    sys.exit(0)


if __name__ == "__main__":
    main()
