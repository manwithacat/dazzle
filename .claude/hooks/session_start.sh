#!/bin/bash
# SessionStart hook: Environment setup for Dazzle development
#
# This hook runs at the start of each Claude Code session and:
# 1. Ensures the Python virtual environment is activated
# 2. Validates the Dazzle installation
# 3. Injects useful context for the session

set -e

# Get project directory
PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$PROJECT_DIR"

# Check for virtual environment
if [ -d ".venv" ]; then
    source .venv/bin/activate 2>/dev/null || true
fi

# Verify dazzle is available
if ! command -v dazzle &> /dev/null; then
    echo "Warning: dazzle CLI not found in PATH" >&2
    exit 0  # Non-blocking
fi

# Quick validation of the project
if [ -f "dazzle.yaml" ]; then
    if ! dazzle validate --quiet 2>/dev/null; then
        echo "Note: DSL validation issues detected. Run 'dazzle validate' for details."
    fi
fi

# Inject context about the environment
if [ -n "$CLAUDE_ENV_FILE" ]; then
    # Export any needed environment variables
    echo "DAZZLE_PROJECT_ROOT=$PROJECT_DIR" >> "$CLAUDE_ENV_FILE"
fi

# Success message (shown in verbose mode)
echo "Dazzle environment initialized"
exit 0
