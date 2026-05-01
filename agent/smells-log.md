# Smells Log

## Fix Cycle — 2026-04-16 (post-baseline)
- Patterns addressed: 14/18
- Correctness fixes: 3 (DB silent failures, foreach errors, email handler)
- Thread safety: 7 singletons made safe
- Duplication removed: ~1,500 lines (Celery module + HTTP utils)
- Type safety: ~30 Any→concrete, type-ignore codes added
- Coupling: MCP→CLI cycle broken, UI→testing layer fixed
- Complexity: 1,477-line function split, 55-method god class extracted, 48 constants frozen
- Filed: #787 (TaskStoreBackend protocol design)
- Deferred: parser god classes (in progress), oversized parser functions (in progress)
- Commit range: 0ef16779..9d973802

## Smells Run — 2026-04-16
- Regressions: 7/9 checks passed (1.1 FAIL: 44 swallowed exceptions, 1.5a FAIL: 1 silent email handler)
- New patterns: 18 found (3 critical, 6 high, 6 medium, 3 low)
- Top concern: DB-connection silent failure in process executors (correctness risk — failed steps reported as success)
- Commit: e91d9066

## Smells Run — 2026-05-01
- Regressions: 8/10 checks passed (1.1 FAIL: 28 swallowed exceptions, ↓16 vs last; 1.5b TRACK: getattr count 916)
- New patterns: 17 (4 HIGH, 7 MEDIUM, 6 LOW)
- Top concern: 28 bare `except Exception: pass` sites — improved but still failing the gate
- Resolved since last: 1.5a silent event handlers (was 1, now 0); 1.1 sites reduced 44 → 28
- New visibility: 1.6/1.7 size metrics now numerically tracked (115 fns >150 ln, 9 classes >800 ln)
- Recommended next 3: (1) finish bare-except-pass cleanup, (2) audit ADR-0003 shims (5), (3) audit ADR-0005 globals (3)
- Commit: 83b34645

## Fix Cycle — 2026-05-01 (post-baseline)
- Action 1 (1.1 bare-except-pass): 28 → 0 prod sites. Pattern: `with suppress(Exception):` for cleanup; `except Exception: logger.debug(..., exc_info=True)` for logged sites.
- Action 2 (P6 shims): removed 2/3 named live shims:
  - `state.py` `_StateModule` proxy + `_LEGACY_ATTR_MAP` deleted; tests updated to use `get_state()` accessor
  - `runtime_tools/__init__.py` 5 delegating wrappers moved into `state.py` as proper public setters/getters
  - `testing/agent_e2e.py` deferred (504-line module, 3 production callers — needs focused refactor cycle)
- Action 3 (P7 globals): not in this cycle. `_AUTH_STORE`, `_event_framework` need request-context plumbing through helpers. `_sa` is a legitimate lazy-import pattern, not application state.
- Drift gates added: `tests/unit/test_no_bare_except_pass.py`, `tests/unit/test_no_shims.py` (with ALLOWED_PATHS for the deferred agent_e2e wrapper + LayoutArchetype rename + RBAC PERMIT_UNPROTECTED text).
- Net: 28 sites quieted; 2 shims gone; 2 drift gates in place. ADR-0005 globals deferred to a focused cycle.
