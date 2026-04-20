# PR #600 Dormant Alpine Primitives

**Date**: 2026-04-20 (cycle 287, following cycle 286 Heuristic-1 save)
**Class**: Framework governance / dead-code hygiene
**Status**: Open — needs product-direction decision

## Problem statement

PR #600 ("migrate dz.js UI features to Alpine.js") shipped a set of
general-purpose Alpine primitives intended for reuse across the
framework. Two of those primitives have **zero production consumers**
today, despite being contracted, tested via the widget harness
(UX-020), and ready for adoption:

1. **`components/alpine/dropdown.html`** — generic menu dropdown with
   click-outside dismiss + Escape-key handler + 3-branch item renderer
   (href / hx_delete / placeholder). Contract: cycle 286's
   `alpine-dropdown.md` dormant-governance doc. Consumer count: 0.
2. **`components/alpine/confirm_dialog.html`** — native-`<dialog>`
   confirmation dialog with `dzConfirm` Alpine controller + `dz-confirm`
   window-event API. Contracted as **UX-014** in cycle 130, QA'd via
   the UX-020 widget harness in cycle 175. Consumer count: 0 in
   production templates.

Cycle 286 discovered #1 during a Heuristic-1 audit — cycle 237's
coverage-map claim of "42 call sites" for `dropdown.html` turned out
to be wrong; actual production consumers = zero. Cycle 287 discovered
#2 during a follow-up orphan-sweep — `confirm_dialog.html` has zero
production `{% include %}` consumers; the only references are the
component's own `x-data="dzConfirm"` anchor and the dev-only
`test-event-widgets.html` harness (UX-020).

The `dzConfirm` mechanism is particularly interesting because the
framework ships:
- The template (unused in production)
- The Alpine data component in `dz-alpine.js:83` (hooks `window`
  listener for `dz-confirm` events)
- An event-dispatch API that consumer code could use
  (`$dispatch('dz-confirm', {message, action, method})`)

So consumer code that dispatches `dz-confirm` expecting the dialog to
render would silently no-op — no dialog element exists in any
production-rendered page to pick up the event.

## Evidence

- **Cycle 286 log** — `alpine/dropdown.html` zero-consumer discovery
  via Heuristic 1. Cycle 237 claim was wrong.
- **Cycle 287 orphan-sweep** — targeted grep for
  `components/alpine/*.html` references across `src/` and `tests/`:
  - `slide_over.html` → 1 production consumer
    (`filterable_table.html:327`) — **not orphaned**
  - `dropdown.html` → 0 production consumers
  - `confirm_dialog.html` → 0 production consumers
- **`dz-alpine.js:83`** — `Alpine.data("dzConfirm", …)` controller is
  defined + registers a `window.addEventListener("dz-confirm", …)`
- **`test-event-widgets.html:213`** — the ONLY non-template reference
  to `dzConfirm` or the dialog element. Dev harness, not a user-facing
  page.
- **SOURCES.txt** — both orphan templates ship with the package's
  Python wheel. They're present in every installed Dazzle but never
  `{% include %}`'d by any rendering surface.

## Root cause hypothesis

PR #600 was a framework-layer migration (dz.js → Alpine.js). The
primitives were written as "available tools" for future UI features,
but the feature-level consumers never landed. In the 2+ years since
(cycle 237 coverage-map mentions these as active, but that map was
optimistic — the actual call-site count was mis-measured), no product
work has adopted either primitive.

The confirm-dialog specifically is probably a victim of HTMX's built-in
`hx-confirm` attribute being "good enough" for most delete flows —
which explains why no adopter ever replaced raw `hx-confirm="Are you
sure?"` text with the richer dialog. Similarly, dropdown usage in the
framework gets subsumed by context-menu, popover, and the per-row
action-link patterns already in use.

Not a defect. Not a drift class. Just **dead-code governance debt**.

## Fix sketch

Three options, in increasing decisiveness:

### Option A (minimal): explicit dormant annotation
Keep both templates + contracts, but add a "DORMANT: zero production
consumers since PR #600" banner comment at the top of each template.
Pros: preserves optionality if someone later wants to adopt. Cons:
dead-code-that-says-it's-dead is still dead code, adds governance
weight.

### Option B (promotion): adopt by landing one consumer each
Find one legitimate feature that would benefit from each primitive and
wire it up. Examples:
- **Dropdown** could replace the inline 3-button row in `list.html`'s
  actions area (region_actions + CSV export) with a kebab-menu
  dropdown. That collapses a widening horizontal toolbar into a single
  trigger + menu.
- **Confirm-dialog** could replace `hx-confirm="…"` on destructive
  bulk-action bar delete buttons. The dialog gives more space for the
  destructive-action copy + a more prominent loading state than the
  browser's default confirm prompt.
Pros: validates the primitives, adds UX polish to existing features.
Cons: each adoption is its own cycle's work; may surface design
questions (does the dropdown's 3-branch item shape actually fit the
list actions?).

### Option C (deletion): remove as dead code
Delete both templates, delete the UX-014 + `alpine-dropdown.md`
contracts, delete the regression tests, delete the `dzConfirm` Alpine
component from `dz-alpine.js`, delete the harness wiring in
`test-event-widgets.html`. Also remove the PR #600 era references from
docs that mention these as "available" primitives.
Pros: lowest maintenance burden. Cons: throws away work; future
adopters would need to rebuild from scratch; harder to reverse if
someone later wants them back.

## Blast radius

**If Option A**: zero behavioural change; comment additions only.
**If Option B (adopt dropdown in `list.html`)**: touches 1 region
template + affects all 5 example apps' list views. Visual change — the
3-button actions row becomes a kebab menu. Needs design sign-off.
**If Option B (adopt confirm-dialog for bulk-delete)**: touches
`bulk_actions.html` fragment + the `_user_can_mutate` delete flows.
Visual change — replaces browser confirm() with framework dialog.
Needs a11y review (focus trap, keyboard dismissal).
**If Option C**: deletes ~100 lines of template + ~40 lines of Alpine
JS + a contract file + regression tests. No user-visible change in
production (nothing was rendering these anyway). Devs who rely on
`$dispatch('dz-confirm', …)` in custom code would see silent no-ops
become errors.

## Open questions

1. **Is there a reason these were kept dormant?** The PR #600 commit
   message would clarify; if the primitives were explicitly deferred
   pending a future feature, Option C might be premature. If they
   were "write it and forget it," Option C is safe.
2. **`hx-confirm` vs. `confirm_dialog` design decision** — are there
   outstanding UX complaints about the browser's default confirm
   prompt? If yes, Option B (adopt confirm-dialog) has a product case.
   If no, Option A or C is more appropriate.
3. **Dropdown vs. context-menu vs. popover overlap** — the framework
   has several menu-like primitives (dropdown, context_menu, popover,
   alpine/dropdown). Why? Is one the "canonical" menu and the others
   legacy? A `helper_audit`-style cycle could disambiguate.
4. **Automated lint for orphans** — should the framework add a CI
   check that flags templates with zero production `{% include %}`
   consumers? Could live in `tests/unit/test_template_orphan_scan.py`
   following the cycle 284 lint-rule pattern. Would prevent future
   dormant primitives from accumulating silently.
5. **How many other PR #600 primitives are dormant?** Cycle 287's
   targeted scan only checked `components/alpine/*.html`. A broader
   sweep across `src/dazzle_ui/runtime/static/js/dz-alpine.js` could
   find Alpine data components with zero `x-data="…"` consumers — the
   same class of dead-interface that `dzConfirm` exemplifies.
6. **Cost of keeping vs. deleting** — keeping dormant primitives
   costs: test execution time (15+15 dormant tests = minor), reading
   burden on future devs (non-zero), governance overhead (contracts
   to maintain). Deleting costs: one-time destruction of work,
   potential need to recreate. Mostly a judgment call.

## Recommendation

**No unilateral action this cycle.** The decision between A/B/C is a
product-direction call, not a framework-hygiene call. Flagging for
user input:

- If the user wants to *preserve optionality*: Option A (annotation only).
- If the user wants to *actually use these primitives*: Option B
  (pick one or both, spec the first adopter, spawn a cycle per adoption).
- If the user wants to *shed weight*: Option C (deletion sweep).

Cycle 286 flagged the meta-question for dropdown with a 3-6 cycle
wait. Cycle 287 extends the question to `confirm_dialog`. Next user
message mentioning these primitives should nudge toward a decision.

## Status as of cycle 329 (2026-04-20)

**Re-verified after ~40 cycles of dormancy.** Still zero production
consumers across all 4 primitives:

```
components/alpine/confirm_dialog.html → 0 consumers
components/alpine/dropdown.html       → 0 consumers
components/modal.html                  → 0 consumers
components/island.html                 → 0 consumers
```

Cycles 286 + 287 flagged the decision as "awaiting user input." The
no-decision state has persisted across:
- PR #600 itself (cycles 286, 287 original discovery)
- Cycle 302's orphan_lint scanner (surfaced all 4 automatically)
- Cycle 304's scanner hardening (added dropdown after false negative)
- Cycle 322's allowlist audit (11/11 entries VALID — including these 4)
- Cycle 328's Python-module orphan rule-out (scope-setting for future)

**Policy stance (cycle 329, re-affirmed):**

**Option A (accept + document)** — the current default. Keep the
dormant primitives, keep their ux-architect contracts, keep the
orphan_lint allowlist entries citing PR #600 + cycle 286/287. No
action. Re-evaluate at v1.0 (when API-stability commitments tighten
the cost of deletion vs. preservation).

**Why the re-affirmation is worth noting:**
- The automatic lint (cycle 302) has turned passive documentation
  into active accountability. Each test run surfaces the allowlist;
  each cycle reads the reason. The primitives are no longer
  "forgotten code" — they're explicitly tracked-dormant.
- The ux-architect contracts for each primitive serve as
  documentation/intent even without adoption. Deletion would lose
  that intent capture.
- Zero user-facing impact. Zero ongoing maintenance cost beyond the
  allowlist entry (~1 line per primitive).

**When to revisit:**
- User explicitly asks about adopting, deleting, or repurposing any
  of the 4 primitives
- v1.0 API-stability milestone
- An example app's DSL introduces a component whose functionality
  matches one of the primitives (would trigger an "adopt instead of
  reinvent" judgement)

**"Dormant primitives review" candidate — removed from next-cycle queue**
in favor of Option A as the durable answer. The candidate will return
naturally if any of the re-visit triggers above fire.
