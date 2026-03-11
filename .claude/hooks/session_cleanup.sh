#!/bin/bash
# SessionEnd hook: Lightweight cleanup at session end.
#
# - Removes ralph-loop state file
# - Cleans up old temp files
# - Logs session end timestamp

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

# Clean up ralph-loop state
rm -f "$PROJECT_DIR/.claude/.ralph_state"

# Clean up temp directory if it exists (only files older than 60 min)
if [ -d "$PROJECT_DIR/.dazzle/tmp" ]; then
    find "$PROJECT_DIR/.dazzle/tmp" -type f -mmin +60 -delete 2>/dev/null || true
fi

# Log session end
mkdir -p "$PROJECT_DIR/.dazzle"
echo "$(date -Iseconds) session_end" >> "$PROJECT_DIR/.dazzle/session-log.txt"

exit 0
