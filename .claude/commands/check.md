Run all quality checks on modified files. This is the on-demand quality gate — use it before shipping or when you want to validate your work.

**Runs the checks as parallel Bash calls in the main loop — not subagents.** At the session's context size the per-command isolation a subagent buys isn't worth the dispatch overhead: deterministic command output is cheap to read directly, and running inline keeps every result in one place. (This replaced the earlier "one Haiku subagent per command" design — the isolation stopped paying off at large context.)

## Steps

### 1. Determine what changed

Run `git diff --name-only HEAD` to get the list of modified files. Categorize:
- `py_changed` = any `.py` files in the diff
- `dsl_changed` = any `.dazzle` files in the diff
- `parser_changed` = any files matching `src/dazzle/core/dsl_parser` in the diff
- `mcp_changed` = any files matching `src/dazzle/mcp/` in the diff

### 2. Lint + format FIRST (it mutates files)

Run this **alone, before** the parallel read-only checks — `ruff` rewrites files, so racing it against mypy/pytest would let them read half-written source (a latent bug in the old subagent fan-out, which ran the fixer concurrently with the readers):

```bash
ruff check src/ tests/ --fix && ruff format src/ tests/
```

Note which files ruff changed. If errors remain after `--fix`, record them for the report.

### 3. Run the read-only checks in parallel

Issue all applicable commands as **separate Bash calls in a single message** so they run concurrently. Always run the type check; add the rest based on what changed in step 1:

| Check | Run when | Command |
|-------|----------|---------|
| Type | always | `mypy src/dazzle` |
| Unit tests | `py_changed` | `pytest tests/unit -x -q --tb=short -m "not slow"` |
| DSL validation | `dsl_changed` | `dazzle validate` |
| Parser corpus | `parser_changed` | `pytest tests/parser_corpus/ -x -q --tb=short` |
| MCP verify | `mcp_changed` | `python scripts/verify-mcp.py` |

The type command **must stay identical to `/ship` and CI** — change one, change all three (see the gate-sync note in `ship.md`).

### 4. Collect and report

Read each command's output and present a summary:

```
## Quality Check Results

| Check | Status | Details |
|-------|--------|---------|
| Lint + format | PASS/FAIL | N issues |
| Type check | PASS/FAIL | N errors |
| Unit tests | SKIP/PASS/FAIL | N passed, M failed |
| DSL validation | SKIP/PASS/FAIL | reason |
| Parser corpus | SKIP/PASS/FAIL | reason |
| MCP verification | SKIP/PASS/FAIL | reason |

**Overall: PASS/FAIL**
```

If everything passed, say: **"All checks passed. Ready to ship."**
If anything failed, list what needs fixing.

Do NOT commit or push. This is a read-only quality check (apart from `ruff --fix`'s in-place formatting).
