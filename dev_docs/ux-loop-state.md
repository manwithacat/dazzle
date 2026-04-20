# /ux-cycle loop state snapshot

Last updated: cycle 338 (2026-04-20)

Single-glance dashboard of where the `/ux-cycle` autonomous loop is now. Regenerated on-demand (see also `dev_docs/ux-log.md` for the full cycle-by-cycle journal).

## Current state

| Dimension | Value |
|---|---|
| **Mode** | Steady-state |
| **Explore budget** | 93 / 100 |
| **Cycles to primary short-circuit** | 7 |
| **UX-architect contracts shipped** | 79 |
| **Preflight gate** | 6 lints + mypy(ui) + dist-warn, ~5s wall |
| **Last full-suite run** | Cycle 311 (11432 passed, 0 failed) |
| **Active `/loop` cadence** | 10m (unchanged since setup) |

## Recent cycle productivity (last 10 non-housekeeping)

| Cycle | Strategy | Finding? |
|---|---|---|
| 323 | issue-filing | #832 ✓ |
| 324 | lint-shipping | external-resource lint ✓ |
| 325 | issue-filing | #833 ✓ |
| 327 | finding_investigation | #834 ✓ |
| 328 | lint rule-out | decision |
| 330 | finding_investigation | FP validated |
| 331 | finding_investigation | FP validated |
| 334 | finding_investigation | #835 ✓ |
| 335 | preemptive audit | no gaps |
| 336/337 | observational | zero |

**Rate:** ~50% across last 10, dropped to ~20% in last 5. Backlog exhausted.

## Open GitHub issues filed by the loop

| # | Filed cycle | State | Title |
|---|---|---|---|
| 829 | 299 | OPEN | TOTP QR secret exfiltration |
| 830 | 301 | OPEN | SRI on external CDN loads |
| 831 | 303 | OPEN | 2FA page routes missing |
| 832 | 323 | OPEN | Vendor Tailwind + own dist |
| 833 | 325 | OPEN | CSP default alignment |
| 834 | 327 | OPEN | `hot_reload.py` orphan investigate |
| 835 | 334 | OPEN | WorkspaceContract persona gap |

**Downstream `/issues` queue is well-stocked.** No new filings expected in the near term without new exploration signal.

## Horizontal-discipline lint stack

| Lint | Cycle | File |
|---|---|---|
| none-vs-default guard | 284 | `tests/unit/test_template_none_safety.py` |
| template orphan scan | 302/304 | `tests/unit/test_template_orphan_scan.py` |
| page route coverage | 306-308 | `tests/unit/test_page_route_coverage.py` |
| canonical pointer | 310 | `tests/unit/test_canonical_pointer_lint.py` |
| DaisyUI-in-Python | 318 | `tests/unit/test_daisyui_python_lint.py` |
| external-resource | 324 | `tests/unit/test_external_resource_lint.py` |

Plus `test_dom_snapshots.py`, `test_card_safety_invariants.py`, and `mypy src/dazzle_ui/` in the preflight gate. `make test-ux-deep` extends to core/cli/mcp/back mypy.

## Silent-drift coverage

| # | Class | Status |
|---|---|---|
| 1 | Syrupy baselines | GATED (cycle 312) |
| 2 | UI type errors | GATED (cycle 314) |
| 3 | dist/ drift | WARNING (cycle 319) |
| 4 | Canonical-helper bypass | MANUAL |
| 5 | DaisyUI in Python HTML | GATED (cycle 318) |
| 6 | contract_audit hygiene | GATED downstream |

Gap doc: `dev_docs/framework-gaps/2026-04-20-ux-cycle-silent-drift-classes.md` (cycle 317).

## Truly-open EX rows

All 3 remaining open rows are FILED:

- EX-054 → #829 (OPEN)
- EX-055 → #831 (OPEN)
- EX-026 → #835 (OPEN, filed cycle 334)

Rest of 54-row backlog is FIXED / CLOSED / DEFERRED / VERIFIED_FALSE_POSITIVE.

## Operator decision points

1. **Cron cadence** — current 10-min interval calibrated for full-backlog era; steady-state may warrant 30m or 60m.
2. **Pause until issues close** — downstream `/issues` has 7 OPEN issues filed by this loop to work through. Closing 3-4 would give this loop material for a cycle 333-style FILED→FIXED sweep.
3. **Continue at current cost** — 20% productivity is still producing some value (#835, cycle 334). No hard requirement to change.

## Where to look for more detail

- `dev_docs/ux-log.md` — full cycle-by-cycle journal (cycles 1→present)
- `dev_docs/ux-backlog.md` — EX rows + PROP rows
- `dev_docs/framework-gaps/` — consolidated theme analyses
- `tests/unit/test_*lint*.py` — all 6 horizontal-discipline lints
- `.claude/commands/ux-cycle.md` — the skill itself (playbook + heuristics)
