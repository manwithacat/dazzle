#!/bin/bash
# SessionStart hook: environment setup for Dazzle development.
#
# 1. Puts the repo's uv-managed .venv/bin first on PATH for every later Bash
#    call (via CLAUDE_ENV_FILE), so bare `dazzle`, `ruff`, `pytest`, `python`
#    resolve to the repo toolchain — not pyenv shims or a stale global wrapper.
# 2. Verifies the venv's dazzle imports.
# 3. Exports DAZZLE_PROJECT_ROOT.

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_DIR" || exit 0

VENV_BIN="$PROJECT_DIR/.venv/bin"

if [ -n "$CLAUDE_ENV_FILE" ]; then
    {
        echo "export DAZZLE_PROJECT_ROOT='$PROJECT_DIR'"
        if [ -x "$VENV_BIN/python" ]; then
            echo "export VIRTUAL_ENV='$PROJECT_DIR/.venv'"
            echo "export PATH='$VENV_BIN':\"\$PATH\""
        fi
    } >> "$CLAUDE_ENV_FILE"
fi

if [ ! -x "$VENV_BIN/python" ]; then
    echo "Warning: no .venv — run 'make dev-install' (uv is the only supported toolchain)" >&2
    exit 0
fi

if ! "$VENV_BIN/python" -c "import dazzle" 2>/dev/null; then
    echo "Warning: dazzle not importable from .venv — run 'uv sync'" >&2
    exit 0
fi

echo "Dazzle environment initialized (.venv/bin on PATH)"
exit 0
