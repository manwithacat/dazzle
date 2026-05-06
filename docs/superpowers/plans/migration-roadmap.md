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
| 12 | Production-path parity | ✓ Shipped | TestClient HTTP test for every example's primary list + simple_task VIEW/CREATE — pins Fragment chrome at the response layer |
| 13 | Audit completeness + CI gate | ✓ Shipped | entity_ref-based field-type resolution; per-example CI step (advisory); smoke + CLI tests relaxed to match honest audit |
| 14 | RefPicker primitive (Phase 2A) | ✓ Shipped | Typed REF-field primitive; adapter REF branch; page route ref_api threading; audit closes ref blocker — examples back to 78/78 honest |

**Today's coverage of the example apps (post-Plan-14 honest 100%):**

| App | Surfaces | Flipped (DSL) | Ready | Blocked |
|---|---|---|---|---|
| simple_task | 17 | 12 / 12 ✓ | 17/17 | 0 |
| contact_manager | 6 | 4 / 4 ✓ | 6/6 | 0 |
| support_tickets | 19 | 12 / 12 ✓ | 19/19 | 0 |
| ops_dashboard | 10 | 8 / 8 ✓ | 10/10 | 0 |
| fieldtest_hub | 26 | 24 / 24 ✓ | 26/26 | 0 |
| **Total** | **78** | **60 / 60 ✓** | **78/78** | **0** |

DSL/audit delta: framework-injected surfaces (`feedback_*`, `_admin_*`) appear in the audit count but are not authored in DSL — they pick up Fragment rendering automatically once the renderer registry is wired.

**Aggregated blockers (cross-app):** none. Phase 2A closed the REF gap (28 surfaces) via the typed RefPicker primitive. Remaining unsupported field types (UUID/JSON/FILE) do not appear on any audit-flippable surface across the examples — they're typically in pk position, not in section.elements.

---

## Where we're going

### Phase 2B — Aegismark and downstream

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

### Plan 14 — typed primitives are cheap; client integration is the load-bearing piece

Adding RefPicker as a new dataclass + renderer branch + adapter branch was three small commits. The integration work was threading `ref_api` from `FieldContext` through `_build_dispatch_ctx` into the field dict — five lines of plumbing in page_routes.py. The expensive thing was the design call: extend Combobox vs. add a new primitive. New primitive won (clean separation between static-options and lazy-fetched-options semantics) — and the substrate stayed cheap to extend.

Re-using existing Alpine machinery (`dz.filterRefSelect`) meant zero new client-side code. The Fragment renderer's contract was just "emit a `<select>` with the right `data-ref-api` attribute and an `x-init` hook"; the client side was already production-tested by the Jinja path.

### Plan 13 — the audit was lying

The dead `section.fields` loop (line 180-189 of `coverage.py`) never ran — `SurfaceSection.elements` is the right attribute name, not `.fields`. Five plans of audit-driven prioritisation operated on a 78/78 number that was structurally wrong. The honest number is 50/78, with all 28 newly-surfaced blockers on a single class (REF fields).

The lesson: TDD any new resolver against a synthetic appspec FIRST; never trust an audit you haven't proven walks the IR you think it walks. The CI gate is now in place per-example (advisory mode); next plan tightens to `--fail-on-blocked` after the adapter closes the REF gap.

### Plan 12 — services-on-app-state is the load-bearing fixture

The HTTP parity test initially failed because the bare FastAPI app didn't have `app.state.services` attached. `_maybe_dispatch_inner_html` (page_routes.py:1180) reads services from app state to route through the renderer registry; without it, dispatch silently returns None and the legacy template path runs. Result: 200 responses with full page chrome but zero Fragment classes — a green-looking failure mode that would have shipped if the test asserted only status code.

The fix mirrors what `DazzleBackendApp.build()` does at server.py:405-407 — `RuntimeServices()` + `register_default_renderers()` + `app.state.services = services`. This is now part of `_client_for()` in the test fixture and documented inline. Future tests that mount page routes directly need the same wiring.

Surfaced URL pattern: create surfaces are at `/<entity>/create`, not `/<entity>/new`. Pinned the test cases against the real route shape via in-process route introspection.

### Plan 11 — DSL/audit count delta is not a bug

The audit reports 78 surfaces; the DSL declares 60. The difference (18) is framework-injected: `feedback_*`, `_admin_health`, `_admin_deploys`. These surfaces are generated post-parse and inherit the renderer registry's defaults, so they ride along automatically once the rest of the app is flipped. The mass-flip helper correctly skips them (they have no DSL representation to edit).

---

## When this roadmap goes stale

- After Plan 12 ships: TestClient parity locked in. Update if it surfaces any production-path regressions the unit tests missed.
- After Plan 13 ships: CI gate active, entity-ref resolution closed. The audit becomes a hard gate, not advisory.
- Phase 2 kickoff: replace this doc with `docs/superpowers/plans/migration-roadmap-aegismark.md`. Keep this one as the historical record of the framework's own migration.
- If a Phase 2 closure costs substantially more than budgeted (>2× tasks): this is a signal the substrate has hidden assumptions worth surfacing. Stop, write a postmortem, decide whether to revisit Plan 1's primitive vocabulary.
