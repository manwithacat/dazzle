# Typed Fragment Migration — Roadmap

**Status:** Active. Updated as plans ship.
**Source of truth for prioritisation:** `dazzle fragment-audit` (Plan 7).
**Last audit:** 2026-05-06 across all five example apps.

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

**Today's coverage of the example apps:**

| App | Ready | Blocked | % Ready |
|---|---|---|---|
| simple_task | 6 | 11 | 35% |
| contact_manager | 3 | 3 | 50% |
| support_tickets | 8 | 11 | 42% |
| ops_dashboard | 4 | 6 | 40% |
| fieldtest_hub | 8 | 18 | 31% |
| **Total** | **29** | **49** | **37%** |

**Aggregated blockers (cross-app):**

```
17  unsupported_mode=CREATE
17  unsupported_mode=EDIT
15  unsupported_mode=VIEW
 3  unsupported_feature=related_groups   (all double-blocked with VIEW)
```

---

## Where we're going

The audit data dictates the closure ordering. Each plan below is sized for one PR-cycle; cumulative coverage is the verification metric.

### Plan 8 — VIEW mode

**Closes:** `unsupported_mode=VIEW` (15 occurrences; 12 single-blocker, 3 also blocked on related_groups).
**Cumulative coverage after:** 41 / 78 = **53%**.
**Cost:** ~6–7 tasks. Lowest risk; salvages Plan 6's draft. Detail surfaces are read-only, no form scaffolding required.
**Why first:** smallest, lowest-risk, partially drafted. Validates the IR-to-Fragment field-rendering approach on read-only output before scaling to writable forms. Engineering economics says ship the smaller-risk plan first to validate the approach, then do the bigger plan with confidence.

### Plan 9 — Form modes (CREATE + EDIT bundled)

**Closes:** `unsupported_mode=CREATE` and `unsupported_mode=EDIT` together (34 occurrences).
**Cumulative coverage after:** 75 / 78 = **96%**.
**Cost:** ~10–12 tasks. Largest plan, but bundles two closures because they share ~80% of infrastructure (FormStack rendering, type-aware Field widgets, Submit, htmx form-post wiring, validation error display). The Fragment primitive library already has the building blocks (`FormStack`, `Field`, `Combobox`, `Submit` shipped in Plan 1); the work is in the IR-to-Fragment translation layer.
**Why bundled:** doing CREATE and EDIT in separate plans wastes the shared form scaffolding. One plan ships them together for economic efficiency.

### Plan 10 — related_groups feature

**Closes:** `unsupported_feature=related_groups` (3 occurrences, all already half-cleared by Plan 8).
**Cumulative coverage after:** 78 / 78 = **100%** example coverage.
**Cost:** ~5–7 tasks. Different structural shape from single-mode work — composite display of related entities below the main detail.
**Why last:** smallest leverage; all 3 affected surfaces are double-blocked on VIEW (which Plan 8 will have cleared). Independent enough to ship cleanly after CREATE+EDIT lands.

### Plan 11+ — Aegismark and downstream

Once examples hit 100%, point the audit at AegisMark. The `fragment-audit` CLI takes any project path; the same blocker-counting logic surfaces what AegisMark needs. Likely candidates from prior conversations: kanban (#1015), day timeline (#1016), pupil card (#1017), class strip (#1018) — but the audit will tell us exactly which ones, in what order, and how many surfaces each unblocks. No speculation needed.

---

## Verification rhythm

Each closure plan ends with a `dazzle fragment-audit` re-run as its stop-condition test. The aggregated-blockers list shrinks measurably; if it doesn't, the plan didn't actually close what it claimed.

CI gate (suggested but not yet wired): a `dazzle fragment-audit examples/<app> --fail-on-blocked` invocation that asserts an expected ready-count for each example. As coverage grows, the threshold moves up. By Plan 10 the gate is `--fail-on-blocked` with no arguments — every example must be 100% Fragment-renderable.

---

## When this roadmap goes stale

- After Plan 8 ships: re-run audit; update the "Where we are" table; verify cumulative coverage hit 53% as predicted.
- After Plan 9 ships: same. Verify CREATE+EDIT bundled plan landed without splitting.
- After Plan 10 ships: 100% example coverage. The roadmap pivots to Aegismark; this doc gets a new "Phase 2" section.
- If a closure costs substantially more than budgeted (>2× tasks): this is a signal the substrate has hidden assumptions worth surfacing. Stop, write a postmortem, decide whether to revisit Plan 1's primitive vocabulary.
