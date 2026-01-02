#!/usr/bin/env python3
"""PreToolUse hook: Protect auto-generated files and sensitive paths.

Blocks modifications to:
- Files marked with AUTO-GENERATED comment
- Lock files (package-lock.json, poetry.lock, etc.)
- .env files with secrets
- .git directory
"""

import json
import sys
from pathlib import Path

PROTECTED_PATTERNS = [
    ".git/",
    ".env",
    ".env.local",
    ".env.production",
    "package-lock.json",
    "poetry.lock",
    "Pipfile.lock",
    "*.key",
    "*.pem",
    "credentials.json",
    "secrets.yaml",
]

AUTO_GENERATED_MARKERS = [
    "# AUTO-GENERATED",
    "// AUTO-GENERATED",
    "/* AUTO-GENERATED",
    "<!-- AUTO-GENERATED",
]


def is_protected_path(file_path: str) -> str | None:
    """Check if path matches protected patterns. Returns reason if protected."""
    path_lower = file_path.lower()

    for pattern in PROTECTED_PATTERNS:
        if pattern.startswith("*"):
            if path_lower.endswith(pattern[1:]):
                return f"Protected file type: {pattern}"
        elif pattern in path_lower:
            return f"Protected path: {pattern}"

    return None


def is_auto_generated(file_path: str) -> bool:
    """Check if file is marked as auto-generated."""
    try:
        path = Path(file_path)
        if not path.exists():
            return False

        # Read first 10 lines to check for marker
        with open(path, encoding="utf-8", errors="ignore") as f:
            for i, line in enumerate(f):
                if i >= 10:
                    break
                for marker in AUTO_GENERATED_MARKERS:
                    if marker in line:
                        return True
    except Exception:
        pass

    return False


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

    # Check path traversal
    if ".." in file_path:
        print("Path traversal blocked", file=sys.stderr)
        sys.exit(2)

    # Check protected patterns
    reason = is_protected_path(file_path)
    if reason:
        print(f"BLOCKED: {reason}", file=sys.stderr)
        sys.exit(2)

    # Check auto-generated (only for Edit, not Write to new file)
    if tool_name == "Edit" and is_auto_generated(file_path):
        print("BLOCKED: File is marked as AUTO-GENERATED. Do not edit directly.", file=sys.stderr)
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
