# Spike: combobox inside grid `kind=select` cells

**Status:** open — not scheduled. Current contract is **non-composition**.
**Registry lock:** `grid.does_not_compose → combobox` in `site/registry.py`
**Consumer map:** `CONSUMER_MAP.md` › Explicit non-compositions
**Implementation today:** `controllers/dz-grid-edit.js` builds
`<select class="dz-inline-edit-select">` — never `data-dz-combobox`.

## Why this spike exists

Agents and humans see “select-ish UX” in two places:

1. **combobox** — progressive enhancement over a form `<select data-dz-combobox>`
2. **grid-edit `kind=select`** — ephemeral in-cell editor for a single-field PUT

They look related. They are **not** the same Hyperpart. Without an explicit
refusal + design gate, the next refactor of either side will “dogfood”
combobox into the grid and break density, morph, or commit semantics.

## Current decisions (locked)

| Concern | Grid `kind=select` today | Combobox |
|---------|--------------------------|----------|
| Lifetime | Ephemeral editor; display span is source of truth | Persistent form control |
| Commit | `change` → raw `PUT {edit-url}/{rowId}` JSON single field | Enclosing form POST (or host action) |
| Morph | `root._dzEdit` + before/after-swap reopen | N/A (page field) |
| Density | One tight `<select>` in a table cell | Overlay input + listbox (~form field height) |
| Catalogue | Closed options from `data-dz-edit-options` JSON | Fixed list **or** `data-dz-allow-create` growing list |
| A11y | Editor `aria-label` on temporary control | `role=combobox` + listbox |

## What would have to be true to flip composition

Flipping means: remove `does_not_compose` for combobox on grid, add a real
composition path (extension or documented mount), and pass CI locks.

### Must-solve checklist

1. **Morph survival** — open combobox state must reopen after `innerMorph` of
   tbody the way `_dzEdit` does today (or combobox must not hold exclusive
   focus state across refresh).
2. **Commit path** — pick remains single-field PUT on change; combobox must not
   require a full form submit. Map `change` on the native select (or a
   documented combobox event) to the existing PUT body shape.
3. **Density** — listbox and field height must fit a data row without blowing
   row height (see form-input / combobox metric alignment). Overflow strategy
   for the listbox inside a scrollable grid region.
4. **Closed enum default** — in-cell select is almost always a closed set.
   Growing-list (`allow-create`) in a cell is a **separate** product decision
   (catalogue upsert mid-grid). Default composition path must be fixed-list only.
5. **Dual-lock** — when mounted, in-cell DOM must satisfy `contracts/combobox.py`
   *or* a new `grid_edit` sub-contract that documents the subset. No “looks like
   combobox but different attrs.”
6. **Behaviour tests** — atomic scenarios: open select cell, pick, PUT fires,
   morph mid-edit, Escape cancel, Tab advance — all still green with combobox.
7. **Consumer map** — regenerate after flipping; refuse edge becomes embed edge.

### Explicit non-goals for v1 composition

- Multi-create chips in a cell (that is **tags**, not combobox)
- Remote FK typeahead in a cell (that is **search-select**)
- Client-side patch of display badges after commit (grid still refreshes via
  `dz-grid:refresh`)

## Flip procedure (when product prioritises this)

1. Implement a prototype branch against the checklist above.
2. Replace `NonComposition` with either:
   - `composes` / extension note that grid-edit mounts combobox, **or**
   - a documented optional `data-dz-edit-widget=combobox` with dual-lock.
3. Soften/remove `require_substrings` / `forbid_substrings` locks for the old
   bare select path (or keep bare select as the default and combobox as opt-in).
4. Regenerate `CONSUMER_MAP.md`, update `agents/grid.md` guidance, ship.

Until then: **do not** mount `data-dz-combobox` inside a grid cell and expect
grid-edit to drive it. CI will fail if controller sources gain combobox markers
while the refusal remains.

## Related files

- `contracts/grid_edit.py` — `kind=select` + `data-dz-edit-options`
- `contracts/combobox.py` — form combobox dual-lock
- `controllers/dz-grid-edit.js` — `buildEditor` select branch
- `controllers/dz-combobox.js` — progressive enhancement
- `site/registry.py` — `grid.does_not_compose`
- `AGENTS.md` › Composition
