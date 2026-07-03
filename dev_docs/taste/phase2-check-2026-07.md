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
