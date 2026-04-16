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
