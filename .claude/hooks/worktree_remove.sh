#!/usr/bin/env bash
# WorktreeRemove hook: delete the worktree directory AND its branch (the harness
# deletes neither when a hook is configured). stdin JSON carries `worktree_path`.
set -euo pipefail
INPUT="$(cat)"
DIR="$(printf '%s' "$INPUT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("worktree_path",""))' 2>/dev/null || true)"
[[ -n "$DIR" && -d "$DIR" ]] || exit 0
ROOT="${CLAUDE_PROJECT_DIR:-$(git -C "$DIR" rev-parse --git-common-dir | xargs dirname)}"
BRANCH="worktree-$(basename "$DIR")"
git -C "$ROOT" worktree remove --force "$DIR" >&2 2>/dev/null || rm -rf "$DIR"
git -C "$ROOT" worktree prune >&2 2>/dev/null || true
git -C "$ROOT" branch -D "$BRANCH" >&2 2>/dev/null || true
exit 0
