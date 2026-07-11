# Data table (`grid`)

A server-rendered data table on a real <table>, all HTML over the wire: search, sortable headers, filters, row selection (one page or every matching row), bulk actions, pagination, and deep-linkable URL-synced state. Optional extensions add column visibility, column resize, and inline cell editing. The wiring lives in the Agent Implementation Guidance below.

## Partial (copy-paste; the live demo renders this exact string)

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

## Exchanges (the endpoint contract your server must satisfy)

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `GET /app/{region}/rows?q=&sort=&dir=&page=&page_size=` | the tbody, on `load` and on `dz-grid:refresh` (fired by a sort click, a filter change, a debounced search keystroke, or a page control) — with `page=` added for pagination | the current page's `<tr>` rows for the query — each a `dz-tr-row` carrying a stable `id` (the idiomorph morph key) plus `data-dz-grid-row-id` (the bulk-action payload anchor) — plus the repainted pagination footer (via an OOB `<nav>` or a wrapping region swap); a zero-result query returns an empty tbody so the `:has(tbody tr td)`-driven empty-state shows | innerMorph of the tbody (`[data-dz-grid-body]`) — idiomorph keys on each row's `id`, so a live selection follows its row across a re-sort — PLUS an out-of-band update of the pagination footer: append `<nav data-dz-grid-pagination data-dz-grid-total="N" hx-swap-oob="true">…</nav>` to the response (the stamped total feeds the all-matching affordance) (or target a wrapping region that contains both the tbody and the footer in one swap). The footer's current-page button carries `aria-current="page"` — the client reads it back as the authoritative (possibly server-clamped) page | loading empty populated error |
| `POST /app/{region}/bulk` | a bulk-action button (e.g. Delete), after the user approves its confirm dialog; the controller injects the selection on `htmx:configRequest` | the server RE-VALIDATES permissions and RE-SCOPES the action to the echoed query (never trusting the client `selected_ids` alone) and applies it. Two patterns: with `data-dz-grid-bulk-refresh` on the button (this demo), the response swaps NOTHING (JSON/204) and the controller re-fetches rows + footer via the normal GET; without it, put `hx-target` on the button and return the refreshed `<tr>` rows directly. When `all_matching_selected=true`, the action applies to the WHOLE matched query minus `excluded_ids` — the server re-runs the echoed query itself, and MUST strip `page`/`page_size` first (they window the display, not the matched set — re-running them verbatim would apply the action to one page only); `selected_ids` is informational (visible state) only. NB form encoding: with no exclusions the `excluded_ids` key is ABSENT from the POST (not sent empty) — default it to the empty list | innerMorph of the tbody (`[data-dz-grid-body]`) plus the OOB footer (its `data-dz-grid-total` re-stamps the matched total) | populated empty error |
| `PUT /app/{entity}/{id}` | the inline-edit extension (dz-grid-edit.js): dblclick an editable cell's display span opens an in-cell editor; Enter (or a change, for bool/select/date) commits a raw fetch PUT to `{data-dz-grid-edit-url}/{rowId}` — NOT an htmx exchange | this is the entity's STANDARD update route, not a bespoke field endpoint: the body is a single-field JSON object (`{"plan": "Pro"}`), so an all-optional update schema + exclude-unset semantics make it a partial update, and the full update gate (permissions, scoping, validation) applies. Return 2xx JSON on success; any non-2xx keeps the editor open with the response text as its error. The controller then fires `dz-grid:refresh` on the tbody, so the committed value renders SERVER-side (badges/dates re-render; no client patching) | none (raw fetch) — the follow-up `dz-grid:refresh` re-fetches rows + footer via the tbody's normal GET | populated error |

## Contract modules (typed source of truth)

Epistemic lock: do not invent attrs or response shapes that diverge from these modules. CI validates exemplars against `DOM_CONTRACT` (`tests/test_contracts.py`).

### `contracts/grid.py`

- **DOM root:** `[data-dz-grid]` (part `grid`)
- Root-only DOM contract (no per-node attribute constraints).

**Module source**

```python
"""HYPERPART: grid — root contract (thin). The base grid's structural
root attributes; the data-bearing seams live in extension contracts
(grid_edit). Root-only: no ingestion model, no exemplars."""

from __future__ import annotations

from contracts._kit import DomContract

DOM_CONTRACT = DomContract(
    part="grid",
    root="[data-dz-grid]",
    nodes=(),
)

__all__ = ["DOM_CONTRACT"]
```

### `contracts/grid_edit.py`

- **DOM root:** `[data-dz-grid][data-dz-grid-edit-url]` (part `grid-edit`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-grid-edit]` | `data-dz-edit-kind` | one of ['text', 'date', 'bool', 'select'] |
| `[data-dz-grid-edit]` | `data-dz-edit-value` | present (any value) |
| `[data-dz-grid-edit]` | `data-dz-edit-label` | present (any value) |
| `[data-dz-grid-edit]` | `data-dz-edit-options` | JSON [[value, label], …]; required when {'data-dz-edit-kind': 'select'} |

**Ingestion model:** `GridEditCell`

| Field | Type | Required |
|---|---|---|
| `col` | `string` | yes |
| `kind` | `string ∈ ['text', 'date', 'bool', 'select']` | yes |
| `value` | `string` | yes |
| `label` | `string` | yes |
| `options` | `array | null` | no |

**Exemplar `render()`** (executable — CI)

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

**FastAPI exemplar** — grid-edit exemplar — how a server feeds the inline-edit seam

How a server feeds this seam (not the gallery mock):

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

- **DOM root:** `[data-dz-grid]` (part `grid-cols`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-grid-col-toggle]` | `data-dz-grid-col-toggle` | present (any value) |
| `[data-dz-col]` | `data-dz-col` | present (any value) |
| `[data-dz-grid-cols-reset]` | `—` | — |

**Module source**

```python
"""HYPERPART: grid (extension: dz-grid-cols) — column visibility seam."""

from __future__ import annotations

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

- **DOM root:** `[data-dz-grid]` (part `grid-resize`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-grid-resize]` | `data-dz-grid-resize` | present (any value) |
| `col[data-dz-col], [data-dz-col]` | `data-dz-col` | present (any value) |

**Module source**

```python
"""HYPERPART: grid (extension: dz-grid-resize) — column resize seam."""

from __future__ import annotations

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

## Guidance (structured)

### Seams

- column visibility: dz-grid-cols.js projects the hidden set onto [data-dz-col] cells after every swap — no per-cell bindings
- column resize: dz-grid-resize.js rides the header cells
- inline edit: dz-grid-edit.js reads the [data-dz-grid-edit] display span (kind/value/label/options) — contract in contracts/grid_edit.py
- row identity: a row's id IS the idiomorph morph key and encodes data-dz-row-id (the bulk payload anchor)

### Pitfalls

- edit state in JS objects dies on morph — the typed buffer lives on the grid root (root._dzEdit) with before/after-swap hooks
- select options must be JSON [[value,label],…] — producers with dicts/tuples/bare strings normalise at ONE boundary (#1573)
- never patch committed values client-side — commit fires dz-grid:refresh so the server re-renders badges/dates

### Keyboard / AT

- Enter commits (text/date), Escape cancels an open editor
- Tab / Shift-Tab commit then advance to the next/previous editable cell, wrapping to the adjacent row
- row checkboxes carry aria-label 'Select {row}'

### Do / Don't

| Do | Don't |
|---|---|
| keep selection state in the DOM (.checked on the row checkbox) | mirror selection into a JS array a tbody swap would orphan |
| return full row fragments from the grid endpoint | return cell deltas the client must splice in |

### Composes with

- `button` (agents/button.md)
- `badge` (agents/badge.md)

## Guidance (prose; HTML from the registry notes field)

The tbody hydrates over the wire — <code>hx-get</code> on <code>load</code> fetches the rows, and <code>innerMorph</code> swaps them in. Each row carries a stable <code>id</code> (the idiomorph <em>morph key</em>) so a selection follows its <em>row</em> — not its DOM position — across a re-sort or paginate; <code>data-dz-grid-row-id</code> stays the bulk-action payload anchor, and the id encodes it so the two agree. Loading is pure-CSS (<code>.htmx-request</code> → the overlay, #972 — no controller flag idiomorph could strip). Selection is delegated + state-in-DOM: <code>dz-grid.js</code> counts the checked <code>[data-dz-grid-select]</code> boxes, writes the total to <code>data-dz-bulk-count</code>, and the CSS reveals the <code>.dz-bulk-actions</code> bar; the count / select-all tri-state re-sync on change and on <code>htmx:afterSwap</code>. Sorting is delegated + state-in-DOM too: a header button (<code>[data-dz-grid-sort]</code>) cycles its column none → ascending → descending → none (state on the th's <code>aria-sort</code>, one active column), rebuilds the tbody's request query, and fires <code>dz-grid:refresh</code> so the <em>server</em> returns the re-ordered rows — no client-side row rendering. Filters and search ride the same seam: a <code>[data-dz-grid-filter]</code> select (on change) and the <code>[data-dz-grid-search]</code> box (on input, debounced) each rebuild the query and <em>compose</em> with the active sort — all read from the DOM into one query; an empty result reveals the empty-state. Note the <strong>Status</strong> filter is a teaching case: the table renders no Status column, yet the filter narrows on it — filters (like scopes) can target <em>any</em> queryable server field, not only what's displayed (here only <strong>Plan</strong> is both shown and filtered). Bulk actions post the selection safely: the <code>[data-dz-grid-bulk-action]</code> Delete button (behind its confirm dialog) sends the action + selected ids + the <em>current query</em> — so the server re-scopes and re-validates rather than trusting client ids (§15). <strong>Select all N results</strong> escalates a page selection to the whole result set for the current query — search + filters + sort scope, including rows on other pages (not “visually similar” rows). State on the root: <code>data-dz-grid-all-matching</code> + a <code>data-dz-grid-excluded</code> JSON list of unchecked exceptions) — rows on other pages arrive selected, the count shows the server-stamped matched total (the footer's <code>data-dz-grid-total</code>), and a bulk action sends <code>all_matching_selected=true</code> + <code>excluded_ids</code> so the server applies it to the matched set minus exclusions. A filter or search change drops the mode (the matched set changed); sort and paging keep it. The footer is <em>server-rendered</em>: the client intercepts a page click, adds <code>page=</code> to the query, and the server returns that page's rows plus the repainted footer (row slice + total from one query, so they can't disagree); sort / filter / search reset to page 1. The <strong>Per page</strong> select is a windowing control on the same seam (<code>[data-dz-grid-page-size]</code> → <code>page_size=</code>): it re-pages the same matched set, resets to page 1, and — unlike a filter/search change — keeps an all-matching selection. State is <strong>URL-synced</strong> (<code>data-dz-grid-url</code>, opt-in): the grid's query mirrors into the address bar as the same human-readable params the server sees — deep links restore on load (before the hydration fetch, so no double fetch), discrete actions push history entries (Back walks grid states), the debounced search replaces, and foreign URL params survive (the grid only touches its own keys). The all-matching selection is ephemeral and deliberately NOT in the URL. The three <strong>extensions</strong> are opt-in per grid, keyed off their own seams. <em>Column visibility</em> (<code>dz-grid-cols.js</code>): the Columns <code>&lt;details&gt;</code> menu's checkboxes (<code>[data-dz-grid-col-toggle]</code>) project a hidden set onto every <code>[data-dz-col]</code> cell — header, hydrated tds, and the colgroup's <code>&lt;col&gt;</code> — persisted per grid id in localStorage; re-fetched rows re-hide on swap; stale keys prune at init. <em>Column resize</em> (<code>dz-grid-resize.js</code>): a pointer drag on the in-th handle (<code>[data-dz-grid-resize]</code>) widens <code>col[data-dz-col]</code> live (snap-8, clamp 80–800px), persists per grid, and never fires the header's sort; the table stays <code>table-layout:auto</code>, so a width is a strong hint. <em>Inline edit</em> (<code>dz-grid-edit.js</code>): dblclick a cell's display span (<code>[data-dz-grid-edit]</code> + <code>data-dz-edit-kind/-value/-label/-options</code>) to open an in-cell editor; Enter commits, Escape cancels, Tab advances — the commit is a single-field JSON <strong>PUT to the entity's standard update route</strong> (<code>data-dz-grid-edit-url</code> on the root; no bespoke field endpoint), and a <code>dz-grid:refresh</code> re-renders the row server-side. An in-flight edit survives a tbody swap: the buffer lives on the grid root, outside the morph path. (The gallery mock approximates the <code>innerMorph</code> swap with an innerHTML replace — copy the snippet into a real htmx4 app, with the idiomorph extension for <code>hx-swap=&quot;innerMorph&quot;</code>, for true morph-preserved selection.)

## Controller files

- `controllers/dz-grid.js`
- `controllers/dz-grid-cols.js`
- `controllers/dz-grid-resize.js`
- `controllers/dz-grid-edit.js`
