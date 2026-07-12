# Playbook: pick a surface

**Goal:** Map a user job to the correct L1 Hyperpart (or host-local primitive).
**Open when:** “I need a dropdown / picker / chips / typeahead / filter / top nav / actions menu.”
**Do not open:** gallery HTML first; do not invent a new part before this matrix.

## Steps

1. Name the **job** in plain language (one sentence).
2. Name **lifetime**: durable form field vs ephemeral editor vs page region.
3. Name **exchange**: form POST, hx-get fragment, single-field PUT, none (pure chrome).
4. Match a row below. Prefer the **Use** column.
5. Open `site/agents/<id>.md` and implement that spine only.

## Pick matrix (L0 → L1)

### Selection / entry

| Job | Recipe slug | Lifetime | Exchange | **Use** | **Do not use** |
|-----|-------------|----------|----------|---------|----------------|
| Single-select, form, closed set | `single-select-form` | Field | Form POST | `combobox` | search-select, tags |
| Single-select, form, add if missing | `single-select-form` | Field | Form POST + **catalogue upsert** | `combobox` + `data-dz-allow-create` | new “create-dropdown” part |
| Multi free-form labels | `multi-label-form` | Field | Form POST (comma-joined) | `tags` | combobox |
| Remote FK / typeahead | `remote-fk-typeahead` | Field | Search + select exchanges | `search-select` | combobox per entity |
| Dense in-cell enum, morph, PUT | `single-select-cell` | Ephemeral cell | Single-field PUT | grid-edit `kind=select` (on `grid`) | combobox (refused today) |
| Toolbar filter (closed options) | _(host-local)_ | Control on host | Host list exchange (query param) | native/filter select on host | invent fourth picker |
| Confirm irreversible action | `confirm-affordance` | Affordance | Existing `hx-*` of the action | `confirm` (hx-confirm) | custom modal stack |
| Money as major display | `money-minor-units` | Field | Form posts **minor integer** | `money` | float string as source of truth |

Recipe slugs are seeded on Hyperparts via `_RECIPE_SEED` in `site/registry.py`
and appear on agent packs + `CONSUMER_MAP.md` › By recipe.

### Structure / chrome

| Job | **Use** | Notes |
|-----|---------|--------|
| Label + help + error | `field` | aria-invalid / describedby |
| Page motif of existing parts | **Blueprint** | Not a new Hyperpart |
| Vertical rhythm | `stack` | Layout primitive |
| Wrapping actions | `cluster` / `toolbar` | Compose real children in HTML |

### Menus / panels / chrome strips

Horizontal panels and “dropdowns” are **not one Hyperpart**. Choose by **job**
(action vs navigate vs app chrome), not by “opens a panel with a chevron.”
shadcn names are a prior; lifetime + exchange decide. Same shape ≠ same L1
(`stems/three-layers.md`).

| Job (one sentence) | Lifetime | Exchange | **Use** | **Do not use** |
|--------------------|----------|----------|---------|----------------|
| Local **actions** from one control (“Edit / Duplicate / Delete”) | Ephemeral affordance on a host | Item owns `hx-*` / dialog; menu itself often none | **`menu`** | menubar, navigation-menu, invent “dropdown-menu” |
| Free-floating **content** (filters, preview, form fragment) | Ephemeral | Optional lazy hx-get into panel | **`popover`** | menu (action list), dialog (modal) |
| **App chrome** File / Edit / View command strip | Durable session chrome | Usually none; items may navigate | **`menubar`** | navigation-menu (site IA), single `menu` for the whole strip |
| **Product / site go-to** top nav (links + optional mega panels) | Durable IA | Navigation (`href` / boost); `aria-current=page` | **`navigation-menu`** | menubar (app commands), app-shell **sidebar** (left rail) |
| Left-rail **app** navigation | Durable shell | Host routes / boost | **`app-shell`** (sidebar) | navigation-menu (top product nav) |
| Confirm irreversible action from a menu item | Affordance on the action | Existing `hx-*` of the item | **`confirm`** on the item | custom modal stack |

**Compressed pick:**

```
Need a list of actions from one button?     → menu
Need free content under a trigger?          → popover
Need File/Edit/View app chrome?             → menubar
Need top product/site nav (go somewhere)?   → navigation-menu
Need left rail app IA?                      → app-shell
```

**Composition (not merge):** `toolbar` embeds `menu`; menubar may compose denser
item lists with menu patterns; navigation-menu sits with app-shell as peer chrome
(top vs side). Do **not** collapse into one part with `data-mode=bar|nav|dropdown`.

**Dismiss model** (stem `overlay-light-dismiss`): two axes — **spatial**
(Esc / outside) vs **temporal** (opt-in `data-dz-dismiss-ms`). Transient overlays
(`menu`, `popover`, menubar/nav panels) default to **spatial only**. Timeout is
per-instance for glance previews, not for forms. Configure:
`data-dz-dismiss="esc outside|none"` + optional `data-dz-dismiss-ms`. In-flow
structure (`accordion`, `tree`): no light-dismiss. Touch: outside, not Esc.
Disclosure chevron ≠ dismiss path.

Agent packs: `site/agents/menu.md`, `menubar.md`, `navigation-menu.md`.

If no row fits: open `invent-safely.md`—do **not** stretch an L1 with mode flags that change lifetime or commit path.

## Stop conditions

- You chose by **screenshot similarity** alone → restart from lifetime + exchange.
- You planned `data-density=cell` on combobox → read `docs/decisions/0002-three-layers.md`.
- Grid in-cell combobox → `CONSUMER_MAP` refuse edge + `docs/spikes/combobox-in-grid-cell.md`.
- You picked menubar vs navigation-menu by “horizontal strip” alone → re-ask: **app commands** or **go somewhere**?

## Next

- Implement: `site/agents/<id>.md`
- Host work: `compose-or-refuse.md`
