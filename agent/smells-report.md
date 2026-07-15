## Code Smells Report — 2026-07-13

In-loop `/improve` cycle 484 exercise of OWNED-IDLE `/smells` (read-only).
Workflow fan-out not available in this harness — used live decay harness +
spot semantic scan of top hotspots instead.

### Regression Check Results
| # | Check | Status | Details |
|---|-------|--------|---------|
| 1 | complexity ratchet | PASS | `tests/unit/test_complexity_ratchet.py` — 6 passed |
| 2 | import contracts | PASS | `lint-imports` — 6 kept, 0 broken (1507 files) |
| 3 | UX preflight | PASS | 12 pass / 11 skip + mypy page clean |
| 4 | structural fitness code | PASS | `dazzle fitness code` generates ordered hotspot queue |

### New Patterns Found
| Pattern | Category | Instances | Root Cause | Fix |
|---------|----------|-----------|------------|-----|
| Broad except in CLI/db surface | error-handling | ~24 except blocks in `cli/db.py` | migration/ops paths absorb many failure modes | Prefer typed error classes + re-raise at boundary; leave ops logging explicit |
| Consolidated MCP dispatcher density | maintainability | handlers_consolidated top hotspot (score 8286, churn 110) | single file owns tool dispatch surface | Already MI-rank A; split by domain only when a concrete seam is forced |

No new systemic semantic pattern elevated above TRACK for this cycle — standing
debt is owned by the complexity ratchet + import contracts.

### Structural Decay (live harness)
- **Ratchet:** clean (6 passed)
- **Import contracts:** KEPT, 6 contracts, 0 broken
- **Priority refactor targets** (high-churn × complexity):
  1. `mcp/server/handlers_consolidated.py` (score 8286, churn 110, MI A)
  2. `render/fragment/primitives/data.py` (7435, 83, B)
  3. `core/dsl_parser_impl/workspace.py` (6600, 66, **C**)
  4. `core/ir/workspaces.py` (6051, 71, B)
  5. `core/lexer.py` (5712, 80, A)

Highest-CC / MI-C files in top 15: workspace.py, entity.py, db.py, page_routes.py,
testing.py, linker_impl.py, server.py, dsl_test.py, rhythm.py.

### Recommended Next Actions
1. When product work next touches workspaces, prefer slicing `dsl_parser_impl/workspace.py` (MI-C + high score).
2. Keep MCP dispatch consolidation until a forced domain split — MI-A despite churn.
3. No FAIL regressions — do not open smells-driven product issues this cycle.

### Comparison with Previous Round
- Previous report: 2026-06-21
- Regressions: 0 FAIL this round (ratchet + imports green)
- Decay delta: not re-diffed against June hotspot ranks this cycle (harness report is authoritative live queue)
