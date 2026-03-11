#!/bin/bash
# WorktreeCreate hook: Auto-setup new worktrees for Dazzle development.
#
# When Claude creates a git worktree, this hook:
# 1. Sets up the Python virtual environment
# 2. Installs the project in editable mode
# 3. Validates the dazzle installation

set -e

# Read worktree path from stdin JSON
WORKTREE_PATH=""
if command -v python3 &>/dev/null; then
    WORKTREE_PATH=$(python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    print(data.get('tool_input', {}).get('path', ''))
except Exception:
    pass
" 2>/dev/null)
fi

if [ -z "$WORKTREE_PATH" ] || [ ! -d "$WORKTREE_PATH" ]; then
    exit 0
fi

cd "$WORKTREE_PATH"

# Create and activate venv if not present
if [ ! -d ".venv" ]; then
    python3 -m venv .venv 2>/dev/null || exit 0
fi

source .venv/bin/activate 2>/dev/null || exit 0

# Install in editable mode
if [ -f "pyproject.toml" ]; then
    pip install -e ".[dev]" --quiet 2>/dev/null || pip install -e . --quiet 2>/dev/null || true
fi

# Verify dazzle works
if python -m dazzle --help &>/dev/null; then
    echo "Worktree ready: $WORKTREE_PATH"
else
    echo "Warning: dazzle not available in worktree" >&2
fi

exit 0
