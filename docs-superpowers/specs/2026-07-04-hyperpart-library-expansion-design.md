# Hyperpart library expansion — design

**Date:** 2026-07-04
**Status:** shortlist + batch-1 approved (conversation)
**Scope:** `packages/hatchi-maxchi/` (registry, gallery build, controllers, CSS, tests).
**Follows:** `2026-07-04-hyperpart-composition-spike-design.md` (the composition
spike de-risked the seam; this expands the primitive + composite library on top
of the template it established).

## Why

The composition spike proved the Hyperpart model composes (toolbar = inline,
master-detail = exchange) and set the template every future component follows.
This is the follow-on line of work: grow the library toward shadcn/Radix
coverage, but **translate each candidate into HM's hypermedia idiom rather than
transplant the React shape**. Deciding the native form per component IS the work.

## The idiom taxonomy (order of preference)

1. **Native element / CSS-only** (`<dialog>`, `<details>`, input types) — no JS.
2. **Declarative-over-htmx** — an Exchange: a slot that `hx-get`s a child fragment.
3. **Instance-isolated vanilla controller** — only where the platform lacks it;
   follow `dz-master-detail.js` (delegated from document, every query scoped to
   `evt.target.closest(root)` so N instances coexist; never `document.querySelector`).

Compose from existing primitives where possible (`Hyperpart.composes = (...)`).

## Non-negotiables (all gated in CI + the standalone repo after sync)

- stdlib-only in the HM package; HM never imports `dazzle.*`.
- Grammar: `class="dz-x"` + `data-dz-variant`/`data-dz-tone`/`data-dz-size`; the
  naming-grammar gate forbids invented data-attrs (only `data-dz-*` / `data-hm-*`).
- Author CSS `dz-`-prefixed; `build_css("")` strips for the gallery, keeps for Dazzle.
- A11y is a hard gate (WCAG axe + Nu/W3C validity, standalone repo only). Known
  traps: `role=combobox`/`aria-expanded` INVALID on `<input>`; `role=listbox` needs
  `option` DIRECT children; static content is not a live region (no gratuitous
  `role=status`); never colour-alone. Pre-check the built gallery with
  `html5validator` locally before pushing.
- Interactive Hyperparts declare an Exchange (endpoint + states), a controller with
  a `HYPERPART:` marker, and a mock; register controllers in `build.py JS_SOURCES`
  and mock responses in `build_site.py`.
- Snippets auto pretty-print (`site/pretty.py`) — verify the fidelity gate stays
  green; add `hm-demo-row` for multi-variant showcases.
- Adversarial review (fresh reviewer subagent) on every interactive/controller-
  bearing component before shipping.

## Full shortlist (curated)

### Tier 1 — native / CSS-only
- **Accordion** — stack of native `<details>`; `name=` attr = single-open exclusivity, zero JS.
- **Skeleton** — CSS shimmer blocks; `prefers-reduced-motion`; wired to `.htmx-request` (TASTE-9).
- **Field** — `dz-field` = label + control + help + error (`data-dz-invalid`); composite over form primitives.
- **Select** — native styled `<select>` (honest, not a custom listbox).
- **Slider** — native styled `<input type=range>`; optional value bubble reuses `dzRangeTooltip`.
- **Separator** — `<hr>` + vertical `role=separator`.
- **Stepper (visual)** — CSS ordered list, done/current/upcoming, `aria-current="step"`; composes icon/badge.

### Tier 2 — declarative-over-htmx (Exchange)
- **Tabs** — tab `<a hx-get>` → shared panel slot (lazy panels); instance-isolated marker
  controller. **A11y: honest link-strip first** (no ARIA tab roles / roving tabindex —
  matches HM's "disclosure, not ARIA menu" candor); full ARIA-tabs keyboard is a later upgrade.
- **Pagination** — page `<a hx-get>` swaps the list region; composes button/icon.
- **Data-table sort/filter** — header `hx-get` re-fetches `tbody`. Heavy; **deferred**.

### Tier 3 — instance-isolated controller
- **Dialog / Modal** — native `<dialog>`; `data-dz-dialog-open="id"` → `showModal()`; close is
  native (`<form method="dialog">` + `closedby="any"` + Esc/backdrop). Composes button/card.
- **Drawer / Sheet** — native `<dialog>` edge-anchored (`data-dz-side`); reuses `dz-dialog.js`.
- **Toast** — `#dz-toasts` live region (legit `aria-live=polite`) + auto-dismiss controller.
- **Combobox** — input + filtered listbox via `hx-get` (command palette IS this). Heavy;
  **deferred**; model on `command`, respect the input-ARIA trap.

### Curated out
- **Collapsible** — redundant with Accordion (single `<details>`).
- **Stat/metric card** — fold delta-tone variants into existing `card`; don't add.
- **Hover-card** — low marginal value over Tooltip; same "not accessible" caveat.
- **Switch / checkbox / radio-group** — already shipped (`controls`, `toggle-group`).

## Batch 1 (approved — build first)

Chosen to span all three idiom tiers + composition, re-validating the whole template
in one batch while only Dialog is non-trivial.

1. **Dialog** (tier 3) — native `<dialog>` + minimal instance-isolated opener
   (`dz-dialog.js`: delegated `click` on `[data-dz-dialog-open]`, `showModal()` on the
   `<dialog id>` it names; close native). New: `dialog.css`, `dz-dialog.js` (→ JS_SOURCES),
   `composes=("button","card")`. No server exchange (client overlay). Adversarial review.
2. **Accordion** (tier 1) — `<details name="…">` group, exclusive-open, zero JS.
   New: `accordion.css`.
3. **Skeleton** (tier 1) — CSS shimmer; `prefers-reduced-motion`; group Feedback.
   New: `skeleton.css`.
4. **Field** (tier 1 composite) — `dz-field` label/help/error triad; `composes=("controls",)`.
   New: `form.css` extension. A third composition example beyond toolbar/master-detail.

## Acceptance (batch 1)

- Each renders live + as a pretty-printed snippet; dependency chips + "Composed of"
  (Field, Dialog) resolve.
- `test_contract` (Exchange↔hx-* match, composes ids real), naming-grammar, WCAG axe,
  Nu/W3C validity, visual, pretty-fidelity, `test_hyperpart_cohesion` (Dialog marker +
  manifest) all green — monorepo + standalone after sync.
- Dialog: opens on trigger, closes via Esc/backdrop/close-button, focus lands in the
  dialog; two dialogs on one page open independently (instance isolation).
- Accordion: opening one closes its siblings (native `name=`), keyboard-operable.

## Non-goals

- No runtime slot/include engine (`composes` stays declarative).
- No ARIA-tabs keyboard widget in batch 1 (Tabs is batch 2, link-strip form).
- Combobox + data-table deferred (high complexity / a11y risk).
