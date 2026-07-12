# Stem: selection strip honest

## Claim

A **selection strip** (tabs, segment toggles, master-detail list, sidebar
nav current) is either:

1. **In-page state** — which panel/item is current without a new URL, or
2. **Navigation** — a real destination (new page / route / fragment the
   server owns).

**Choose the platform element from that intent**, then style. Do not fake
ARIA roles you will not fully implement.

| Intent | Element | Selection state | Examples |
|--------|---------|-----------------|----------|
| In-page state | `<button type="button">` | `aria-current="true"` (or `aria-pressed`) | **tabs** (`__tab`), toggle, master-detail list buttons |
| Navigation | `<a href="…">` | `aria-current="page"` | sidebar nav, pagination page links, breadcrumb current |
| Exclusive form choice | native radio / checkbox | `:checked` | **toggle-group** |

**Do not** ship `role="tablist"` / `role="tab"` without roving tabindex +
arrow keys (same honesty as menu: disclosure, not fake ARIA menu).

## Taxonomy (tabs)

| Name | Class | Role |
|------|-------|------|
| **Tab** | `.dz-tabs__tab` | Clickable strip label — **button** |
| **Tab list** | `.dz-tabs__list` | Horizontal strip of tabs |
| **Panel** | `.dz-tabs__panel` | Content for the current tab |

Human “tab header / title” ≈ **tab**. Not a heading (`h2`); not a link
unless the product routes each panel.

## Why buttons for tabs (rational)

1. **Activate, don’t navigate** — switching Overview → Activity is local
   state (show/hide + optional htmx load), not “go to another URL.”
2. **Keyboard** — Enter/Space activate natively; Tab moves between tabs
   without inventing roving-tabindex (honest progressive model).
3. **No dead ARIA** — full WAI-ARIA tabs pattern is a contract; HM refuses
   the half-built version.
4. **Same family as other in-page choosers** — master-detail items and
   toggles also use button/`aria-current` when not navigating.

Use **links** when the strip *is* routing (sidebar, pagination). Agents:
if the panel swap would still work offline with only DOM, prefer buttons.

## Indicator geometry (presentation contract)

When the current mark is a **bottom edge** (tab underline, flush rail):

- The mark must be a **straight segment**, not a rounded-rectangle border
  following `border-radius`.
- Root cause of curved underlines: `base.css` `button { border-radius:
  var(--radius-sm) }` inherited by tab buttons; the active
  `border-block-end` **follows those radii** at the corners.
- Fix: set **`border-radius: 0`** on strip tabs (and keep the indicator on
  the border or a square `::after` bar). Do not “fix” by thickening the
  curve.

## Agent recognition of incongruous curvature

| Signal | Machine / reconstructable |
|--------|---------------------------|
| Active tab has non-zero `border-*-radius` **and** a coloured bottom border | **FAIL** presentation — straight indicator required |
| Human: “blue line tips curl up” | Same bug: radius × bottom border |
| Vision models | Optional advisory; **do not** rely on them — CSS geometry is the gate |

Pin: `test_tabs_active_indicator_is_square` (computed radius 0 on active tab).

## Not this

- `<a href="#">` tabs that only toggle panels (link affordance + inert hash).
- `role="tablist"` without arrow-key contract.
- Relying on default `button` chrome (radius, filled hover) for strip labels —
  always reset for selection-strip presentation.
- Rounding the active underline “to match brand radius” — radius is for
  surfaces, not flush rail indicators.

## Expressions

- `components/tabs.css`, `controllers/dz-tabs.js`, `contracts/tabs.py`
- Related: `toggle-group` (radios), `master-detail` items, `app-shell` nav links
- Gallery: Hyperpart **tabs** agent pack Guidance
