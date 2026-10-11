#!/bin/bash
# WorktreeCreate hook: set up a new git worktree with the uv toolchain.
#
# uv is the only supported local toolchain (AGENTS.md › Dev Setup). Mirrors
# `make dev-install` minus pre-commit. Never pip / venv / pyenv.

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

cd "$WORKTREE_PATH" || exit 0

UV="${HOME}/.local/bin/uv"
if [ ! -x "$UV" ]; then
    UV="$(command -v uv 2>/dev/null)"
fi
if [ -z "$UV" ]; then
    echo "Warning: uv not found; worktree has no venv (see docs/contributing/dev-setup.md)" >&2
    exit 0
fi

if [ -f "pyproject.toml" ]; then
    "$UV" sync --frozen --extra dev --extra llm --extra mcp --extra mobile \
        --extra postgres --extra perf --extra saml --extra lsp --quiet 2>/dev/null \
        || "$UV" sync --frozen --extra dev --quiet 2>/dev/null \
        || true
fi

if [ -x ".venv/bin/python" ] && .venv/bin/python -c "import dazzle" 2>/dev/null; then
    echo "Worktree ready (uv): $WORKTREE_PATH"
else
    echo "Warning: dazzle not importable in worktree venv" >&2
fi

exit 0
