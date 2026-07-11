# Playbook: pick a surface

**Goal:** Map a user job to the correct L1 Hyperpart (or host-local primitive).
**Open when:** “I need a dropdown / picker / chips / typeahead / filter.”
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

If no row fits: open `invent-safely.md`—do **not** stretch an L1 with mode flags that change lifetime or commit path.

## Stop conditions

- You chose by **screenshot similarity** alone → restart from lifetime + exchange.
- You planned `data-density=cell` on combobox → read `docs/decisions/0002-three-layers.md`.
- Grid in-cell combobox → `CONSUMER_MAP` refuse edge + `docs/spikes/combobox-in-grid-cell.md`.

## Next

- Implement: `site/agents/<id>.md`
- Host work: `compose-or-refuse.md`
