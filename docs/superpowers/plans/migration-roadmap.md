# Typed Fragment Migration — Roadmap

**Status:** Active. Updated as plans ship.
**Source of truth for prioritisation:** `dazzle fragment-audit` (Plan 7).
**Last audit:** 2026-05-06 across all five example apps — 78 / 78 ready, 0 blocked.

---

## Where we are

| Plan | Title | Status | What it shipped |
|---|---|---|---|
| 1 | Foundations | ✓ Shipped | Typed Fragment library — 34 frozen-dataclass primitives, FragmentRenderer, registry, errors, htmx wrappers |
| 2 | Integration | ✓ Shipped | `render:` DSL clause, IR fields, parser, linker validation, RuntimeServices wiring |
| 3 | First conversion | ✓ Shipped | Real adapters, dispatch wiring, `simple_task.task_list` flipped, structural-parity test |
| 4 | Primitive CSS | ✓ Shipped | `components/fragment-primitives.css` — Surface/Heading/Region.list/Text/Table styled |
| 5 | Dispatch uniformity | ✓ Shipped | `FragmentSurfaceRenderer` adapter; dispatcher reduced to single uniform call |
| 6 | Detail mode (draft) | ⊘ Superseded by Plan 8 | Doc retained as design reference |
| 7 | Coverage audit | ✓ Shipped | `dazzle fragment-audit` CLI — text + JSON + CI gate |
| 8 | VIEW mode | ✓ Shipped | Adapter `_build_view`, definition-list Region kind, Stack/Row/Heading/Text composition; CSS for `.dz-region--kind-detail` |
| 9 | Form modes (CREATE + EDIT) | ✓ Shipped | Adapter `_build_form`, type-aware widget mapping, FormStack/Field/Combobox/Submit primitives, form CSS |
| 10 | related_groups feature | ✓ Shipped | Region(kind="related") wrapper, Skeleton placeholder for htmx-loaded children, related-group CSS |
| 11 | Mass surface flip | ✓ Shipped | `scripts/flip_to_fragment.py` helper; 60 DSL surfaces flipped across 5 apps; per-example smoke test |

**Today's coverage of the example apps:**

| App | Surfaces | Flipped (DSL) | Ready (audit) | Blocked |
|---|---|---|---|---|
| simple_task | 17 | 12 / 12 ✓ | 17 | 0 |
| contact_manager | 6 | 4 / 4 ✓ | 6 | 0 |
| support_tickets | 19 | 12 / 12 ✓ | 19 | 0 |
| ops_dashboard | 10 | 8 / 8 ✓ | 10 | 0 |
| fieldtest_hub | 26 | 24 / 24 ✓ | 26 | 0 |
| **Total** | **78** | **60 / 60 ✓** | **78** | **0** |

DSL/audit delta: framework-injected surfaces (`feedback_*`, `_admin_*`) appear in the audit count but are not authored in DSL — they pick up Fragment rendering automatically once the renderer registry is wired.

**Aggregated blockers (cross-app):** none. The substrate held — the mass flip applied without any adapter, dispatch, or CSS regression.

---

## Where we're going

### Plan 12 — Production-path parity test (planned)

**Goal:** Extend the parity test from in-process renderer calls to a TestClient-driven request through the real FastAPI route stack. Catches integration regressions the unit-level parity test can miss (route handler context shape, htmx swap headers, error-response wrapping).

**Cost:** ~3–4 tasks. Builds on `tests/integration/test_examples_fragment_smoke.py`.

### Plan 13 — CI gate + audit completeness (planned)

**Goal:** Wire `dazzle fragment-audit examples/<each> --fail-on-blocked` into CI for all five examples. Close the audit's entity-field-type resolution gap so REF/UUID/JSON/FILE actually surface as blockers (today the audit walks SurfaceElement which only carries name+label).

**Cost:** ~4–6 tasks. The CI wiring is small; the entity-ref resolution is where the design work is.

### Phase 2 — Aegismark and downstream

With 100% example coverage and a CI gate locked in, point the audit at AegisMark. The `fragment-audit` CLI takes any project path; the same blocker-counting logic surfaces what AegisMark needs. Likely candidates from prior conversations: kanban (#1015), day timeline (#1016), pupil card (#1017), class strip (#1018) — but the audit will tell us which ones, in what order, and how many surfaces each unblocks. No speculation needed.

---

## Verification rhythm

Each closure plan ends with a `dazzle fragment-audit` re-run as its stop-condition test. The aggregated-blockers list shrinks measurably; if it doesn't, the plan didn't actually close what it claimed.

CI gate (Plan 13 will wire this): `dazzle fragment-audit examples/<app> --fail-on-blocked` for every example. Today the assertion lives in `tests/integration/test_examples_fragment_smoke.py` as a parametrised test — same effect, different transport.

---

## Lessons learned

### Plan 11 — mass flip applied cleanly

74 DSL-level surface flips across 5 apps, zero adapter regressions, zero CSS gaps, zero dispatch errors, zero parse failures. The substrate's typed-from-the-start design held under bulk migration — this is the strongest validation yet that the Fragment approach scales beyond single-surface conversions.

The discovery log table the plan reserved for "issues found during the flip" remained empty. That's data: the audit-then-flip-then-verify rhythm works, and the substrate's invariants don't drift between apps.

### Plan 11 — DSL/audit count delta is not a bug

The audit reports 78 surfaces; the DSL declares 60. The difference (18) is framework-injected: `feedback_*`, `_admin_health`, `_admin_deploys`. These surfaces are generated post-parse and inherit the renderer registry's defaults, so they ride along automatically once the rest of the app is flipped. The mass-flip helper correctly skips them (they have no DSL representation to edit).

---

## When this roadmap goes stale

- After Plan 12 ships: TestClient parity locked in. Update if it surfaces any production-path regressions the unit tests missed.
- After Plan 13 ships: CI gate active, entity-ref resolution closed. The audit becomes a hard gate, not advisory.
- Phase 2 kickoff: replace this doc with `docs/superpowers/plans/migration-roadmap-aegismark.md`. Keep this one as the historical record of the framework's own migration.
- If a Phase 2 closure costs substantially more than budgeted (>2× tasks): this is a signal the substrate has hidden assumptions worth surfacing. Stop, write a postmortem, decide whether to revisit Plan 1's primitive vocabulary.
