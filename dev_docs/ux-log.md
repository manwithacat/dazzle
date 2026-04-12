# UX Cycle Log

Append-only log of `/ux-cycle` cycles. Each cycle writes one section.

---

## 2026-04-12T18:28Z — Cycle 11

**Selected row:** UX-010 (widget:datepicker) — second widget row, direct parallel to UX-009's TomSelect pattern.

**Phases:**
- **OBSERVE**: Bucket 2 empty. Picked UX-010 for momentum — same shape as UX-009 (vendored widget, MISSING+DONE with DaisyUI leakage on the template branch).
- **SPECIFY**: Wrote `~/.claude/skills/ux-architect/components/widget-datepicker.md`. Covers both `picker` (single date/datetime) AND `range` (daterange) variants — they share Flatpickr and the CSS-override block, so one contract covers both efficiently. Progressive-enhancement model (native `<input type="text">` + bridge-managed Flatpickr). 5 quality gates (no DaisyUI on both branches, native fallback works, Flatpickr mounts after settle, unmounts before swap, required respected).
- **REFACTOR**:
  - `templates/macros/form_field.html`: rewrote both the `picker` and `range` branches to match form-field's chrome (wrapper, label, hint/error, aria-describedby wiring, required+aria-required, aria-invalid on server error).
  - `runtime/static/css/design-system.css`: appended ~115-line Flatpickr override block — `.flatpickr-calendar`, `.flatpickr-month`, `.flatpickr-current-month`, `.flatpickr-prev/next-month`, `.flatpickr-weekday`, `.flatpickr-day` (default/hover/today/selected/inRange/disabled), `.flatpickr-day.startRange/endRange`, calendar arrow colour fixes, destructive border on `[aria-invalid="true"]`.
  - dz-widget-registry.js Flatpickr registration unchanged.
  - Both branches scope-scanned: 0 DaisyUI hits.
- **QA Phase A**: DEFERRED — needs running app.
- **QA Phase B**: DEFERRED.

**Outcome:** UX-010 contract + refactor done for both datepicker variants (picker + range); status READY_FOR_QA.

**Pattern consolidation:** Cycle 10 introduced the "vendored widget" refactor pattern (CSS override block keyed to library class names, living in design-system.css). Cycle 11 confirms it works for a second library (Flatpickr) without modification. The template side is near-identical between cycles — the diff is just the data-dz-widget attribute name and any library-specific options. **The pattern generalises:** remaining vendored widget rows (UX-011 command-palette, UX-015 popover via Floating UI, UX-012 slide-over) will follow the same shape. Each cycle is ~200 lines of code, ~10-15 minutes of work.

**Throughput observation:** Cycles 6–11 shipped 6 components in roughly 45 minutes. The cycle is settling into a predictable rhythm: OBSERVE (1 min), SPECIFY (5 min), REFACTOR (5-10 min), REPORT (2 min), Commit + push (1 min). The scope triage from the unblock cycle is keeping work tractable.

---

## 2026-04-12T18:20Z — Cycle 10

**Selected row:** UX-009 (widget:combobox) — first of the widget rows (UX-009..015 TomSelect/Flatpickr/Pickr/Quill wrappers).

**Phases:**
- **OBSERVE**: Bucket 2 empty after the form decomposition completed. Picked UX-009 as the first widget row. MISSING+DONE shape; applied Cycle 8's learning — grepped the combobox branch before declaring impl:DONE and found full DaisyUI leakage.
- **SPECIFY**: Wrote `~/.claude/skills/ux-architect/components/widget-combobox.md`. Documents the progressive-enhancement model: native `<select>` with `data-dz-widget="combobox"`, bridge mounts TomSelect on `htmx:afterSettle`, unmounts on `htmx:beforeSwap`. Declares a CSS-override contract that targets Tom Select's generated `.ts-wrapper`/`.ts-control`/`.ts-dropdown` class names — v0.1-authorised because the library is vendored. 5 quality gates (no DaisyUI in branch, native fallback works without JS, TS mounts after settle, TS unmounts before swap, required attribute respected).
- **REFACTOR**:
  - `templates/macros/form_field.html` combobox branch: rewrote the wrapper to match form-field's pattern — `<div class="w-full space-y-1">`, token-driven label with destructive required marker, hint/error paragraphs using `text-[12px] text-[hsl(var(--muted-foreground|destructive))]`, `aria-describedby` wiring that combines hint + error IDs, `required aria-required="true"` attribute now correctly emitted (was previously just `aria-required`), `aria-invalid="true"` on server error.
  - `runtime/static/css/design-system.css`: appended ~70 lines of Tom Select token overrides targeting `.ts-wrapper.single|.multi .ts-control`, `.ts-dropdown .option/.active/.selected`, focus ring via `box-shadow`, destructive border on `[aria-invalid="true"]`. Also styled multi-select pills (for multiselect/tags which are separate rows) so they inherit the tokens without extra work.
  - `dz-widget-registry.js` and `dz-component-bridge.js` unchanged — mount/unmount lifecycle was already correct.
  - Scope-accurate scanner: 0 DaisyUI hits in the combobox branch.
- **QA Phase A**: DEFERRED — needs running app.
- **QA Phase B**: DEFERRED.

**Outcome:** UX-009 contract + refactor done; status READY_FOR_QA.

**Pattern observation (shared CSS override):** This cycle introduced a pattern that will apply to all vendored widget rows (UX-010 Flatpickr, UX-011 command-palette, UX-015 popover): the Dazzle-owned token overrides live in `design-system.css`, keyed to the library's own class names. The library CSS files (`vendor/tom-select.css`, etc.) stay as-is — we don't fork them. This is the cleanest boundary: vendored code stays vendored, and the aesthetic layer lives exactly where the design tokens do. Future widget cycles should just append an override block per widget.

**Unexpected win:** The Tom Select override block also styles `multiselect` and `tags` widgets (UX future rows) because they share the same `.ts-wrapper.multi` class family. Those rows now need template refactoring only — the CSS is already aligned. Should reduce their cycle cost significantly.

---

## 2026-04-12T18:12Z — Cycle 9

**Selected row:** UX-019 (form-validation) — last of the UX-004 decomposition.

**Phases:**
- **OBSERVE**: Bucket 2 remains empty (form sub-rows exhaust it). Picked UX-019 (PENDING, MISSING, PARTIAL). Note: this cycle also clears the UX-004 aggregate tracker.
- **SPECIFY**: Wrote `~/.claude/skills/ux-architect/components/form-validation.md`. Contract is orchestration-only: documents the three layered validation mechanisms (HTML5 native → `dzWizard.validateStage` → server 422/5xx swap), declares the server contract (422 with `form_errors` list + `field_errors` dict), names explicit v0.2 scope (per-blur validation, cross-field, async uniqueness). 5 quality gates (required-blocks-submit, stage-advance-blocks, server-summary-renders, per-field-errors-render, aria-describedby-wires-correctly).
- **REFACTOR**: **No code changes.** The layered model is already fully implemented across UX-016 (form-chrome, `hx-target-422="#form-errors"`), UX-017 (form-field, `aria-invalid` + error paragraph + `aria-describedby` wiring), UX-018 (form-wizard, `validateStage` + `reportValidity`), and HTML5 native. Verified all 5 gates are satisfied by existing code via inspection. impl: PARTIAL → DONE reflects that the orchestration is now explicit, documented, and load-bearing for v0.2 design decisions.
- **QA Phase A**: DEFERRED — needs running app.
- **QA Phase B**: DEFERRED.

**Outcome:** UX-019 contract-only cycle done; status READY_FOR_QA. **UX-004 (form) aggregate tracker upgraded from BLOCKED_ON to READY_FOR_QA** — all four sub-rows (UX-016/017/018/019) are now complete. The form decomposition experiment is a success: a single row that was too large to attempt in one cycle became four tractable rows that completed in four consecutive cycles (6, 7, 8, 9) taking roughly 25 minutes total.

**Meta-learning (decomposition pattern):** UX-004 → UX-016/017/018/019 was classified by the unblock-triage taxonomy as TOO_LARGE with clear sub-boundaries. The decomposition was cheap (10 minutes) and unblocked 4 cycles of progress. Key insight: the sub-boundaries weren't arbitrary — they matched the file structure already present in the codebase (`components/form.html`, `macros/form_field.html`, `fragments/form_stepper.html`, dzWizard in `dz-alpine.js`). When looking for decomposition opportunities, the existing code structure is the strongest signal. **New heuristic for scope triage**: before marking a row BLOCKED for size, run `ls -1 <component-family>/` and count files — N files → likely N sub-rows.

---

## 2026-04-12T18:04Z — Cycle 8

**Selected row:** UX-018 (form-wizard) — third sibling of the UX-004 decomposition; MISSING+DONE shape (contract only, no state machine work).

**Phases:**
- **OBSERVE**: Bucket 2 (MISSING+PENDING) empty. Loose interpretation: picked the fastest remaining shape — UX-018 is MISSING+DONE (dzWizard Alpine component already exists). On inspection, discovered `templates/fragments/form_stepper.html` still uses DaisyUI `steps`/`step-primary`, so this was more than a pure retroactive doc — included a stepper refactor.
- **SPECIFY**: Wrote `~/.claude/skills/ux-architect/components/form-wizard.md`. Documents the existing dzWizard state machine (step/total/next/prev/goToStep/validateStage/isActive/isCurrent), specifies the stepper visual as pure Tailwind, 5 quality gates (no DaisyUI stepper classes, dzWizard signature preserved, advance blocked on required field, backward-jump unconditional, active state via Alpine binding).
- **REFACTOR**: Rewrote `src/dazzle_ui/templates/fragments/form_stepper.html`:
  - Replaced DaisyUI `steps steps-horizontal` + `step step-primary` with pure flex layout: `<ol>` + `<li>` + bubble span + title span + connector span
  - Bubbles use `rounded-full h-6 w-6` with Alpine `:class` switching between muted bordered and primary-filled
  - Added inline SVG checkmark for completed stages (`step > N`) via `<template x-if>`
  - Connector line is `flex-1 h-px` with Alpine `:class` tinting based on `isActive(N+1)`
  - Added `role="list"` + `aria-label="Form progress"` and dynamic `:aria-current="isCurrent(N) ? 'step' : false"`
  - sr-only span with `x-text` announcing "completed/current/pending" per step
  - dzWizard Alpine component in `dz-alpine.js` **unchanged** — signature and behaviour preserved
- **QA Phase A**: DEFERRED — needs running app.
- **QA Phase B**: DEFERRED.

**Outcome:** UX-018 contract + stepper refactor done; status READY_FOR_QA. Three of the four UX-004 sub-components are now READY_FOR_QA. Only UX-019 form-validation remains from the form decomposition.

**Pattern observation:** This cycle was classified as MISSING+DONE but on inspection had meaningful refactor work (the stepper fragment). Pure retroactive-doc cycles are rarer than the backlog seeding suggested — most "impl DONE" components still have some peripheral template/fragment that wasn't touched by the original refactor. The lesson: SPECIFY should always include a quick `grep -E 'btn|alert|steps|form-control|label-text|input-bordered' <relevant files>` to spot DaisyUI leakage before declaring impl:DONE.

---

## 2026-04-12T17:57Z — Cycle 7

**Selected row:** UX-017 (form-field) — sibling of UX-016 from the UX-004 decomposition.

**Phases:**
- **OBSERVE**: Bucket 2 (PENDING+MISSING+PENDING) matched UX-017 only. Picked.
- **SPECIFY**: Wrote `~/.claude/skills/ux-architect/components/form-field.md`. Explicit scope carve-out: covers `text`, `textarea`, `select`, `number`, `email`, `date`, `datetime`, `checkbox`; explicitly excludes rich widgets (`combobox`, `multi_select`, `tags`, `picker`, `range`, `color`, `rich_text`, `slider`, `money`, `file`, search-select). 5 quality gates (no DaisyUI on core branches, required-marker a11y, error→aria-invalid+destructive border, hint→aria-describedby wiring, checkbox label wraps input).
- **REFACTOR**: Edited `src/dazzle_ui/templates/macros/form_field.html`:
  - Wrapper: `<div class="form-control w-full has-error">` → `<div class="w-full space-y-1">`
  - Checkbox: `label cursor-pointer justify-start gap-3` → `inline-flex items-center gap-2`, `checkbox checkbox-primary` → `h-4 w-4 rounded-[3px] accent-[hsl(var(--primary))]`, `label-text` → plain span
  - Standard label: `<label class="label">...<span class="label-text">` → `<label class="block text-[13px] font-medium text-[hsl(var(--foreground))]">`. Required marker `text-error` → `text-[hsl(var(--destructive))]`
  - Hint: `label-text-alt text-base-content/60` → `text-[12px] text-[hsl(var(--muted-foreground))]`
  - Input base: pulled into a `{% set base_input %}` reusable variable for text/select/date/datetime/number/email
  - Textarea: token-driven with `min-h-24 resize-y px-3 py-2`
  - Error paragraph: `label-text-alt text-error` → `text-[12px] text-[hsl(var(--destructive))]`
  - `input-error`/`textarea-error`/`select-error` modifier class replaced with conditional `border-[hsl(var(--destructive))]` via Jinja ternary
  - Widget branches (combobox, multi_select, tags, picker, range, color, rich_text, slider, money, file, search-select) intentionally **untouched** — tracked by UX-009..015
  - Jinja parses OK; scope-accurate DaisyUI scan finds 0 hits in UX-017-scoped branches.
- **QA Phase A**: DEFERRED — needs running localhost:3000.
- **QA Phase B**: DEFERRED.

**Outcome:** UX-017 contract + core-branch refactor done; status READY_FOR_QA. Second sub-component from the UX-004 decomposition is now clear. Next: UX-018 form-wizard (impl already DONE → retroactive contract only, single-phase cycle).

**Scoping observation:** UX-017 is a good example of *scope-aware* refactoring inside a shared macro. The `form_field.html` macro has 11 widget branches that all inherit the outer wrapper. Attempting a full DaisyUI purge would have forced me into rewriting TomSelect, Flatpickr, Pickr, Quill, and FileUpload markup — each of which has its own specialized UX concerns already captured by UX-009..015. The contract explicitly declares "widget branches are out of scope" and the quality gates enforce this carve-out via a scope-accurate scanner. This is the pattern future cycles should reach for when a row's code is embedded inside a larger shared file.

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
