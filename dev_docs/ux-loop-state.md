# /ux-cycle loop state snapshot

Last updated: cycle 370 (2026-04-21)

Single-glance dashboard of where the `/ux-cycle` autonomous loop is now. Regenerated on-demand (see also `dev_docs/ux-log.md` for the full cycle-by-cycle journal).

## Current state

| Dimension | Value |
|---|---|
| **Mode** | Resumed after 26-tick auto-pause (340→366) |
| **Explore budget** | 98 / 100 |
| **Cycles to primary short-circuit** | 2 |
| **UX-architect contracts shipped** | 79 |
| **Preflight gate** | **7 lints** + mypy(ui) + dist-warn, ~5s wall (added ir-field-reader-parity cycle 367) |
| **Advisory audit** | `make audit-internals` (cycle 368) — 2/2 real findings so far |
| **Last full-suite run** | Cycle 311 (11432 passed, 0 failed) |
| **Active `/loop` cadence** | 15m (was 10m; tightened at resume cycle 367) |

## This session's burst (cycles 367-369)

Loop resumed after 26-tick auto-pause with **new detection infrastructure** seeded operator-side — four horizontal-discipline shapes codifying the "half-finished internals" pattern from cycles 829/831/834/835:

| Shape | Detection | Ship | Cycle |
|---|---|---|---|
| **#2 IR field ↔ reader parity** | ratchet lint (baseline of 186 known orphans) | `95a23c4a` | pre-resume |
| **#1 template ↔ route parity** | widened existing page-route-coverage (3→6 patterns, +2 render callers, +src/dazzle scan) | `8d076dc6` | pre-resume |
| **#3 module import-graph orphans** | on-demand `make audit-internals` + re-export pre-pass (83% FP → 150 candidates) | `fc8a2096` | pre-resume |
| **#4 external canonical-registry** | new assertion on external-resource allowlist (must cite #NNN / gap doc / cycle) | `e101fef7` | pre-resume |

Then 3 productive post-resume cycles:

| Cycle | Strategy | Outcome |
|---|---|---|
| 367 | finding_investigation | **#838** — TwoFactorConfig IR orphan; triple signal convergence (external-resource + page-route + reader-parity all point at 2FA) |
| 368 | framework_gap_analysis | `dev_docs/framework-gaps/2026-04-21-ir-policy-field-drift.md` — systematises #838 into a subsystem-wide pattern covering ~50 of the 186 baselined orphans (messaging, governance, grants, HLESS, approvals, LLM cost, appspec.hless_mode) |
| 369 | finding_investigation | **#839** — compliance pipeline orphans (citation/renderer/slicer tested-but-unwired, same shape as #834) |

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
| **838** | **367** | **OPEN** | **2FA subsystem: TwoFactorConfig IR has no producer/consumer** |
| **839** | **369** | **OPEN** | **Compliance pipeline: citation/renderer/slicer tested but unwired** |

**Downstream `/issues` queue now at 9 OPEN.** Three are 2FA-related (#829/#831/#838) and collectively describe the three-layer wiring gap documented in the cycle-368 gap doc.

## Horizontal-discipline lint stack (7 gates)

| Lint | Cycle | File | Shape |
|---|---|---|---|
| template orphan scan | 302/304 | `test_template_orphan_scan.py` | structural |
| page route coverage | 306-308 / post-342 | `test_page_route_coverage.py` | #1 |
| canonical pointer | 310 | `test_canonical_pointer_lint.py` | structural |
| template-none-safety | 284 | `test_template_none_safety.py` | structural |
| daisyui-in-python | 318 | `test_daisyui_python_lint.py` | structural |
| external-resource | 324 + 370 | `test_external_resource_lint.py` | #4 |
| **ir-field-reader-parity** | **367** | **`test_ir_field_reader_parity.py`** | **#2** |

Plus `test_dom_snapshots.py`, `test_card_safety_invariants.py`, and `mypy src/dazzle_ui/`. `make test-ux-deep` extends to core/cli/mcp/back mypy. `make audit-internals` generates `dev_docs/audit-internals.md` as advisory shape-#3 output.

## Silent-drift coverage

| # | Class | Status |
|---|---|---|
| 1 | Syrupy baselines | GATED (cycle 312) |
| 2 | UI type errors | GATED (cycle 314) |
| 3 | dist/ drift | WARNING (cycle 319) |
| 4 | Canonical-helper bypass | MANUAL |
| 5 | DaisyUI in Python HTML | GATED (cycle 318) |
| 6 | contract_audit hygiene | GATED downstream |
| **7** | **IR field consumer drift** | **GATED (cycle 367)** |
| **8** | **External-origin replacement-path** | **GATED (cycle 370/e101fef7)** |

## Loop health

- **Explore-budget velocity:** 3 productive cycles → +3 budget (95 → 98). At current rhythm, 2 more productive cycles reach 100 → deliberate batch reset by operator.
- **Finding rate post-resume:** 100% (3/3 cycles produced concrete artifacts). Pre-pause the loop was at ~20%.
- **Shape-#3 audit real-finding rate:** 2/150 entries = 1.3%. Not high, but 2/2 filings have been actionable, which is the rate that matters.
- **Synthesis debt:** 1 gap doc written this session; covers 6 clusters. Should be enough without another gap-analysis cycle for ~5 cycles.

## Framework-gap docs (recent)

- `2026-04-21-ir-policy-field-drift.md` — **NEW** (cycle 368)
- `2026-04-20-ux-cycle-silent-drift-classes.md` (cycle 317)
- `2026-04-20-external-resource-integrity.md` (cycle 300)

## Operator decision points

1. **Explore budget at 98/100** — one or two more productive cycles will hit the cap. Plan a batch-reset pass after that (skim the 9 OPEN issues, decide triage order, reset the counter).
2. **Issue queue stocked** — #829/#831/#838 are three separate filings on the 2FA subsystem; they naturally go together in one `/issues` pickup. Same for #830/#832/#833 (external-resource triad).
3. **Gap doc awaiting action** — the IR policy-field drift doc proposes per-cluster triage (wire vs retire). No single `/issues` pickup can resolve it; needs a subsystem-by-subsystem call from the operator.
4. **Loop cadence** — 15m is steady; no reason to change unless the next cycle or two produces nothing new.

## Where to look for more detail

- `dev_docs/ux-log.md` — full cycle-by-cycle journal (cycles 1→370)
- `dev_docs/ux-backlog.md` — EX rows + PROP rows
- `dev_docs/framework-gaps/` — consolidated theme analyses
- `dev_docs/audit-internals.md` — regenerate via `make audit-internals` (local-only, gitignored)
- `tests/unit/test_*lint*.py` + `tests/unit/test_ir_field_reader_parity.py` — all 7 horizontal-discipline lints
- `.claude/commands/ux-cycle.md` — the skill itself (playbook + heuristics)
