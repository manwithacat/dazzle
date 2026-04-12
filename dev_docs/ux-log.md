# UX Cycle Log

Append-only log of `/ux-cycle` cycles. Each cycle writes one section.

---

## 2026-04-12T17:49Z — Cycle 6

**Selected row:** UX-016 (form-chrome) — first cycle after unblock triage; highest-priority PENDING+MISSING+PENDING.

**Phases:**
- **OBSERVE**: Priority bucket 2 matched UX-016 and UX-017 (from UX-004 decomposition). Picked UX-016 (form-chrome) — smaller, self-contained, does not depend on form-field.
- **SPECIFY**: Wrote `~/.claude/skills/ux-architect/components/form-chrome.md`. Linear aesthetic, server-driven scaffold delegating fields to UX-017 and wizard to UX-018. 5 quality gates (no DaisyUI, error summary render, submit disable on request, wizard nav visibility by stage, cancel is a real `<a>`).
- **REFACTOR**:
  - Rewrote `src/dazzle_ui/templates/components/form.html` — replaced `btn btn-primary` / `btn btn-ghost` with token-driven pure-Tailwind button classes using `hsl(var(--*))` variables; added `htmx-request:opacity-60` for submitting state; added `border-t border-[hsl(var(--border))]` to action bar.
  - Rewrote `src/dazzle_ui/templates/fragments/form_errors.html` — replaced `alert alert-error` DaisyUI pattern with destructive-token border/background and inline exclamation-triangle SVG.
  - Jinja parse verified for both.
- **QA Phase A**: DEFERRED — `dazzle ux verify --contracts` needs a running app on localhost:3000.
- **QA Phase B**: DEFERRED — same.

**Outcome:** UX-016 contract + refactor done; status READY_FOR_QA (has stable URLs — unlike modal/toast this appears on any form surface). 2 DaisyUI class families removed (`btn*`, `alert*`) from form scaffold.

**Observation:** The unblock triage paid off immediately. UX-004 was unworkable as a single row; decomposed into 4 sub-components, the first (form-chrome) was a clean one-cycle job. form-field (UX-017) is up next at the same priority, and form-wizard (UX-018) is already impl:DONE so it only needs a retroactive contract. The form aggregate row (UX-004) will naturally clear once all four sub-rows are READY_FOR_QA.

---

## 2026-04-12T16:56Z — Unblock Triage (out-of-cycle)

**Trigger:** User request to identify blocker types and unblock UX-004 via agent cognition.

**Actions:**

1. **Added new status values to the backlog legend:**
   - `BLOCKED_ON: UX-NNN` — row depends on another row; re-prioritises the dependency
   - `NEEDS_HARNESS` — event-triggered component needs a test harness before QA can run
   - `READY_FOR_QA` — work done, awaiting running app for Phase B verification

2. **Re-classified existing rows:**
   - UX-001/002/003 (dashboard-grid, data-table, card): `DONE` → `READY_FOR_QA`
   - UX-005 (modal): `PENDING` → `NEEDS_HARNESS`
   - UX-006/007/008 (filter-bar, search-input, pagination): `PENDING` → `READY_FOR_QA`
   - UX-013 (toast): `PENDING` → `NEEDS_HARNESS`

3. **Decomposed UX-004 (form)** — BLOCKED → BLOCKED_ON: UX-016..019, with four new sub-components added:
   - **UX-016 form-chrome** — outer shell (multi-section layout, submit bar, error summary) — `impl: PENDING`
   - **UX-017 form-field** — individual field macro (form_field.html) — `impl: PENDING`
   - **UX-018 form-wizard** — multi-step navigation state machine (dzWizard) — `impl: DONE` (already exists as Alpine component)
   - **UX-019 form-validation** — client-side validation orchestration — `impl: PARTIAL`

**Agent cognition unblock-triage strategy:**

| Blocker type | Agent can resolve? | Action |
|---|---|---|
| TOO_LARGE (composite with clear sub-boundaries) | **Yes** | Decompose into sub-component rows |
| AMBIGUOUS_DESIGN | No | Emit `ux-needs-human` signal, leave BLOCKED |
| MISSING_DEPENDENCY | **Yes** | Re-queue dependency at higher priority |
| NO_TESTABLE_URL | Partially | New state `NEEDS_HARNESS`; agent can write harness |
| STAGNATION_ON_REFACTOR | Sometimes | Smaller scope retry or decomposition |

**Result:** UX-004 unblocked via decomposition. 4 new backlog rows available for picking. The backlog now has explicit distinguishing states for the three different "waiting" conditions (human, harness, infra).

---

## 2026-04-12T16:51Z — Cycle 5

**Selected row:** UX-008 (pagination) — final row in the retroactive run.

**Phases:**
- **OBSERVE**: Priority scan picked UX-008, last of the `MISSING + PARTIAL` rows touched during UX-002.
- **SPECIFY**: Wrote `~/.claude/skills/ux-architect/components/pagination.md`. Linear aesthetic, server-authoritative state, 5 quality gates (filter preservation, active visual, prev/next disabling, row count math, bulk count override).
- **REFACTOR**: Already done as part of UX-002.
- **QA**: DEFERRED.

**Outcome:** UX-008 retroactive contract documented.

**End of retroactive run.** Backlog now has:
- 3 DONE rows (UX-001/002/003 dashboard/table/card — awaiting QA)
- 1 DONE+refactor row (UX-005 modal — awaiting QA)
- 1 DONE+refactor row (UX-013 toast — awaiting QA)
- 3 retroactively documented (UX-006/007/008 — awaiting QA)
- 1 BLOCKED row (UX-004 form — needs decomposition)
- 7 remaining `MISSING + DONE` widget/standalone rows (UX-009-015)

Next cycle will shift from "retroactive documentation" to "contract writing for already-implemented vendor widgets". UX-009 (widget:combobox) is the first.

---

## 2026-04-12T16:48Z — Cycle 4

**Selected row:** UX-007 (search-input) — continuing retroactive documentation run.

**Phases:**
- **OBSERVE**: Priority: UX-007 and UX-008 remain in impl:PARTIAL+MISSING state (already restyled as part of UX-002). Picked UX-007.
- **SPECIFY**: Wrote `~/.claude/skills/ux-architect/components/search-input.md`. Linear aesthetic, 5 quality gates (debounce, clear reset, clear visibility, focus ring, query in request URL).
- **REFACTOR**: Already done as part of UX-002. No changes needed.
- **QA**: DEFERRED — same as filter-bar (subset of data-table QA).

**Outcome:** UX-007 retroactive contract documented; impl already DONE; QA deferred.

**Cumulative state:** 4 cycles, 4 components spec-governed (modal, toast, filter-bar, search-input). Next cycle targets UX-008 (pagination) to finish the retroactive run, then widget wrappers.

---

## 2026-04-12T16:41Z — Cycle 3

**Selected row:** UX-006 (filter-bar) — fastest possible cycle (retroactive contract for already-refactored component).

**Phases:**
- **OBSERVE**: Priority scan found UX-006/007/008 as impl:PARTIAL (already restyled as part of UX-002). Picked UX-006 as the first. This is the optimal row shape for the current loop state — no refactor work, just contract writing.
- **SPECIFY**: Wrote `~/.claude/skills/ux-architect/components/filter-bar.md`. Linear aesthetic, server-driven with client-held transient input state, 5 quality gates (text debounce, select immediacy, multi-filter includes, async ref options, empty-value clears).
- **REFACTOR**: Verified zero DaisyUI classes remain — already done as part of UX-002 data-table rebuild.
- **QA**: DEFERRED — filter-bar is only rendered inside a data-table on a list page. Its QA is a subset of the data-table QA (which is itself pending a running app for UX-002 verification).

**Outcome:** UX-006 filter-bar contract documented; impl already DONE; QA deferred.

**Pattern observation:** UX-007 (search-input) and UX-008 (pagination) are in exactly the same state — impl:PARTIAL from the UX-002 rebuild, just needing contracts. These will be the next 2 fastest cycles if picked. The loop is effectively **documenting what was already done** for these rows, which is valuable but not new work.

**Learning 7:** The backlog should distinguish "retroactive documentation" from "new work". After a multi-component refactor (like UX-002 which touched filter-bar, search-input, pagination), the derived rows should be seeded as `contract: DRAFT, impl: DONE` so the cycle knows they only need contract writing. Currently they're seeded as `contract: MISSING, impl: PARTIAL` which looks ambiguous.

---

## 2026-04-12T16:35Z — Cycle 2

**Selected row:** UX-013 (toast) — via loose interpretation of priority function.

**Phases:**
- **OBSERVE**: After Cycle 1, no rows strictly matched priority bucket 2 (`contract: MISSING` AND `impl: PENDING`). UX-004 BLOCKED, UX-005 status PENDING but work DONE. Remaining rows have either `impl: PARTIAL` (UX-006-008) or `impl: DONE` (UX-009-015). Applied loose interpretation: bucket 2 includes any PENDING + MISSING regardless of impl. Picked UX-013 (toast) as smallest scope for contract-only cycle.
- **SPECIFY**: Wrote `~/.claude/skills/ux-architect/components/toast.md`. Linear aesthetic, server-emitted OOB fragments with client queue via `dzToast` Alpine. 5 quality gates covering auto-dismiss, stacking, pause-on-hover, level distinguishable, accessible aria-live.
- **REFACTOR**: Rewrote `src/dazzle_ui/templates/fragments/toast.html` from 5 lines of DaisyUI (`alert alert-{level}`) to pure Tailwind with inline SVG icons per level, `border-l-4` accent in level colours, `hsl(var(--*))` design-system variables, aria-live polite/assertive by severity.
- **QA Phase A**: SKIPPED (toast has no stable URL — OOB swap only).
- **QA Phase B**: DEFERRED (event-triggered, needs a trigger flow).

**Outcome:** UX-013 toast contract + fragment refactor done; dzToast Alpine unchanged; QA deferred.

**Additional learnings (beyond Cycle 1):**
5. **Priority function has gaps.** It defines `contract: MISSING and impl: PENDING` as bucket 2, but most remaining rows have `impl: PARTIAL` or `impl: DONE` after earlier cross-component work. The function should have explicit buckets for `MISSING + PARTIAL` and `MISSING + DONE` — the latter is actually fastest (just needs a contract written, no refactor).
6. **The state machine doesn't track "work done, awaiting QA".** UX-005's status stayed PENDING even though contract + impl were DONE, because QA was deferred. A `READY_FOR_QA` state would be clearer, and the priority function could surface these rows as high priority when a running app becomes available.

---

## 2026-04-12T16:24Z — Cycle 1

**Selected row:** UX-005 (modal) — after BLOCKING UX-004 (form) for scope.

**Phases:**
- **OBSERVE**: Priority function picked UX-004 (form) as highest PENDING with contract MISSING + impl PENDING. On inspection, form is a composite component (chrome, fields, wizards, validation, 8 widgets) — too large for one cycle. Marked UX-004 BLOCKED with decomposition note. Re-ran priority and picked UX-005 (modal).
- **SPECIFY**: Wrote `~/.claude/skills/ux-architect/components/modal.md`. Linear aesthetic, native `<dialog>` model (server-driven content + client-driven lifecycle), 5 quality gates covering native semantics, Esc, backdrop click, focus restoration, body scroll lock.
- **REFACTOR**: Rewrote `src/dazzle_ui/templates/components/modal.html` from 35 lines of DaisyUI to pure Tailwind + design-system HSL variables. Uses native `<dialog>` with `open:` variant for enter animation, `::backdrop` pseudo-element for overlay, `<form method="dialog">` for close affordances (no JS handlers needed). Alpine `x-effect` for body scroll lock.
- **QA Phase A** (HTTP contracts): SKIPPED — modal is not rendered in any landing page; it's fetched via `hx-get` on demand and doesn't have a stable URL for contract verification.
- **QA Phase B** (Playwright agent): DEFERRED — requires a running Dazzle app with a button flow that opens the modal. No example app currently triggers a standalone modal on a deterministic path.

**Outcome:** UX-005 modal contract + refactor complete; QA deferred.

**Learnings for loop design:**
1. **Scope triage is a needed step.** The priority function doesn't account for component size. Large composite components need decomposition before the loop can work on them. Either SPECIFY should include a size-check, or the seed step should decompose large components into sub-components up front.
2. **Not all components have a testable URL.** Modal, toast, confirm-dialog, popover — these are event-triggered components with no direct page to load. QA needs a test harness pattern (like the `test-dashboard.html` / `test-data-table.html` files) rather than real example apps.
3. **The "canonical example + QA" pattern doesn't fit event-triggered components.** The spec assumed every component is rendered somewhere on a landing page. Many aren't.
4. **Phase A (HTTP contracts) has narrow applicability.** It works for list/detail/workspace pages that `generate_contracts()` produces but not for on-demand components. The cycle should skip Phase A cleanly rather than treat it as mandatory.

**Next cycle** will pick UX-006 (filter-bar) if backlog priority puts it next — contract MISSING, impl PARTIAL.

---
