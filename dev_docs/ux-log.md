# UX Cycle Log

Append-only log of `/ux-cycle` cycles. Each cycle writes one section.

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
