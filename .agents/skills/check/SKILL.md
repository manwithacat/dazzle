---
name: check
description: Run all quality checks on modified files — the on-demand pre-ship quality gate
---

Run all quality checks on modified files. This is the on-demand quality gate — use it before shipping or when you want to validate your work.

**Runs the checks as parallel Bash calls in the main loop — not subagents.** At the session's context size the per-command isolation a subagent buys isn't worth the dispatch overhead: deterministic command output is cheap to read directly, and running inline keeps every result in one place. (This replaced the earlier "one Haiku subagent per command" design — the isolation stopped paying off at large context.)

Local ↔ CI concordance: `docs/contributing/local-ci-concordance.md`. Shared runner:
`scripts/ci_local.sh` / `make ci-fast` / `make ci-core` / `make ship-surface` /
`make ci-changed`.

**Habits (build muscle memory):**

1. Mid-edit → `make ci-changed` (path packs from git diff).
2. Before claiming "ready to ship" → at least `make ship-surface` if you only
   ran targeted pytest; prefer full `make ci-fast`.
3. Do not stop at unit green when you touched examples DSL — SPEC footers and
   ship-surface will fail on GitHub if you skip them.

## Steps

### 1. Determine what changed

Run `git diff --name-only HEAD` to get the list of modified files. Categorize:
- `py_changed` = any `.py` files in the diff
- `dsl_changed` = any `.dazzle` / `*.dsl` files in the diff
- `parser_changed` = any files matching `src/dazzle/core/dsl_parser` in the diff
- `mcp_changed` = any files matching `src/dazzle/mcp/` in the diff
- `ci_surface_changed` = any of `scripts/ci_local.sh`, `scripts/ship_surface.py`,
  `scripts/ci_changed.py`, `Makefile`, `.github/workflows/ci.yml`,
  `.github/actions/setup-dazzle/**`
- Prefer path packs when the diff is non-empty:

```bash
make ci-changed   # or: python scripts/ci_changed.py --status && make ci-changed
```

### 2. Lint + format FIRST (it mutates files)

Run this **alone, before** the parallel read-only checks — `ruff` rewrites files, so racing it against mypy/pytest would let them read half-written source:

```bash
ruff check src/ tests/ --fix && ruff format src/ tests/
```

Note which files ruff changed. If errors remain after `--fix`, record them for the report.

### 3. Run the read-only checks in parallel

Issue all applicable commands as **separate Bash calls in a single message** so they run concurrently. Always run the type check; add the rest based on what changed in step 1:

| Check | Run when | Command |
|-------|----------|---------|
| Type | always | `mypy src/dazzle` |
| Path packs | any non-empty diff | `make ci-changed` |
| Ship-surface | `py_changed` or `dsl_changed` or operator asks ship-ready | `make ship-surface` |
| Unit tests | `py_changed` | `pytest tests/unit -n auto --dist loadgroup -q --tb=short -m "not slow"` |
| Gate suite | `ci_surface_changed` or operator asks "CI-like" | `pytest tests/unit -m gate -q` (or full `make ci-fast`) |
| DSL validation | `dsl_changed` | `dazzle validate` (in affected example dirs) + SPEC freshness via ship-surface |
| Parser corpus | `parser_changed` | `pytest tests/parser_corpus/ -x -q --tb=short` |
| MCP verify | `mcp_changed` | `python scripts/verify-mcp.py` |

**mypy command** must stay identical to `/ship` Tier 0 and CI (`mypy src/dazzle` — no extra flags). For release-grade type confidence when extras may be thin:

```bash
make type-check-ci   # sync CI type extras on Python 3.12, then mypy
```

Unit tests run parallel (`-n auto --dist loadgroup`): per-worker Postgres DBs when a DB URL is set; otherwise postgres-marked tests pin via xdist_group. Prefer **full unit** (`-m "not slow"`) over gates-only when Python changed — gates alone are what `/ship` Tier 0 runs, and they under-approximate CI `python-tests`.

If the operator asks for **CI-core concordance** (or you are validating a release candidate), run instead of the table:

```bash
make ci-core
```

### 4. Collect and report

Read each command's output and present a summary:

```
## Quality Check Results

| Check | Status | Details |
|-------|--------|---------|
| Lint + format | PASS/FAIL | N issues |
| Type check | PASS/FAIL | N errors |
| ci-changed packs | SKIP/PASS/FAIL | pack names |
| ship-surface | SKIP/PASS/FAIL | bandit + recurrent pack |
| Unit tests | SKIP/PASS/FAIL | N passed, M failed |
| DSL validation | SKIP/PASS/FAIL | reason |
| Parser corpus | SKIP/PASS/FAIL | reason |
| MCP verification | SKIP/PASS/FAIL | reason |

**Overall: PASS/FAIL**
```

If everything passed, say: **"All checks passed. Ready to ship."**
If anything failed, list what needs fixing.
If only Tier-0-equivalent checks ran, note: *"Not full CI — run `make ci-core` before a release tag."*
If ship-surface was skipped after `py_changed`/`dsl_changed`, note: *"ship-surface not run — badge-red classes may still fail on GitHub."*

Do NOT commit or push. This is a read-only quality check (apart from `ruff --fix`'s in-place formatting).
