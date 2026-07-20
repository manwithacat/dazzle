## Code Smells Report — 2026-07-20

In-loop `/improve` cycle 1191 exercise of HYGIENE `/smells` (read-only).
Workflow fan-out not used — live decay harness + ratchet + import contracts.

### Regression Check Results
| # | Check | Status | Details |
|---|-------|--------|---------|
| 1 | complexity ratchet | PASS | `tests/unit/test_complexity_ratchet.py` — 6 passed |
| 2 | import contracts | PASS | `lint-imports` — 6 kept, 0 broken (1555 files, 9775 deps) |
| 3 | UX preflight | PASS | preflight-surface + test-ux-preflight green this cycle |
| 4 | structural fitness code | PASS | `dazzle fitness code` ordered hotspot queue regenerated |

### New Patterns Found
| Pattern | Category | Instances | Root Cause | Fix |
|---------|----------|-----------|------------|-----|
| (none elevated) | — | — | Standing debt owned by ratchet + import contracts | TRACK only |

No new systemic semantic pattern elevated above TRACK — FAIL regressions = 0.

### Structural Decay (live harness)
- **Ratchet:** clean (6 passed)
- **Import contracts:** KEPT, 6 contracts, 0 broken
- **Priority refactor targets** (high-churn × complexity):
  1. `mcp/server/handlers_consolidated.py` (score 8811, churn 116, MI A)
  2. `render/fragment/primitives/data.py` (7894, 88, B)
  3. `core/dsl_parser_impl/workspace.py` (6600, 66, **C**)
  4. `core/ir/workspaces.py` (6051, 71, B)
  5. `core/lexer.py` (5712, 80, A)

### Recommended Next Actions
1. When product work next touches workspaces, prefer slicing `dsl_parser_impl/workspace.py` (MI-C).
2. Keep MCP dispatch consolidation until a forced domain split — MI-A despite churn.
3. No FAIL regressions — do not open smells-driven product issues this cycle.

### Comparison with Previous Round
- Regressions: 0 FAIL (same as cycle 484 report posture)
- New patterns: 0 elevated
- Decay delta: handlers_consolidated score 8286→8811 (churn 110→116); data.py 7435→7894 — rising but still MI A/B; ratchet still holds
