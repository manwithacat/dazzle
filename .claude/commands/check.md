Run all quality checks on modified files. This is the on-demand quality gate — use it before shipping or when you want to validate your work.

## Steps

1. **Lint + format** — Run `ruff check src/ tests/ --fix && ruff format src/ tests/`. Fix any remaining issues.

2. **Type check** — Run `mypy src/dazzle`. Fix any errors.

3. **Unit tests** (if Python files changed) — Check `git diff --name-only HEAD` for `.py` files. If any changed, run `pytest tests/unit -x -q --tb=short -m "not slow"`. Report failures.

4. **DSL validation** (if .dazzle files changed) — Check `git diff --name-only HEAD` for `.dazzle` files. If any changed, run `dazzle validate`. Report failures.

5. **Parser corpus** (if parser files changed) — Check `git diff --name-only HEAD` for files matching `src/dazzle/core/dsl_parser`. If any changed, run `pytest tests/parser_corpus/ -x -q --tb=short`.

6. **MCP verification** (if MCP files changed) — Check `git diff --name-only HEAD` for files matching `src/dazzle/mcp/`. If any changed, run `python scripts/verify-mcp.py`.

7. **Report** — Summarize results: which checks ran, which passed, which failed. If everything passed, say so clearly.

Do NOT commit or push. This is a read-only quality check.
