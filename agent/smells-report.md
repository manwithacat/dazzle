# Code Smells Report — 2026-04-16

## Regression Check Results

| # | Check | Status | Details |
|---|-------|--------|---------|
| 1.1 | No swallowed exceptions | **FAIL** | 44 bare except-pass in production code. 0 in `core/`. Concentrated in CLI/MCP (19), dazzle_back runtime (7), agent/e2e helpers (18). |
| 1.2 | No redundant except tuples | **PASS** | 0 results. |
| 1.3 | Core→MCP isolation | **PASS** | 0 imports. |
| 1.4 | No `project_path: Any` in handlers | **PASS** | 0 results. |
| 1.5 | Fallback paths log at WARNING+ | **N/A** | Spot-check: outer loops log but silent-site logging absent in some cases. |
| 1.5a | No silent event handlers | **FAIL** | 1 genuine: `email.py:496` — `(JSONDecodeError, KeyError): pass` in message-read path, silently returns None. |
| 1.5b | `getattr()` count < 200 | **TRACK** | 731 calls across 139 files. |
| 1.6 | Function length > 150 lines | **INFO** | 106 functions. Top 5: `get_consolidated_tools` (1477), `get_workflow_guide` (777), `parse_entity` (728), `serve_command` (594), `_page_handler` (514). |
| 1.7 | Class length > 800 lines | **INFO** | 8 classes. Worst: `EntityParserMixin` (2282), `ProcessParserMixin` (1576), `MessagingParserMixin` (1190). |

**Hard failures**: 1.1 (44 swallowed exceptions), 1.5a (1 silent email handler)

---

## New Patterns Found

### Critical (correctness risk)

| Pattern | Category | Instances | Root Cause | Fix |
|---------|----------|-----------|------------|-----|
| DB-connection failure silently returns `{}` | error_handling | 6 (3 files) | `_get_db_connection` errors caught and swallowed — process runs marked COMPLETED despite DB failure | Raise `RuntimeError` instead of `return {}`; outer run-loop already handles with `_run_compensation` |
| Foreach sub-step errors counted but run always succeeds | error_handling | 3 (3 files) | `errors` counter incremented but never inspected — 100%-failure foreach steps marked COMPLETED | Raise when `errors == len(items)`; add integration test |
| In-process mutable task store in production path | mutable_globals | 2 | `_task_store: dict` in `activities.py` is dev-only but wired into production Temporal path — data lost on restart | Extract `TaskStoreBackend` protocol; inject via `RuntimeServices` (ADR-0005) |

### High (structural debt)

| Pattern | Category | Instances | Root Cause | Fix |
|---------|----------|-----------|------------|-----|
| Duplicate Celery module | duplication | 2 files, ~750 lines | `celery_tasks.py` and `process_celery_tasks.py` are near-identical | Keep one in `dazzle.core`, delete the other |
| Broad-exception log-and-return-falsy | error_handling | 53 across 34 files | No codebase rule on exception strategy | Enable ruff `BLE001`; propagate or use typed result |
| MCP→CLI reverse dependency | coupling | 7 imports across 3 files | Shared logic placed in `cli/` instead of neutral package | Move to `dazzle/services/` |
| `Any` in `route_generator.py` signatures | type_safety | 23 | `TYPE_CHECKING` block exists but wasn't populated | Add concrete types under `TYPE_CHECKING` |
| Oversized functions (>300 lines) | complexity | 16 | Parser/tool-registration mega-functions | Extract per-branch helpers |
| Deep nesting (depth ≥8) | complexity | 78 | `if/elif` dispatch instead of guard clauses or dispatch tables | Invert conditions, use `dict[str, Callable]` |

### Medium

| Pattern | Category | Instances | Root Cause | Fix |
|---------|----------|-----------|------------|-----|
| `_build_process_where_clause` copy-pasted | duplication | 3 copies | Written before `QueryBuilder` existed | Import `QueryBuilder`, delete copies |
| `ServerConfig` fields typed `Any` | type_safety | 7 | `TYPE_CHECKING` block empty (`pass`) | Populate with concrete types |
| Thread-unsafe lazy-init singletons | mutable_globals | 8 | `if X is None: X = ...` without lock | Use `functools.lru_cache` or add `threading.Lock` |
| Two divergent HTTP-retry implementations | coupling | 2 modules, 10 call-sites | `core.http_client` vs `dazzle_back.runtime.http_utils` | Consolidate into `core.http_client` |
| God classes (>35 methods) | complexity | 7 | Domain objects accumulate query helpers | Extract to companion query modules |
| Bare `# type: ignore` without codes | type_safety | 6+ production, 15+ test | Time pressure | Add error codes; enable `warn_unused_ignores` |

### Low

| Pattern | Category | Instances | Root Cause | Fix |
|---------|----------|-----------|------------|-----|
| `_TRIGGER_MAP: dict[Any, Any]` | type_safety | 2 | Enum types not added to `TYPE_CHECKING` | Replace with concrete types |
| Unfrozen lookup tables | mutable_globals | 102 | No `frozenset`/`tuple` convention | Convert ALL_CAPS sets→frozenset, lists→tuple |
| UI→testing layer violation | coupling | 2 | Convenience imports across boundary | Move shared functions to `dazzle.core` |

---

## Recommended Next Actions

1. **Fix DB-connection silent failures in process executors** — correctness risk: failed steps report success. 6 locations across 3 files, straightforward `raise` instead of `return {}`.

2. **Delete duplicate Celery module** — 750 lines of dead duplication. `process_celery_tasks.py` can be removed, all callers updated to `celery_tasks.py`.

3. **Resolve MCP→CLI reverse dependency** — architectural violation of ADR-0002. Move `feedback_impl.py` and `agent_commands/` to `dazzle/services/`. The `agent_commands` module was just created in v0.57.0 — fixing it now is cheaper than later.

4. **Type-harden `route_generator.py`** — 23 `Any` annotations where `TYPE_CHECKING` imports already exist. Pure refactor, zero runtime risk.

5. **Enable ruff BLE001** — turns 53 broad-exception catches into CI failures, with `# noqa` annotations on the ~8 intentional cases.

---

## Comparison with Previous Round

_First run with `agent/` convention — no previous report to compare against._

- Regressions: 2/9 hard checks failed (1.1, 1.5a)
- New patterns: 18 patterns catalogued across 4 categories
- Resolved since last round: N/A (baseline run)
