# Data table (`grid`)

A server-rendered data table on a real <table>, all HTML over the wire: search, sortable headers, filters, row selection (one page or every matching row), bulk actions, pagination, and deep-linkable URL-synced state. Optional extensions add column visibility, column resize, and inline cell editing. See How to use it and the DOM contract on this page for wiring.

> **Layer:** L2 host · **Recipe:** `list-region-host` — server-driven list / data table host · **Refuses:** `combobox`
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="hm-stack">
  <div class="table" data-grid data-grid-url data-bulk-count="0" data-grid-page="1" data-grid-edit-url="/mock/grid">
    <div class="filter-bar">
      <div class="filter-cell">
        <label class="filter-label" for="hm-grid-search">Search</label>
        <input class="filter-input" id="hm-grid-search" type="search" data-grid-search name="q" placeholder="Name or plan…">
      </div>
      <div class="filter-cell">
        <label class="filter-label" for="hm-grid-filter-plan">Plan</label>
        <select class="filter-select" id="hm-grid-filter-plan" data-grid-filter="plan">
          <option value="">Any plan</option>
          <option value="Free">Free</option>
          <option value="Pro">Pro</option>
          <option value="Team">Team</option>
          <option value="Enterprise">Enterprise</option>
        </select>
      </div>
      <!-- status is a filter-only field (no column): filters can narrow on any server field, not just displayed columns -->
      <div class="filter-cell">
        <label class="filter-label" for="hm-grid-filter-status">Status</label>
        <select class="filter-select" id="hm-grid-filter-status" data-grid-filter="status">
          <option value="">Any status</option>
          <option value="Active">Active</option>
          <option value="Trialing">Trialing</option>
          <option value="Churned">Churned</option>
        </select>
      </div>
      <div class="filter-cell">
        <label class="filter-label" for="hm-grid-page-size">Per page</label>
        <select class="filter-select" id="hm-grid-page-size" data-grid-page-size>
          <option value="2">2</option>
          <option value="4" selected>4</option>
          <option value="8">8</option>
        </select>
      </div>
      <details class="table-col-menu">
        <summary class="table-col-menu-trigger" aria-label="Toggle column visibility">Columns</summary>
        <div class="table-col-menu-panel">
          <label class="table-col-menu-item"><input type="checkbox" checked class="table-col-menu-checkbox" data-grid-col-toggle="first" aria-label="Show First name column"><span>First name</span></label>
          <label class="table-col-menu-item"><input type="checkbox" checked class="table-col-menu-checkbox" data-grid-col-toggle="last" aria-label="Show Last name column"><span>Last name</span></label>
          <label class="table-col-menu-item"><input type="checkbox" checked class="table-col-menu-checkbox" data-grid-col-toggle="plan" aria-label="Show Plan column"><span>Plan</span></label>
          <label class="table-col-menu-item"><input type="checkbox" checked class="table-col-menu-checkbox" data-grid-col-toggle="signed" aria-label="Show Signed up column"><span>Signed up</span></label>
          <button type="button" class="table-col-menu-reset" data-grid-cols-reset>Show all columns</button>
        </div>
      </details>
    </div>
    <div class="bulk-actions"><span aria-live="polite" aria-atomic="true"><span data-bulk-count-target>0</span> selected</span><button type="button" class="bulk-matching" data-grid-select-all-matching title="Select every row that matches the current search and filters (including other pages) — not only the rows on this page" aria-label="Select all results matching current search and filters">Select all <span data-grid-matching-total>…</span> results</button><button type="button" class="bulk-delete" data-grid-bulk-action="delete" data-grid-bulk-refresh hx-swap="none" hx-post="/mock/grid/bulk" hx-confirm="Delete the selected customers? This cannot be undone.">Delete</button><button type="button" class="bulk-clear" data-grid-clear>Clear</button></div>
    <div class="table-scroll">
      <div class="table-loading" aria-hidden="true"><span class="table-loading-spinner"><svg class="icon" aria-hidden="true"><use href="#i-loader-circle"/></svg></span></div>
      <div class="table-scroll-x">
        <table class="table-grid">
          <colgroup>
            <col class="table-col-select">
            <col data-col="first">
            <col data-col="last">
            <col data-col="plan">
            <col data-col="signed">
          </colgroup>
          <thead>
            <tr>
              <th class="table-th-select"><input type="checkbox" data-grid-select-all aria-label="Select all rows"></th>
              <th class="table-th" data-col="first" aria-sort="none"><button type="button" class="table-sort-button" data-grid-sort="first">First name<span class="table-sort-icon" aria-hidden="true"><svg class="icon" aria-hidden="true"><use href="#i-chevron-up"/></svg></span></button><span class="table-resize-handle" data-grid-resize="first" aria-hidden="true"></span></th>
              <th class="table-th" data-col="last" aria-sort="none"><button type="button" class="table-sort-button" data-grid-sort="last">Last name<span class="table-sort-icon" aria-hidden="true"><svg class="icon" aria-hidden="true"><use href="#i-chevron-up"/></svg></span></button><span class="table-resize-handle" data-grid-resize="last" aria-hidden="true"></span></th>
              <th class="table-th" data-col="plan" aria-sort="none"><button type="button" class="table-sort-button" data-grid-sort="plan">Plan<span class="table-sort-icon" aria-hidden="true"><svg class="icon" aria-hidden="true"><use href="#i-chevron-up"/></svg></span></button><span class="table-resize-handle" data-grid-resize="plan" aria-hidden="true"></span></th>
              <th class="table-th" data-col="signed" aria-sort="none"><button type="button" class="table-sort-button" data-grid-sort="signed">Signed up<span class="table-sort-icon" aria-hidden="true"><svg class="icon" aria-hidden="true"><use href="#i-chevron-up"/></svg></span></button><span class="table-resize-handle" data-grid-resize="signed" aria-hidden="true"></span></th>
            </tr>
          </thead>
          <tbody class="table-body" data-grid-body data-grid-src="/mock/grid/rows" hx-get="/mock/grid/rows" hx-trigger="load, grid:refresh" hx-swap="innerMorph">
            <tr class="tr-row" aria-hidden="true">
              <td class="tr-checkbox-cell"><span class="skeleton" data-shape="text"></span></td>
              <td class="tr-cell"><span class="skeleton" data-shape="text"></span></td>
              <td class="tr-cell"><span class="skeleton" data-shape="text"></span></td>
              <td class="tr-cell"><span class="skeleton" data-shape="text"></span></td>
              <td class="tr-cell"><span class="skeleton" data-shape="text"></span></td>
            </tr>
            <tr class="tr-row" aria-hidden="true">
              <td class="tr-checkbox-cell"><span class="skeleton" data-shape="text"></span></td>
              <td class="tr-cell"><span class="skeleton" data-shape="text"></span></td>
              <td class="tr-cell"><span class="skeleton" data-shape="text"></span></td>
              <td class="tr-cell"><span class="skeleton" data-shape="text"></span></td>
              <td class="tr-cell"><span class="skeleton" data-shape="text"></span></td>
            </tr>
            <tr class="tr-row" aria-hidden="true">
              <td class="tr-checkbox-cell"><span class="skeleton" data-shape="text"></span></td>
              <td class="tr-cell"><span class="skeleton" data-shape="text"></span></td>
              <td class="tr-cell"><span class="skeleton" data-shape="text"></span></td>
              <td class="tr-cell"><span class="skeleton" data-shape="text"></span></td>
              <td class="tr-cell"><span class="skeleton" data-shape="text"></span></td>
            </tr>
          </tbody>
        </table>
        <div class="table-empty">
          <span class="table-empty-icon"><svg class="icon" aria-hidden="true"><use href="#i-inbox"/></svg></span>
          <p class="table-empty-title">No customers found</p>
          <p class="table-empty-hint">Adjust the filters to widen your search.</p>
        </div>
      </div>
    </div>
    <span class="grid-announce" data-grid-announce aria-live="polite" aria-atomic="true"></span>
    <nav class="pagination" data-grid-pagination aria-label="Pagination"></nav>
  </div>
</div>
```

## Server exchange

When the client affordance finishes, htmx issues **this** request. Return the **response fragment** in the table (usually HTML, not JSON). Dazzle often implements these from the app model; a standalone HTMX4 app implements them explicitly.

> **Do not reimplement the gallery.** Flash toasts (e.g. confirm’s > “Deleted (demo).”), `/mock/*` paths, and other static-site > scaffolding are **demo-only** (`MOCK_HTMX` in `site/build_site.py`). > They are not Hyperpart surface and not a product API. If you are > stuck making a toast or mock URL work, stop — implement the > exchange row below instead. See AGENTS.md › *Gallery demos are not > the product API*.

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `GET /app/{region}/rows?q=&sort=&dir=&page=&page_size=` | the tbody, on `load` and on `dz-grid:refresh` (fired by a sort click, a filter change, a debounced search keystroke, or a page control) — with `page=` added for pagination | the current page's `<tr>` rows for the query — each a `dz-tr-row` carrying a stable `id` (the idiomorph morph key) plus `data-dz-grid-row-id` (the bulk-action payload anchor) — plus the repainted pagination footer (via an OOB `<nav>` or a wrapping region swap); a zero-result query returns an empty tbody so the `:has(tbody tr td)`-driven empty-state shows | innerMorph of the tbody (`[data-dz-grid-body]`) — idiomorph keys on each row's `id`, so a live selection follows its row across a re-sort — PLUS an out-of-band update of the pagination footer: append `<nav data-dz-grid-pagination data-dz-grid-total="N" hx-swap-oob="true">…</nav>` to the response (the stamped total feeds the all-matching affordance) (or target a wrapping region that contains both the tbody and the footer in one swap). The footer's current-page button carries `aria-current="page"` — the client reads it back as the authoritative (possibly server-clamped) page | loading empty populated error |
| `POST /app/{region}/bulk` | a bulk-action button (e.g. Delete), after the user approves its confirm dialog; the controller injects the selection on `htmx:configRequest` | the server RE-VALIDATES permissions and RE-SCOPES the action to the echoed query (never trusting the client `selected_ids` alone) and applies it. Two patterns: with `data-dz-grid-bulk-refresh` on the button (this demo), the response swaps NOTHING (JSON/204) and the controller re-fetches rows + footer via the normal GET; without it, put `hx-target` on the button and return the refreshed `<tr>` rows directly. When `all_matching_selected=true`, the action applies to the WHOLE matched query minus `excluded_ids` — the server re-runs the echoed query itself, and MUST strip `page`/`page_size` first (they window the display, not the matched set — re-running them verbatim would apply the action to one page only); `selected_ids` is informational (visible state) only. NB form encoding: with no exclusions the `excluded_ids` key is ABSENT from the POST (not sent empty) — default it to the empty list | innerMorph of the tbody (`[data-dz-grid-body]`) plus the OOB footer (its `data-dz-grid-total` re-stamps the matched total) | populated empty error |
| `PUT /app/{entity}/{id}` | the inline-edit extension (dz-grid-edit.js): dblclick an editable cell's display span opens an in-cell editor; Enter (or a change, for bool/select/date) commits a raw fetch PUT to `{data-dz-grid-edit-url}/{rowId}` — NOT an htmx exchange | this is the entity's STANDARD update route, not a bespoke field endpoint: the body is a single-field JSON object (`{"plan": "Pro"}`), so an all-optional update schema + exclude-unset semantics make it a partial update, and the full update gate (permissions, scoping, validation) applies. Return 2xx JSON on success; any non-2xx keeps the editor open with the response text as its error. The controller then fires `dz-grid:refresh` on the tbody, so the committed value renders SERVER-side (badges/dates re-render; no client patching) | none (raw fetch) — the follow-up `dz-grid:refresh` re-fetches rows + footer via the tbody's normal GET | populated error |

## Morph / swap

Stem: `stems/morph-safe-hypermedia.md` · decisions 0005–0007. Morph for **stable** surfaces; replacement for **disposable** fragments. Gallery mocks may approximate morph with `innerHTML` — production follows the swap column in **Server exchange**.

### Morph (persistent region)

- `GET /app/{region}/rows?q=&sort=&dir=&page=&page_size=` → innerMorph of the tbody (`[data-dz-grid-body]`) — idiomorph keys on each row's `id`, so a live selection follows its row across a re-sort — PLUS an out-of-band update of the pagination footer: append `<nav data-dz-grid-pagination data-dz-grid-total="N" hx-swap-oob="true">…</nav>` to the response (the stamped total feeds the all-matching affordance) (or target a wrapping region that contains both the tbody and the footer in one swap). The footer's current-page button carries `aria-current="page"` — the client reads it back as the authoritative (possibly server-clamped) page
- `POST /app/{region}/bulk` → innerMorph of the tbody (`[data-dz-grid-body]`) plus the OOB footer (its `data-dz-grid-total` re-stamps the matched total)

### No HTML swap (raw fetch / companion OOB)

- `PUT /app/{entity}/{id}` → none (raw fetch) — the follow-up `dz-grid:refresh` re-fetches rows + footer via the tbody's normal GET

### Identity rules

- Morph participants need **stable** `id` / domain keys (not loop indexes).
- Carry selection/edit affordances in the **DOM** (checked, `data-*`, ARIA) — not Alpine/`x-data` or a JS array a morph would orphan.
- Mark third-party widgets as explicit islands / morph-skip boundaries.

## How to use it

### Seams

- column visibility: dz-grid-cols.js projects the hidden set onto [data-dz-col] cells after every swap — no per-cell bindings
- column resize: dz-grid-resize.js rides the header cells
- inline edit: dz-grid-edit.js reads the [data-dz-grid-edit] display span (kind/value/label/options) — contract in contracts/grid_edit.py
- kind=select cells open a bare native <select> editor — NOT the combobox Hyperpart (dense row, morph-safe, commit-on-change PUT)
- row identity: a row's id IS the idiomorph morph key and encodes data-dz-row-id (the bulk payload anchor)

### Do / Don't

| Do | Don't |
|---|---|
| keep selection state in the DOM (.checked on the row checkbox) | mirror selection into a JS array a tbody swap would orphan |
| return full row fragments from the grid endpoint | return cell deltas the client must splice in |
| use bare select for in-cell enum edit (current contract) | assume grid dogfoods combobox because both have 'select' UX |
| innerMorph the tbody; give each row a stable `id` (morph key) + `data-dz-grid-row-id` (bulk anchor) | innerHTML-replace the tbody without stable row ids (selection follows DOM position, not the entity) |
| use `hx-swap=none` + `dz-grid:refresh` for bulk when a full re-fetch is clearer than splicing | morph a flash/toast region that should fully reset |
| park in-flight edit buffer on the grid root (outside the morph path) | store open-cell edit state only in a JS object the tbody morph drops |

### Pitfalls

- edit state in JS objects dies on morph — the typed buffer lives on the grid root (root._dzEdit) with before/after-swap hooks
- select options must be JSON [[value,label],…] — producers with dicts/tuples/bare strings normalise at ONE boundary (#1573)
- never patch committed values client-side — commit fires dz-grid:refresh so the server re-renders badges/dates
- do not mount data-dz-combobox inside a grid cell expecting grid-edit to drive it — that is a future composition, not current seam

### Keyboard / AT

- Enter commits (text/date), Escape cancels an open editor
- Tab / Shift-Tab commit then advance to the next/previous editable cell, wrapping to the adjacent row
- row checkboxes carry aria-label 'Select {row}'

### Related parts

- `button` — agents/button.md
- `badge` — agents/badge.md

### Does not compose

Local primitives that look like another Hyperpart. Declared in the registry; CI-locked. See `CONSUMER_MAP.md`.

- does **not** use `combobox` (kind=select in-cell editor): bare <select class=dz-inline-edit-select> for density, morph survival (root._dzEdit + before/after-swap), and commit-on-change PUT — not the progressive-enhancement combobox overlay — spike `docs/spikes/combobox-in-grid-cell.md`

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/grid.py`

- **Required root:** `[data-dz-grid]` (part `grid`)

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: grid — root contract (thin). The base grid's structural
root attributes; the data-bearing seams live in extension contracts
(grid_edit). Root-only: no ingestion model, no exemplars."""

from contracts._kit import DomContract

DOM_CONTRACT = DomContract(
    part="grid",
    root="[data-dz-grid]",
    nodes=(),
)

__all__ = ["DOM_CONTRACT"]
```

### `contracts/grid_edit.py`

- **Required root:** `[data-dz-grid][data-dz-grid-edit-url]` (part `grid-edit`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-grid-edit]` | `data-dz-edit-kind` | one of ['text', 'date', 'bool', 'select'] |
| `[data-dz-grid-edit]` | `data-dz-edit-value` | present (any value) |
| `[data-dz-grid-edit]` | `data-dz-edit-label` | present (any value) |
| `[data-dz-grid-edit]` | `data-dz-edit-options` | JSON [[value, label], …]; required when {'data-dz-edit-kind': 'select'} |

#### Ingestion model `GridEditCell`

| Field | Type | Required |
|---|---|---|
| `col` | `string` | yes |
| `kind` | `string ∈ ['text', 'date', 'bool', 'select']` | yes |
| `value` | `string` | yes |
| `label` | `string` | yes |
| `options` | `array | null` | no |

#### Exemplar `render()`

```python
def render(cell: GridEditCell) -> str:
    """Model → conforming display-span fragment (the seam the controller reads)."""
    opts = ""
    if cell.kind == "select" and cell.options is not None:
        pairs = json.dumps([[v, label] for v, label in cell.options])
        opts = f' data-dz-edit-options="{html.escape(pairs, quote=True)}"'
    return (
        f'<span class="dz-tr-cell-display" '
        f'data-dz-grid-edit="{html.escape(cell.col, quote=True)}" '
        f'data-dz-edit-kind="{cell.kind}" '
        f'data-dz-edit-value="{html.escape(cell.value, quote=True)}" '
        f'data-dz-edit-label="{html.escape(cell.label, quote=True)}"{opts}>'
        f"{html.escape(cell.value)}</span>"
    )
```

#### FastAPI feed example — grid-edit exemplar — how a server feeds the inline-edit seam

```python
@app.get("/rows", response_class=HTMLResponse)
def rows() -> str:
    """A tbody fragment: what a real endpoint returns to fill the grid.
    Mirrors Dazzle's shape: the grid ROOT (with data-dz-grid-edit-url)
    is page furniture; this endpoint returns rows whose editable cells
    carry the seam spans."""
    cells = "".join(f"<td>{render(c)}</td>" for c in EXEMPLARS[:3])
    return f'<tr id="row-1">{cells}</tr>'
```

### `contracts/grid_cols.py`

- **Required root:** `[data-dz-grid]` (part `grid-cols`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-grid-col-toggle]` | `data-dz-grid-col-toggle` | present (any value) |
| `[data-dz-col]` | `data-dz-col` | present (any value) |
| `[data-dz-grid-cols-reset]` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: grid (extension: dz-grid-cols) — column visibility seam."""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="grid-cols",
    root="[data-dz-grid]",
    nodes=(
        Node("[data-dz-grid-col-toggle]", attrs={"data-dz-grid-col-toggle": Present()}),
        Node("[data-dz-col]", attrs={"data-dz-col": Present()}),
        Node("[data-dz-grid-cols-reset]", attrs={}),
    ),
)

__all__ = ["DOM_CONTRACT"]
```

### `contracts/grid_resize.py`

- **Required root:** `[data-dz-grid]` (part `grid-resize`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-grid-resize]` | `data-dz-grid-resize` | present (any value) |
| `col[data-dz-col], [data-dz-col]` | `data-dz-col` | present (any value) |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: grid (extension: dz-grid-resize) — column resize seam."""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="grid-resize",
    root="[data-dz-grid]",
    nodes=(
        Node("[data-dz-grid-resize]", attrs={"data-dz-grid-resize": Present()}),
        Node("col[data-dz-col], [data-dz-col]", attrs={"data-dz-col": Present()}),
    ),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

The tbody hydrates over the wire — hx-get on load fetches the rows, and innerMorph swaps them in. Each row carries a stable id (the idiomorph morph key) so a selection follows its row — not its DOM position — across a re-sort or paginate; data-dz-grid-row-id stays the bulk-action payload anchor, and the id encodes it so the two agree. Loading is pure-CSS (.htmx-request → the overlay, #972 — no controller flag idiomorph could strip). Selection is delegated + state-in-DOM: dz-grid.js counts the checked [data-dz-grid-select] boxes, writes the total to data-dz-bulk-count, and the CSS reveals the .dz-bulk-actions bar; the count / select-all tri-state re-sync on change and on htmx:afterSwap. Sorting is delegated + state-in-DOM too: a header button ([data-dz-grid-sort]) cycles its column none → ascending → descending → none (state on the th's aria-sort, one active column), rebuilds the tbody's request query, and fires dz-grid:refresh so the server returns the re-ordered rows — no client-side row rendering. Filters and search ride the same seam: a [data-dz-grid-filter] select (on change) and the [data-dz-grid-search] box (on input, debounced) each rebuild the query and compose with the active sort — all read from the DOM into one query; an empty result reveals the empty-state. Note the Status filter is a teaching case: the table renders no Status column, yet the filter narrows on it — filters (like scopes) can target any queryable server field, not only what's displayed (here only Plan is both shown and filtered). Bulk actions post the selection safely: the [data-dz-grid-bulk-action] Delete button (behind its confirm dialog) sends the action + selected ids + the current query — so the server re-scopes and re-validates rather than trusting client ids (§15). Select all N results escalates a page selection to the whole result set for the current query — search + filters + sort scope, including rows on other pages (not “visually similar” rows). State on the root: data-dz-grid-all-matching + a data-dz-grid-excluded JSON list of unchecked exceptions) — rows on other pages arrive selected, the count shows the server-stamped matched total (the footer's data-dz-grid-total), and a bulk action sends all_matching_selected=true + excluded_ids so the server applies it to the matched set minus exclusions. A filter or search change drops the mode (the matched set changed); sort and paging keep it. The footer is server-rendered: the client intercepts a page click, adds page= to the query, and the server returns that page's rows plus the repainted footer (row slice + total from one query, so they can't disagree); sort / filter / search reset to page 1. The Per page select is a windowing control on the same seam ([data-dz-grid-page-size] → page_size=): it re-pages the same matched set, resets to page 1, and — unlike a filter/search change — keeps an all-matching selection. State is URL-synced (data-dz-grid-url, opt-in): the grid's query mirrors into the address bar as the same human-readable params the server sees — deep links restore on load (before the hydration fetch, so no double fetch), discrete actions push history entries (Back walks grid states), the debounced search replaces, and foreign URL params survive (the grid only touches its own keys). The all-matching selection is ephemeral and deliberately NOT in the URL. The three extensions are opt-in per grid, keyed off their own seams. Column visibility (dz-grid-cols.js): the Columns <details> menu's checkboxes ([data-dz-grid-col-toggle]) project a hidden set onto every [data-dz-col] cell — header, hydrated tds, and the colgroup's <col> — persisted per grid id in localStorage; re-fetched rows re-hide on swap; stale keys prune at init. Column resize (dz-grid-resize.js): a pointer drag on the in-th handle ([data-dz-grid-resize]) widens col[data-dz-col] live (snap-8, clamp 80–800px), persists per grid, and never fires the header's sort; the table stays table-layout:auto, so a width is a strong hint. Inline edit (dz-grid-edit.js): dblclick a cell's display span ([data-dz-grid-edit] + data-dz-edit-kind/-value/-label/-options) to open an in-cell editor; Enter commits, Escape cancels, Tab advances — the commit is a single-field JSON PUT to the entity's standard update route (data-dz-grid-edit-url on the root; no bespoke field endpoint), and a dz-grid:refresh re-renders the row server-side. An in-flight edit survives a tbody swap: the buffer lives on the grid root, outside the morph path. (The gallery mock approximates the innerMorph swap with an innerHTML replace — copy the snippet into a real htmx4 app, with the idiomorph extension for hx-swap="innerMorph", for true morph-preserved selection.)

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/grid.py`
- `contracts/grid_edit.py`
- `contracts/grid_cols.py`
- `contracts/grid_resize.py`
- `controllers/dz-grid.js`
- `controllers/dz-grid-cols.js`
- `controllers/dz-grid-resize.js`
- `controllers/dz-grid-edit.js`
