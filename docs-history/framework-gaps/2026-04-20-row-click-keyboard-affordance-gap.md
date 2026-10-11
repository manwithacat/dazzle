# Row-Click Keyboard Affordance Gap Across Workspace Regions

!!! info "📜 Historical snapshot — not current docs"
    Captured **2026-04-20** during Dazzle's autonomous-improvement cycles. It records the
    framework as it was then and the gap being worked at the time; **it may not
    describe current behaviour.** Start from the [documentation home](../../index.md),
    or see [Project Evolution](../../architecture/evolution.md) for how these fit together.


**Date**: 2026-04-20 (cycle 281)
**Class**: Framework-level accessibility gap
**Status**: Open for implementation

## Problem statement

Four workspace regions render clickable `<div>` or `<tr>` row bodies that fire HTMX drill-downs into the detail drawer. None of them expose the affordance to keyboard-only users:

| Region | Click target | Keyboard focusable? | Screen reader hint? |
|--------|--------------|---------------------|---------------------|
| `grid-region` (UX-066) | `<div class="dz-grid-cell">` | No | None |
| `timeline-region` (UX-067) | `<div class="dz-timeline-content">` | No | None |
| `queue-region` (UX-068) | `<div class="flex-1 min-w-0 cursor-pointer">` | No | None |
| `list-region` (UX-069) | `<tr class="dz-list-row">` | No | None |

Mouse users can click the row and see the detail drawer open via HTMX. Keyboard users cannot reach the row's drill-down at all — the Tab sequence walks through filter `<select>`s, sortable column anchors, and ref-cell anchors inside the row, but never lands on the row container itself.

This excludes:
- Users with motor impairments who navigate by keyboard
- Power users who prefer keyboard-only navigation
- Screen reader users (who also can't hear "clickable" hint since there's no `role="button"`)

For a dashboard that relies on row-click to preview records, this is a meaningful accessibility failure.

## Evidence

- **Cycle 275** (UX-066 grid-region contract) — v2 Q1: "Cells are `<div>` not `<button>` or `<a>` — keyboard users can't reach the drill-down via Tab."
- **Cycle 276** (UX-067 timeline-region contract) — v2 Q3: "Content pad is `<div>` not `<button>` — keyboard users can't reach HTMX drill-down."
- **Cycle 277** (UX-068 queue-region contract) — v2 Q2: button-group `<div>` has stopPropagation but row body itself has no keyboard affordance. (Indirect.)
- **Cycle 278** (UX-069 list-region contract) — v2 Q2: "Row click is on `<tr>` with no `role='button'` / `tabindex`. Keyboard users can't reach row-level drill-down."

Four independent contract cycles surfaced the same gap. Cross-cycle reinforcement >3 → framework-level theme.

## Root cause hypothesis

Each region's row template was written before accessibility was a priority, and the "cursor-pointer + hx-get on row `<div>`" pattern got copied forward as new regions were added. The pattern is valid HTMX but invalid a11y — HTMX doesn't require `<button>` or `<a>` semantics, so templates didn't adopt them.

Not a helper-audit class defect (Heuristic 2) — there's no shared helper that does the right thing but isn't called. It's a pattern-copy class defect — each region implements the same wrong pattern independently.

Nearest existing reference: `data-table` (UX-002) has similar row-click behaviour and also the same gap. Suggests the pattern predates the workspace-region family.

## Fix sketch

Three viable approaches, in increasing order of invasiveness:

### Option A (minimal): add `role`, `tabindex`, keyboard handlers

For each row container `<div>` / `<tr>` with `hx-get`:
```html
<div class="..."
     role="button"
     tabindex="0"
     @keydown.enter.prevent="$el.click()"
     @keydown.space.prevent="$el.click()"
     hx-get="..." ...>
```

- `role="button"` tells screen readers "this is a button"
- `tabindex="0"` includes in the natural Tab sequence
- The Alpine `@keydown` handlers translate Enter/Space keypresses into clicks

**Pros**: minimal change, preserves all existing HTMX wiring, no visual difference.
**Cons**: introduces Alpine dependency into previously-pure-HTMX regions (grid, timeline, list). Violates the "no Alpine for static-rendering regions" stance in each contract. Also: `$el.click()` is slightly hacky — some browsers fire the HTMX click handler correctly, others might race.

### Option B (semantic): convert row body to `<a href>` with `hx-boost`

Instead of `<div hx-get="...">`, use `<a href="/app/item/{id}" hx-boost="true">`:
- `<a>` is natively focusable and keyboard-activatable (Enter fires click).
- `hx-boost="true"` makes HTMX intercept the click, turning the naive navigation into an HTMX swap into the detail drawer.
- Falls back to native navigation when JS disabled.

**Pros**: semantically correct, no Alpine, works with JS disabled.
**Cons**: requires changing the DOM structure (wrapping row content in `<a>`). For list-region, `<a>` can't be a direct child of `<tr>`; would need `<tr><td><a>...</a></td></tr>` reshape. Destroys current single-row-click semantics.

### Option C (shared primitive): `dz-clickable-row` Alpine component

Extract a reusable `dz-clickable-row` primitive:

```js
Alpine.data('dzClickableRow', () => ({
  init() {
    this.$el.setAttribute('role', 'button');
    this.$el.setAttribute('tabindex', '0');
    this.$el.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        this.$el.click();
      }
    });
  }
}));
```

Each region uses: `<div x-data="dzClickableRow" hx-get="...">`. The Alpine component handles the a11y wiring; HTMX handles the actual swap.

**Pros**: shared logic, easy to add cross-cutting a11y improvements later (focus-visible styling, `aria-live` announcements, etc).
**Cons**: introduces Alpine dependency into static-rendering regions (same as Option A). Alpine init is async (fires on `Alpine:init`), so the `role`/`tabindex` attrs aren't present in the server-rendered HTML — screen readers on first paint see a plain `<div>` until Alpine hydrates. For SSR-first apps this is a regression.

### Recommendation

**Option B (semantic) with exceptions for `<tr>` contexts**:
- Grid, timeline, queue content-pad → wrap in `<a href hx-boost>`.
- List → keep the `<tr hx-get>` structure but add `role="button" tabindex="0"` at the template level (no Alpine needed) + an explicit keyboard event handler... actually the server-rendered `role`/`tabindex` + the native HTMX click handler should work. Enter on a focused element with `role="button"` fires `click` in modern browsers per ARIA spec. Verify via Heuristic 1.

This mixes approaches per region (A for list, B for everything else) based on what the DOM structure allows. It's pragmatic and preserves pure-HTMX stance for static regions.

**Reference implementation**: check `components/detail-view.html` (UX-029) — the detail-view page has back/action buttons that are legitimate `<a href>` + `hx-boost`. That pattern is the precedent.

## Blast radius

- **Affected regions**: grid (UX-066), timeline (UX-067), queue (UX-068), list (UX-069). ALSO: `data-table` (UX-002) same gap, worth including.
- **Affected apps**: all 5 example apps. Default-mode rendering uses list-region, so blast radius is full-fleet.
- **Regression tests needed**: keyboard-activation tests via Playwright (cycle 217-227 pattern). HTTP-layer tests can verify `role="button" tabindex="0"` present; behavioural tests need browser automation.
- **Visual regression risk**: `<a>` wrapping may change the hover/focus styling — need to verify current `hover:bg-muted/0.4` doesn't break. `<tr>` role+tabindex should have zero visual impact.

## Open questions

1. **Heuristic 1 (real-thing check)**: does `<tr role="button" tabindex="0">` with `hx-get` actually respond to Enter keypress? ARIA spec says yes, but browser implementations vary. Before writing the fix, manually verify in a live browser. A "manual testing" cycle might precede the code cycle.

2. **Focus-visible styling**: currently rows use `hover:bg-muted/0.4`. Keyboard-focused rows need `focus-visible:bg-muted/0.6` or similar to signal focus. Framework should add this to the shared pattern.

3. **Tab order reachability**: adding `tabindex="0"` to every row in a large list (100 rows) floods the Tab sequence. Is that a feature or bug? Keyboard users may prefer a structural skip (Tab → filter bar → table → row region → out); with 100 tabindexed rows, Tab becomes unusable. Consider `tabindex="-1"` on rows + a wrapper with `tabindex="0"` that uses roving-tabindex pattern (arrow keys between rows).

4. **Screen-reader announcement**: `role="button"` gets announced as "button". But the row is semantically a table row or a card, not a button. Alternative: `role="link"` for drill-down rows, since they do navigate somewhere. Or `role="row"` on `<tr>` (native) + `aria-rowindex` for position tracking. Detail worth settling before shipping.

5. **Data-table (UX-002) inclusion**: fixing 4 workspace regions but leaving the similar pattern in data-table produces another inconsistency. Fix should probably span 5 components, not 4.

6. **Detail drawer focus management**: when HTMX drops the drill-down response into `#dz-detail-drawer-content`, focus doesn't automatically move to the drawer's close button. Keyboard users don't know "something opened". A future cycle could add `hx-trigger="load" @hx-swap:afterSettle="$refs.drawerClose.focus()"` or similar focus-move Alpine handler. Out of scope for the initial row-click fix.

## Implementation sketch

**Order of operations** (if we go with Option B+A hybrid):

1. Write a short manual-testing doc confirming `<tr role="button" tabindex="0">` works with Enter keypress across Firefox/Chrome/Safari. (Heuristic 1, first step.)
2. For grid, timeline, queue: wrap the HTMX-triggering `<div>` in `<a href="{action_url | replace('{id}', ...)}" hx-boost="true">`. Preserve existing class chain. Drop `hx-get` (boost handles it).
3. For list: `<tr class="dz-list-row" role="button" tabindex="0" ...>` — minimal template edit.
4. Also apply to data-table's list rows (UX-002).
5. Add `focus-visible:` variants to row hover styles so keyboard focus is distinct from mouse hover.
6. Regression tests: HTTP-layer assertions for `role="button"` + `tabindex="0"` presence per region. Browser-layer tests deferred (they'd need Playwright).
7. Per Heuristic 3: verify on all 5 example apps. Tab through a dashboard using each region + confirm drill-down fires on Enter.
8. Update the 5 affected contracts (grid/timeline/queue/list/data-table) to document the new keyboard affordance + mark the previous v2 open questions RESOLVED.

**Estimated scope**: one `/ux-cycle` session (90-120 min) plus manual a11y verification. Bigger than the attention-tier extraction because it touches 5 region templates + requires browser-level verification.

**Not in scope**: detail-drawer focus management (open question #6). Data-table structural rework if `<a>` wrapping doesn't fit its column layout.
