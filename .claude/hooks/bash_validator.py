#!/usr/bin/env python3
"""PreToolUse hook: Block dangerous bash commands and rewrite dazzle commands.

Hard-blocks destructive operations. Rewrites bare `dazzle` commands to
`python -m dazzle` to avoid PATH issues (input-modifying hook, v2.0.10+).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _hook_io import BASH_TOOLS, safe_main, tool_input, tool_name  # noqa: E402

# Absolute-path deletes under /tmp, $HOME, project dirs are allowed; only
# filesystem root and shell globs are hard-blocked (the old `\s+/` pattern
# false-positived on `rm -rf /tmp/...` and similar agent cleanup).
BLOCK_RULES = [
    (r"\brm\s+-rf\s+/\s*$", "Dangerous: Recursive delete of filesystem root"),
    (r"\brm\s+-rf\s+/\*", "Dangerous: Recursive wildcard delete from root"),
    (r"\brm\s+-rf\s+\*(?:\s|$)", "Dangerous: Recursive wildcard delete"),
    (r">\s*/dev/sd[a-z]", "Dangerous: Writing to block device"),
]

DAZZLE_BARE_RE = re.compile(r"(?<!-m )(?<!\w)dazzle\b")
ALREADY_MODULE_RE = re.compile(r"python[3]?\s+-m\s+dazzle\b")


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    if tool_name(input_data) not in BASH_TOOLS:
        sys.exit(0)

    inp = tool_input(input_data)
    command = str(inp.get("command") or "")
    if not command:
        sys.exit(0)

    for pattern, message in BLOCK_RULES:
        if re.search(pattern, command):
            print(f"BLOCKED: {message}", file=sys.stderr)
            sys.exit(2)

    if DAZZLE_BARE_RE.search(command) and not ALREADY_MODULE_RE.search(command):
        new_command = DAZZLE_BARE_RE.sub("python -m dazzle", command)
        # Claude Code: dump updated tool_input on stdout (input-modifying hook).
        # Grok: decision+updatedInput is also recognized; include both shapes.
        updated = {**inp, "command": new_command}
        print(
            json.dumps(
                {
                    "decision": "allow",
                    "updatedInput": updated,
                    **updated,  # Claude legacy: top-level tool_input fields
                }
            )
        )
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    safe_main(main)
