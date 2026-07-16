# Project hooks (agent harnesses)

Configured in `.claude/settings.json`. The harness loads these when the folder is trusted.

## PreToolUse (blocking)

| Hook | Matcher | Purpose |
|------|---------|---------|
| `bash_validator.py` | `Bash\|run_terminal_command` | Block destructive shell; rewrite bare `dazzle` → `python -m dazzle` |
| `file_protection.py` | `Edit\|Write\|search_replace\|write` | Block auto-generated / secret paths |

Exit codes: `0` allow, `2` deny, other = fail-open (tool still runs; the harness may log the failure).

## PostToolUse (passive)

| Hook | Purpose |
|------|---------|
| `dsl_validator.py` | After `.dsl`/`.dazzle` edits, run `dazzle validate` in nearest `dazzle.toml` root |
| `code_formatter.py` | `ruff format` / prettier on edited sources |

## Runner

`run_hook.sh <script.py>` — prefers `$CLAUDE_PROJECT_DIR/.venv/bin/python`, else `python3`.

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
```
