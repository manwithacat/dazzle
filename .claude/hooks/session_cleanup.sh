#!/bin/bash
# SessionEnd hook: lightweight cleanup at session end.
#
# - Removes temp files older than 60 min under .dazzle/tmp
# - Logs the session end timestamp

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

if [ -d "$PROJECT_DIR/.dazzle/tmp" ]; then
    find "$PROJECT_DIR/.dazzle/tmp" -type f -mmin +60 -delete 2>/dev/null || true
fi

mkdir -p "$PROJECT_DIR/.dazzle"
echo "$(date -Iseconds) session_end" >> "$PROJECT_DIR/.dazzle/session-log.txt"

exit 0
