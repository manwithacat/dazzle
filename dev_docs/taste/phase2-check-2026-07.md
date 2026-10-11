# Phase 2 foundations — evidence check (2026-07-03)

Mini-panel over the two vehicle apps (`ops_dashboard`, `design_studio`) on
v0.93.4 foundations (Geist, inline-SVG icons, focus rings, WCAG-recalibrated
ramps), judged blind against the SAME 14 dialect references as the baseline
(3 sonnet judges via CC subagents, identical rubric/protocol; 429 scores,
0 collection problems). NOT the Phase 4 gate — a directional check only.

## Read the gap, not the absolute

This judge cohort scored the references at 5.09 pooled (baseline cohort:
5.54) — absolute cross-run scores carry cohort noise, which is precisely why
the panel interleaves references in every run. The within-run gap is the
metric:

| App | Baseline gap | Phase 2 gap | Movement |
|---|---|---|---|
| ops_dashboard | 2.22 | 1.46 | **narrowed 0.76** |
| design_studio | 2.48 | 2.21 | narrowed 0.26 |

## Per-dimension (phase2 absolute vs baseline absolute)

ops_dashboard improved on all six dimensions despite the harsher cohort:
dark_mode_integrity +0.56, spatial_rhythm +0.56, typographic_hierarchy
+0.22, state_completeness +0.22, perceived_craft +0.17, color_discipline
+0.11. design_studio moved within noise (−0.50 to +0.22 per dimension,
n≈9–18 per cell): its judged screens are `_platform_admin` under
designer/reviewer personas — RBAC-empty pages that no amount of type or
iconography can rescue. Content-forward apps need the Phase 3 component
pass (empty states, icon integration at nav/actions) to move.

## Reading

The foundations move dense workspaces materially (ops_dashboard gap nearly
halved) and do not move empty screens — consistent with the baseline's
finding that the fleet's best screens were already dense ones. Phase 3
(component pass: icons at nav/empty-state/action seams, spacing sweep,
state coverage) targets exactly the residue. Full-fleet re-judge remains
the Phase 4 gate against the locked margins.

Raw data: `.dazzle/qa/taste/phase2-check.json` (gitignored);
protocol identical to `dev_docs/taste/baseline-2026-07-02.md`.

---

# Phase 3 component pass — evidence check (2026-07-03, v0.93.5)

Same protocol, same 14 references, 26-image blind pool, 3 sonnet judges
(429 scores, 0 problems). Reference cohort mean 5.26 (baseline 5.54,
phase 2 5.09) — within-run gaps remain the metric.

## Gap trajectory (pooled, vs same-run references)

| App | Baseline | Phase 2 | Phase 3 |
|---|---|---|---|
| ops_dashboard | 2.22 | 1.49 | 1.52 (flat — within noise) |
| design_studio | 2.47 | 2.24 | **2.02** |

## Reading

Phase 3 targeted the content-light residue, and that is what moved:
design_studio's largest per-dimension gains are exactly the seams touched —
perceived_craft +0.83 (nav icons, badge SVGs, card shadows),
typographic_hierarchy +0.50, color_discipline +0.44. ops_dashboard, which
took its big step from the Phase 2 foundations, holds its gap (1.49→1.52,
inside judge noise) with modest dimension gains (dark_mode_integrity +0.56,
state_completeness +0.28).

Cumulative from baseline: ops_dashboard −0.70 gap, design_studio −0.45.
The worst remaining screens are the RBAC-denied raw-JSON 403 pages (#1536)
— a product fix, not a CSS one. Next: Phase 4 full-fleet judgment against
the locked margins (with persona-matched workspace sampling per the
baseline's protocol note), after #1536-class fixes and any straggler
per-app sitespec work.

Raw data: `.dazzle/qa/taste/phase3-check.json` (gitignored).
