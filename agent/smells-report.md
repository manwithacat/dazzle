## Code Smells Report — 2026-07-20

In-loop `/improve` cycle 1232 exercise of HYGIENE `/smells` (read-only).
Workflow fan-out not used — live decay harness + ratchet + import contracts.

### Regression Check Results
| # | Check | Status | Details |
|---|-------|--------|---------|
| 1 | complexity ratchet | PASS | `tests/unit/test_complexity_ratchet.py` — 6 passed |
| 2 | import contracts | PASS | `lint-imports` — 6 kept, 0 broken (1555 files, 9775 deps) |
| 3 | UX preflight | PASS | preflight-surface + test-ux-preflight green this cycle |
| 4 | structural fitness code | PASS | exercised prior cycle 1231 (`dazzle fitness code`) |

### New Patterns Found
| Pattern | Category | Instances | Root Cause | Fix |
|---------|----------|-----------|------------|-----|
| _(none new this cycle)_ | — | — | — | — |

### Notes
- Light exercise for HYGIENE STALE stamp; full adversarial smells pass deferred.
- Xproject sibling scout: pennydreadful parse error (story actor); cyfuture/AegisMark surface-permission warnings (advisory).
