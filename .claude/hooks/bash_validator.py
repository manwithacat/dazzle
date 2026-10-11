#!/usr/bin/env python3
"""PreToolUse hook: block destructive bash commands.

Hard-blocks a short list of catastrophic shell patterns. Everything else is
allowed unchanged. (The former bare-`dazzle` → `python -m dazzle` rewrite was
removed: it corrupted paths such as `src/dazzle/` and `.dazzle/`, and the
SessionStart hook now puts `.venv/bin` first on PATH so bare `dazzle` is the
repo's own CLI.)
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
    (
        r"\bgit\s+push\s+(?:\S+\s+)*--force\b(?!-with-lease)",
        "Dangerous: force push (use --force-with-lease)",
    ),
]


def main() -> None:
    try:
        input_data = json.load(sys.stdin)
    except json.JSONDecodeError:
        sys.exit(0)

    if tool_name(input_data) not in BASH_TOOLS:
        sys.exit(0)

    command = str(tool_input(input_data).get("command") or "")
    if not command:
        sys.exit(0)

    for pattern, message in BLOCK_RULES:
        if re.search(pattern, command):
            print(f"BLOCKED: {message}", file=sys.stderr)
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    safe_main(main)
