# Project hooks (agent harnesses)

Configured in `.claude/settings.json`. The harness loads these when the folder is trusted.
All Python hooks run through `run_hook.sh` (repo `.venv/bin/python`, else `python3`)
and resolve tools via `_hook_io.venv_tool()` — never the harness PATH.

## Why venv-first matters here

The harness shell inherits the operator's login PATH, where `python`, `ruff`,
`pytest` are **pyenv shims** (observed: Python 3.9 shims that fail because the
`.python-version` pin is uv-managed 3.14) and bare `dazzle` was a stale
`~/.local/bin` wrapper onto a pyenv virtualenv. `session_start.sh` therefore
prepends `.venv/bin` to PATH through `CLAUDE_ENV_FILE`, and every hook that
shells out uses the venv binary explicitly.

## SessionStart

| Hook | Purpose |
|------|---------|
| `session_start.sh` | Export `DAZZLE_PROJECT_ROOT`, `VIRTUAL_ENV`, and `PATH=.venv/bin:$PATH` via `CLAUDE_ENV_FILE`; verify `import dazzle` |

## PreToolUse (blocking)

| Hook | Matcher | Purpose |
|------|---------|---------|
| `bash_validator.py` | `Bash\|run_terminal_command` | Block `rm -rf /`, wildcard root deletes, block-device writes, and forced pushes (`--force-with-lease` is allowed) |
| `file_protection.py` | `Edit\|Write\|search_replace\|write` | Block auto-generated / secret paths |

Exit codes: `0` allow, `2` deny. **Never exit 1** — harnesses log that as
`pre_tool_use[N] failed with exit code 1` while still fail-opening the tool.
Hooks use `from __future__ import annotations` (system Python 3.9) and
`_hook_io.safe_main` so runtime bugs also exit 0 instead of spamming the TUI.

The validator scans the **whole** command text, including heredoc bodies.
If a file you are writing via heredoc contains a blocked phrase, the write
is refused; use the harness's Write/Edit tool or split the literal.

**Removed (2026-10-11):** the bare-`dazzle` → `python -m dazzle` rewrite. It
matched `dazzle` inside paths (`src/dazzle/`, `.dazzle/`) and emitted
`src/python -m dazzle/`; Claude Code also ignored its legacy output shape, so
it was either a no-op or a corruption. Regression test:
`test_bash_validator_never_rewrites_commands`.

### Known regression (fixed 2026-07-16)

`pre_tool_use[1]` is the `file_protection` matcher group. Before the fix it
crashed on every `search_replace` under PATH `python3` 3.9 because
`str | None` was evaluated at import time (PEP 604). Session telemetry on
main: **376× exit-1 failures → 0 after** `run_hook.sh` + future annotations +
camelCase payloads.

## PostToolUse (passive)

| Hook | Purpose |
|------|---------|
| `dsl_validator.py` | After `.dsl`/`.dazzle` edits, run `dazzle validate` in nearest `dazzle.toml` root |
| `code_formatter.py` | `ruff format` on edited `.py` (async). No JS/TS formatter — the repo configures none |

## Stop / Subagent / Compact

| Hook | Purpose |
|------|---------|
| `stop_lint.py` | `ruff check` every changed `.py` (staged, unstaged, untracked) at end of turn → `systemMessage` |
| `subagent_context.py` | Three-line live orientation (branch, dirty count, toolchain rule). AGENTS.md already reaches subagents; this adds only live state |
| `subagent_stop.py` | `ruff check` `.py` files modified in the last 2 min under `src/ tests/ scripts/` |
| `compact_context.py` | Preserve branch, HEAD, and `git status --porcelain` across compaction |
| `worktree_setup.sh` | **Creates** the worktree (`.claude/worktrees/<name>`, branch `worktree-<name>`, from current HEAD — the harness does not create it when a hook exists), runs `uv sync --frozen` with the dev extras, copies `.env*`, prints the path as the last stdout line |
| `worktree_remove.sh` | Removes the worktree directory and its `worktree-<name>` branch (the harness deletes neither) |
| `session_cleanup.sh` | Prune `.dazzle/tmp`, log session end |

## Compatibility notes

- Harnesses may send **camelCase** (`toolName`, `toolInput`) or **snake_case**
  (`tool_name`, `tool_input`). `_hook_io.py` accepts both.
- System `python3` may be 3.9 — hooks use `from __future__ import annotations`
  so PEP 604 types do not crash import (regression:
  `tests/unit/test_claude_pretool_hooks.py`).
- Do not use `cmd || fallback` for hook commands: exit `2` (deny) would re-run
  the fallback.

## Smoke

```bash
export CLAUDE_PROJECT_DIR="$(pwd)"
printf '%s\n' '{"toolName":"search_replace","toolInput":{"file_path":"README.md"}}' \
  | .claude/hooks/run_hook.sh file_protection.py
# expect exit 0
printf '%s\n' '{"tool_name":"Bash","tool_input":{"command":"ls src/dazzle"}}' \
  | .claude/hooks/run_hook.sh bash_validator.py
# expect exit 0 and no stdout
```
