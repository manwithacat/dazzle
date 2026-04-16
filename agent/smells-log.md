# Smells Log

## Smells Run — 2026-04-16
- Regressions: 7/9 checks passed (1.1 FAIL: 44 swallowed exceptions, 1.5a FAIL: 1 silent email handler)
- New patterns: 18 found (3 critical, 6 high, 6 medium, 3 low)
- Top concern: DB-connection silent failure in process executors (correctness risk — failed steps reported as success)
- Commit: e91d9066
