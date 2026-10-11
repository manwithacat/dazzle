#!/usr/bin/env bash
# WorktreeCreate hook: CREATE the worktree (the harness does not when a hook is
# configured), set it up with the uv toolchain, and print its absolute path as
# the last line of stdout. Everything else goes to stderr.
#
# Contract (code.claude.com/docs/en/hooks#worktreecreate): stdin JSON carries
# `name` (slug) and `cwd`; stdout's last non-empty line is the path.
#
# Worktrees branch from the CURRENT HEAD (not the default branch) so flense
# ships prepared in parallel start from the orchestrator's tip. Layout:
# <repo>/.claude/worktrees/<name> on branch worktree-<name> (gitignored path).
set -euo pipefail

INPUT="$(cat)"
NAME="$(printf '%s' "$INPUT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("name",""))' 2>/dev/null || true)"
CWD="$(printf '%s' "$INPUT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("cwd",""))' 2>/dev/null || true)"
ROOT="${CLAUDE_PROJECT_DIR:-}"
if [[ -z "$ROOT" ]]; then
  ROOT="$(git -C "${CWD:-.}" rev-parse --show-toplevel)"
fi
if [[ -z "$NAME" ]]; then
  NAME="wt-$(date +%s)-$RANDOM"
fi
DIR="$ROOT/.claude/worktrees/$NAME"
BRANCH="worktree-$NAME"

mkdir -p "$ROOT/.claude/worktrees"
if [[ -e "$DIR" ]]; then
  echo "worktree path already exists: $DIR" >&2
  exit 1
fi
git -C "$ROOT" worktree add -b "$BRANCH" "$DIR" HEAD >&2

# uv is the only supported toolchain (AGENTS.md › Dev Setup). Mirror make
# dev-install's extras so make targets and gates work inside the worktree.
UV="${HOME}/.local/bin/uv"
[[ -x "$UV" ]] || UV="$(command -v uv 2>/dev/null || true)"
if [[ -n "$UV" ]]; then
  (cd "$DIR" && "$UV" sync --frozen --extra dev --extra llm --extra mcp --extra mobile \
      --extra postgres --extra perf --extra saml --extra lsp --quiet) >&2 \
    || echo "warning: uv sync failed in $DIR — run it manually" >&2
else
  echo "warning: uv not found; worktree has no venv" >&2
fi

# .worktreeinclude is not processed when a hook is used: carry local env files.
for f in .env .env.local; do
  [[ -f "$ROOT/$f" ]] && cp "$ROOT/$f" "$DIR/$f"
done

echo "worktree ready: $DIR ($BRANCH from $(git -C "$ROOT" rev-parse --short HEAD))" >&2
echo "$DIR"
