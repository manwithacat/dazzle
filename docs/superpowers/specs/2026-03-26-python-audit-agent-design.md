# Python Audit Sentinel Agent

**Issue**: New (to be created)
**Status**: Approved
**Date**: 2026-03-26

## Summary

Add a `PythonAuditAgent` (PA) to the sentinel framework that detects obsolete Python patterns in user project code. Three detection layers: curated ruff rules for mechanical modernisation, a semgrep ruleset for deprecated stdlib and patterns ruff misses, and `@heuristic` methods for LLM training-bias patterns no generic linter catches. Results flow through the existing sentinel infrastructure — findings, deduplication, persistence, MCP query. The `/smells` CLI skill becomes a thin wrapper over `sentinel scan --agent PA`.

## Design

### 1. Agent Identity

New `AgentId` member: `PA = "PA"` (Python Audit).

New agent class: `PythonAuditAgent` in `src/dazzle/sentinel/agents/python_audit.py`.

Registered in `src/dazzle/sentinel/agents/__init__.py` alongside the existing 8 agents. The orchestrator picks it up automatically on the next scan.

### 2. Detection Layer 1 — Ruff Profile

Run `ruff check` with a curated rule selection against the user's project Python files. Parse JSON output into `Finding` objects.

**Rule categories:**

| Ruff Rules | Audit Doc Section | Coverage |
|------------|------------------|----------|
| `UP` (pyupgrade) | Type Hints | `Optional`, `Union`, `List`, `Dict`, `__future__` |
| `PTH` (pathlib) | String/Path | `os.path.*` → `pathlib` |
| `ASYNC` | Async | asyncio anti-patterns |
| `C4` (comprehensions) | Control Flow | Unnecessary comprehension wrapping |
| `SIM` (simplify) | Control Flow | if/elif simplification |

**Invocation:**

```python
ruff check --select UP,PTH,ASYNC,C4,SIM --output-format json --target-version py312 <paths>
```

- `--target-version` derived from `pyproject.toml` `requires-python`
- Runs against `app/`, `scripts/`, and root-level `.py` files — not framework code
- Separate invocation from the project's own ruff config — does not interfere

**Finding mapping:**
- `heuristic_id`: `PA-{ruff_code}` (e.g., `PA-UP007`, `PA-PTH100`)
- Severity: ruff's categorisation mapped to sentinel levels (UP → LOW/INFO, PTH → INFO, ASYNC → MEDIUM)
- Evidence: file, line, code snippet from ruff JSON
- Remediation: ruff's suggested fix text + the modern replacement pattern

### 3. Detection Layer 2 — Semgrep Ruleset

A custom semgrep ruleset shipped at `src/dazzle/sentinel/rules/python_audit.yml` for patterns ruff doesn't cover.

**Rules (~10):**

| Rule ID | Pattern | Severity | Min Version |
|---------|---------|----------|-------------|
| `PA-SG-distutils` | `import distutils` / `from distutils` | HIGH | 3.12+ (removed) |
| `PA-SG-pkg-resources` | `import pkg_resources` | MEDIUM | 3.9+ |
| `PA-SG-cgi` | `import cgi` / `import cgitb` | HIGH | 3.13+ (removed) |
| `PA-SG-imp` | `import imp` | HIGH | 3.12+ (removed) |
| `PA-SG-event-loop` | `asyncio.get_event_loop()` | HIGH | 3.10+ (deprecated) |
| `PA-SG-timezone-utc` | `datetime.timezone.utc` | LOW | 3.11+ |
| `PA-SG-self-typevar` | `TypeVar("T", bound="ClassName")` for Self | LOW | 3.11+ |
| `PA-SG-nose` | `import nose` / `from nose` | HIGH | Abandoned |
| `PA-SG-toml-lib` | `import toml` (PyPI package) | MEDIUM | 3.11+ (stdlib) |
| `PA-SG-format-string` | `'{}'.format(x)` / `'%s' % x` (outside logging) | LOW | 3.6+ |

**Invocation:**

```python
semgrep --config src/dazzle/sentinel/rules/python_audit.yml --json <paths>
```

**Finding mapping:** same pattern as ruff — parse JSON, create `Finding` with evidence and remediation.

### 4. Detection Layer 3 — LLM Training-Bias Heuristics

`@heuristic`-decorated methods on `PythonAuditAgent` for patterns specific to LLM-generated code that generic linters don't flag.

| Heuristic ID | Pattern | Detection |
|-------------|---------|-----------|
| `PA-LLM-01` | `requests` in async codebase | AST: check if project has `async def` functions and also imports `requests` — suggest `httpx` |
| `PA-LLM-02` | `configparser`/`json` for config | AST: `import configparser` when `pyproject.toml` or `dazzle.toml` exists — suggest `tomllib` |
| `PA-LLM-03` | Manual dunder methods | AST: class with `__init__` + `__repr__` or `__eq__` but no `@dataclass` decorator |
| `PA-LLM-04` | unittest in pytest project | AST: `import unittest` / `class X(unittest.TestCase)` when `conftest.py` exists |
| `PA-LLM-05` | `setup.py` alongside `pyproject.toml` | File check: both files exist |
| `PA-LLM-06` | `pip install` / `virtualenv` when `uv` available | File check: `uv.lock` exists but scripts/docs reference `pip install` |

Each heuristic method:
1. Walks `.py` files using `ast.parse()`
2. Checks node types and context
3. Returns `Finding` objects with evidence and remediation

### 5. Python Version Filtering

The agent reads the target Python version from `pyproject.toml` `requires-python` field (e.g., `>=3.12`). Findings with a `min_version` higher than the target are filtered out before returning results.

Example: a project targeting `>=3.9` would not see `PA-SG-timezone-utc` (requires 3.11+) or `PA-SG-distutils` (removed in 3.12).

If `requires-python` is not set, default to `3.10` (conservative — flags most patterns without false positives from 3.11/3.12-only changes).

### 6. Scan Scope

The agent scans the user's project code, not framework code:
- Include: `app/`, `scripts/`, root-level `*.py`, any directories in `dazzle.toml` `[modules].paths`
- Exclude: `__pycache__/`, `.venv/`, `node_modules/`, `.dazzle/`, files matching `# AUTO-GENERATED`
- Exclude: `src/dazzle/`, `src/dazzle_back/`, `src/dazzle_ui/` (framework code — audited separately)

Scope is relative to the project root (from manifest).

### 7. Severity Mapping

| Audit Doc Severity | Sentinel Severity | When |
|-------------------|-------------------|------|
| MAJOR | HIGH | Deprecated/removed API — will break on target Python |
| MODERATE | MEDIUM | Technical debt, maintainability cost |
| MINOR | LOW | Suboptimal but functional, better alternative exists |
| COSMETIC | INFO | Style preference, modern idiom preferred |

### 8. `/smells` Skill Update

The existing `/smells` CLI skill (`.claude/commands/smells.md`) becomes a thin wrapper:

1. Triggers `sentinel scan` filtered to agent `PA`
2. Formats findings as the familiar markdown report (grouped by severity, then category)
3. Saves to `dev_docs/smells-report.md`

The current parallel-subagent pipeline in `/smells` is retired — sentinel's orchestrator replaces it. The regression checks from `/smells` Phase 1 (swallowed exceptions, function length, class length) become additional `@heuristic` methods on the PA agent, preserving existing coverage.

### 9. Testing

- Unit tests for each `@heuristic` method with sample Python source fixtures (strings parsed via `ast.parse()`)
- Unit tests for ruff JSON output → `Finding` conversion (mock `subprocess.run`)
- Unit tests for semgrep JSON output → `Finding` conversion (mock `subprocess.run`)
- Unit test for Python version filtering (3.9 project doesn't get 3.11+ findings)
- Unit test for scan scope (framework code excluded, user code included)
- Integration test: run full agent against a fixture directory with known obsolete patterns, verify expected findings
- Existing sentinel tests (orchestrator, dedup, store) — should pass unchanged

### 10. What Does Not Change

- Existing 8 sentinel agents (DI, AA, MT, ID, DS, PR, OP, BL)
- MCP `sentinel` tool schema (no new operations — PA findings appear via existing `findings`/`status`/`history`)
- Finding persistence and deduplication
- Sentinel orchestrator (new agent is just another entry in the agent registry)

## Files to Create/Modify

| File | Change |
|------|--------|
| `src/dazzle/sentinel/models.py` | Add `PA = "PA"` to `AgentId` enum |
| `src/dazzle/sentinel/agents/python_audit.py` | New: `PythonAuditAgent` with 3 detection layers |
| `src/dazzle/sentinel/agents/__init__.py` | Register `PythonAuditAgent` |
| `src/dazzle/sentinel/rules/python_audit.yml` | New: semgrep ruleset (~10 rules) |
| `.claude/commands/smells.md` | Update: thin wrapper over `sentinel scan --agent PA` |
| `tests/unit/test_python_audit_agent.py` | New: unit + integration tests |

## Appendix: Audit Reference Mapping

The audit reference document (`audit-reference.docx`) maps to detection layers as follows:

| Doc Section | Layer | Notes |
|-------------|-------|-------|
| 1. Type Hints | Ruff `UP` | Full coverage via pyupgrade rules |
| 2. String/Path | Ruff `PTH` | os.path → pathlib |
| 3. Async/HTTP | Ruff `ASYNC` + Semgrep + LLM-01 | Event loop deprecation, requests→httpx |
| 4. Dataclasses/Config | LLM-02, LLM-03, Semgrep | Manual dunders, configparser, toml |
| 5. Exception Handling | Ruff `SIM` | Parenthesised context managers, bare except |
| 6. Pattern Matching | Ruff `SIM` | if/elif simplification candidates |
| 7. Testing | LLM-04, Semgrep | unittest in pytest, nose |
| 8. Packaging | LLM-05, LLM-06 | setup.py, pip/virtualenv |
| 9. Django | Out of scope | Dazzle is FastAPI-based |
| 10. Stdlib Removals | Semgrep | distutils, pkg_resources, cgi, imp |
| 11. Toolchain | LLM-06 | ruff vs flake8/black/isort |
