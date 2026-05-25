#!/usr/bin/env python3
"""PreToolUse hook: surface counter-priors before Edit/Write to user app code.

Opt-in hook for Claude Code. When the agent is about to Edit or Write a file
under `app/**/*.py`, `app/**/*.sh`, or `scripts/**/*.sh`, this hook runs the
counter-prior catalogue's code_shape matcher against the file path + extension
and prints any matches as a system reminder. Adds zero token cost when no
matches fire.

To install, add to your Claude Code settings.json:

  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "/Volumes/SSD/Dazzle/scripts/hooks/counter-prior-pretooluse.py"
          }
        ]
      }
    ]
  }

The hook reads the tool call's JSON payload from stdin and writes a
system-reminder block (if relevant) to stdout. Exits 0 either way — the hook
is advisory, not gating.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Resolve the catalogue path relative to this script's repo.
REPO_ROOT = Path(__file__).resolve().parents[2]
CATALOGUE_DIR = REPO_ROOT / "docs" / "counter-priors"


def _file_in_user_app_scope(file_path: str) -> bool:
    """Restrict surfacing to user-app code where the host-language counter-priors apply."""
    p = Path(file_path)
    try:
        rel = p.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        # File is outside the Dazzle repo — assume out of scope.
        return False
    if rel.startswith("app/") and (rel.endswith(".py") or rel.endswith(".sh")):
        return True
    if rel.startswith("scripts/") and rel.endswith(".sh"):
        return True
    return False


def _load_catalogue() -> list:
    """Lazy import so the hook doesn't pay catalogue load cost when out of scope."""
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from dazzle.mcp.semantics_kb.counter_priors import load_all_counter_priors

    return load_all_counter_priors()


def _matches_for(entries: list, file_path: str) -> list:
    """Return entries whose triggers_code regex matches the file path.

    We pass the file path itself (not file contents) because the hook fires
    PRE-write — the content isn't available yet. The regexes are sketched to
    catch common path shapes (e.g. `app/sync/.*\\.py`), but the bulk of the
    match signal comes from the agent's `code_shape` parameter when calling
    `knowledge counter_prior` explicitly.
    """
    from dazzle.mcp.semantics_kb.counter_priors import match_code_triggers

    return match_code_triggers(entries, file_path)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool_input = payload.get("tool_input", {})
    file_path = tool_input.get("file_path") or tool_input.get("path") or ""
    if not file_path or not _file_in_user_app_scope(file_path):
        return 0

    try:
        entries = _load_catalogue()
    except Exception:
        return 0

    hits = _matches_for(entries, file_path)
    if not hits:
        return 0

    lines = [
        "<system-reminder>",
        f"Counter-prior catalogue matched {len(hits)} entr{'y' if len(hits) == 1 else 'ies'} "
        f"for {file_path}:",
        "",
    ]
    for entry in hits:
        lines.append(f"  - {entry.id} ({entry.layer}): {entry.name}")
        lines.append(f"    knowledge counter_prior id={entry.id!r} for full guidance")
    lines.append("</system-reminder>")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
