Run all quality checks on modified files. This is the on-demand quality gate — use it before shipping or when you want to validate your work.

**This command uses parallel subagents** to run independent checks concurrently.

## Steps

### 1. Determine what changed

Run `git diff --name-only HEAD` to get the list of modified files. Categorize:
- `py_changed` = any `.py` files in the diff
- `dsl_changed` = any `.dazzle` files in the diff
- `parser_changed` = any files matching `src/dazzle/core/dsl_parser` in the diff
- `mcp_changed` = any files matching `src/dazzle/mcp/` in the diff

### 2. Dispatch parallel checks

**Dispatch ALL applicable checks as background subagents in a single message.** Use `model: "claude-haiku-4-5-20251001"` for each — these are mechanical checks and Haiku 4.5 is both cheapest and fast. (The bare `haiku` alias was retired when Haiku 3 shut down; reach for the explicit 4.5 id.)

Always dispatch these two (they always apply):

**Lint + format agent:**
```
Run lint and format checks on the Dazzle project:
1. Run: ruff check src/ tests/ --fix && ruff format src/ tests/
2. If ruff made changes, report which files were fixed
3. If errors remain after --fix, list them
Return: LINT: pass|fail (N issues)
```

**Type check agent:**
```
Run mypy type checks on the Dazzle project (matching CI):
1. Run: mypy src/dazzle/core src/dazzle/cli src/dazzle/mcp --ignore-missing-imports --exclude 'eject'
2. Run: mypy src/dazzle_back/ --ignore-missing-imports
3. Report any errors with file paths and line numbers from BOTH runs
Return: MYPY: pass|fail (N errors)
```

Conditionally dispatch these based on what changed:

**Unit tests agent** (if `py_changed`):
```
Run unit tests for the Dazzle project:
1. Run: pytest tests/unit -x -q --tb=short -m "not slow"
2. Report pass/fail count and any failure details
Return: TESTS: pass|fail (N passed, M failed)
```

**DSL validation agent** (if `dsl_changed`):
```
Run DSL validation for the Dazzle project:
1. Run: dazzle validate
2. Report any parse or validation errors
Return: DSL: pass|fail (details)
```

**Parser corpus agent** (if `parser_changed`):
```
Run parser corpus tests for the Dazzle project:
1. Run: pytest tests/parser_corpus/ -x -q --tb=short
2. Report pass/fail count
Return: PARSER: pass|fail (N passed, M failed)
```

**MCP verification agent** (if `mcp_changed`):
```
Run MCP tool verification for the Dazzle project:
1. Run: python scripts/verify-mcp.py
2. Report any missing or misconfigured tools
Return: MCP: pass|fail (details)
```

### 3. Collect and report

As each subagent completes, collect its result. Once ALL are done, present a summary:

```
## Quality Check Results

| Check | Status | Details |
|-------|--------|---------|
| Lint + format | PASS/FAIL | N issues |
| Type check | PASS/FAIL | N errors |
| Unit tests | PASS/FAIL | N passed, M failed |
| DSL validation | SKIP/PASS/FAIL | reason |
| Parser corpus | SKIP/PASS/FAIL | reason |
| MCP verification | SKIP/PASS/FAIL | reason |

**Overall: PASS/FAIL**
```

If everything passed, say: **"All checks passed. Ready to ship."**
If anything failed, list what needs fixing.

Do NOT commit or push. This is a read-only quality check.
