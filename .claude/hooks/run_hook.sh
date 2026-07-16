#!/usr/bin/env bash
# Run a project hook with the repo venv Python when present, else python3.
# Usage: run_hook.sh <script_name.py>
# Relies on CLAUDE_PROJECT_DIR / GROK_WORKSPACE_ROOT (Grok sets both).
set -euo pipefail
ROOT="${CLAUDE_PROJECT_DIR:-${GROK_WORKSPACE_ROOT:-}}"
if [[ -z "$ROOT" ]]; then
  ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
fi
SCRIPT="$ROOT/.claude/hooks/${1:?hook script name required}"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  exec "$ROOT/.venv/bin/python" "$SCRIPT"
fi
exec python3 "$SCRIPT"
