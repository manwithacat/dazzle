# List region (`list-region`)

The in-card data table: CSV export, sortable headers, a scrollable table body, and an overflow count.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="list-region" data-list-region id="hm-list-region-demo">
  <div class="list-actions">
    <div class="list-action-group"><button type="button" class="list-csv-button" title="Export CSV" aria-label="Export CSV" data-csv-endpoint="sample-list-export.csv" data-csv-filename="work-items.csv" onclick="window.dz.downloadCsv(this.dataset.dzCsvEndpoint||this.dataset.csvEndpoint, this.dataset.dzCsvFilename||this.dataset.csvFilename)"><svg class="icon" aria-hidden="true"><use href="#i-download"/></svg></button></div>
  </div>
  <div class="list-scroll">
    <table class="list-table">
      <thead>
        <tr>
          <th><a class="list-sort-link" hx-get="/mock/list-region?sort=name&amp;dir=desc" hx-target="closest [data-list-region]" hx-swap="outerHTML">Name<span>▲</span></a></th>
          <th><a class="list-sort-link" hx-get="/mock/list-region?sort=owner&amp;dir=asc" hx-target="closest [data-list-region]" hx-swap="outerHTML">Owner</a></th>
          <th><a class="list-sort-link" hx-get="/mock/list-region?sort=status&amp;dir=asc" hx-target="closest [data-list-region]" hx-swap="outerHTML">Status</a></th>
        </tr>
      </thead>
      <tbody>
        <tr class="list-row is-clickable">
          <td>Capacity review</td>
          <td>J. Dias</td>
          <td>Active</td>
        </tr>
        <tr class="list-row is-clickable">
          <td>Load study</td>
          <td>K. Novak</td>
          <td>Draft</td>
        </tr>
        <tr class="list-row is-clickable">
          <td>Quarterly audit</td>
          <td>M. Reyes</td>
          <td>Active</td>
        </tr>
        <tr class="list-row ">
          <td>Site walkdown</td>
          <td>M. Reyes</td>
          <td>Closed</td>
        </tr>
        <tr class="list-row ">
          <td>Vendor renewal</td>
          <td>A. Osei</td>
          <td>Draft</td>
        </tr>
      </tbody>
    </table>
  </div>
  <p class="list-overflow">Showing 5 of 5</p>
</div>
```

## Server exchange

When the client affordance finishes, htmx issues **this** request. Return the **response fragment** in the table (usually HTML, not JSON). Dazzle often implements these from the app model; a standalone HTMX4 app implements them explicitly.

> **Do not reimplement the gallery.** Flash toasts (e.g. confirm’s > “Deleted (demo).”), `/mock/*` paths, and other static-site > scaffolding are **demo-only** (`MOCK_HTMX` in `site/build_site.py`). > They are not Hyperpart surface and not a product API. If you are > stuck making a toast or mock URL work, stop — implement the > exchange row below instead. See AGENTS.md › *Gallery demos are not > the product API*.

| Request | Trigger | Response fragment | Swap | Envelope | States |
|---|---|---|---|---|---|
| `GET /mock/list-region` | click on a sort header | Full list-region outerHTML reordered by ?sort=&dir= (leftover-honest include_closed / as_of ride); active column caret ▲/▼ | closest [data-dz-list-region] outerHTML | `outer` | populated |
| `GET sample-list-export.csv` | click Export CSV (via dz.downloadCsv) | text/csv file body (download, not a DOM swap) | n/a — Blob download | `none` | populated error |

## Swap contract

Agent-visible HTMX topology (ADR-0054 / decision 0012). **Exchange envelope** = what the response may re-emit relative to the persistent slot (`body_only` | `outer` | `none` | `host_owned` | `document`). Dual-lock validates part markup only — not this envelope. Stem: `stems/morph-safe-hypermedia.md`.

Gallery mocks may approximate morph with `innerHTML` — production follows the swap column in **Server exchange**.

### Exchanges (swap · envelope)

- `GET /mock/list-region` → closest [data-dz-list-region] outerHTML · **envelope=`outer`**
- `GET sample-list-export.csv` → n/a — Blob download · **envelope=`none`**

### Replace / other HTML swap

- `GET /mock/list-region` → outer
- `GET sample-list-export.csv` → none

### Envelope rules

- **`body_only`** — innerHTML / innerMorph into a slot; response is interior only (no re-wrap of slot id / nested `data-dz-region`).
- **`outer`** — outerHTML / outerMorph; response may carry identity.
- **`none`** — no HTML swap (JSON/204/bytes; client or OOB companion).
- **`host_owned`** — swap target/mode chosen by the host button's `hx-target` / `hx-swap` (part does not fix the envelope).
- **`document`** — full navigation / document load (not a fragment).
- Slot owns stable `id` / domain keys; state in DOM, not Alpine.

### Envelope response examples

What the **server returns** for each exchange. Match the **exchange envelope**; dual-lock still applies to interior markup.

#### `GET /mock/list-region` · envelope=`outer`

Correct response for outer (outerHTML / outerMorph) replacing #slot.

**Do — correct response body**

```html
<!-- envelope=outer → response root may carry the slot identity -->
<div id="slot" class="dz-card" data-dz-card>
  <!-- full replacement of the previous element -->
</div>
```

**Don’t — violates `outer`**

```html
<!-- WRONG for outer: body-only fragment when the host expects a full element -->
<!-- (missing root that matches hx-target — leaves empty or nested junk) -->
<span>partial content without the target root</span>
```

#### `GET sample-list-export.csv` · envelope=`none`

Correct response for none (raw fetch / no HTML swap).

**Do — correct response body**

```text
// envelope=none — no HTML swap (JSON/204; client or OOB companion)
// HTTP 204 No Content
// or:
{ "ok": true }
// Application/json; status 200
// Optional: separate OOB HTML fragments if the host declares them
```

**Don’t — violates `none`**

```text
<!-- WRONG: HTML body when hx-swap is none / raw fetch expects JSON|204 -->
<div class="dz-alert">Deleted</div>
```

## How to use it

No extended guidance authored yet — start from Copy this and the dependency chips.

### Seams

- copy the partial under Copy this; keep root class and data-* modifiers so the CSS/JS bundle matches
- implement Server exchange endpoints; return HTML fragments, not JSON
- satisfy the DOM contract tables (CI stop-ship)

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/list_region.py`

- **Required root:** `[data-dz-list-region]` (part `list-region`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-list-region]` | `data-dz-list-region` | present (any value) |

#### Ingestion model `ListRegion`

| Field | Type | Required |
|---|---|---|
| `body_html` | `string` | no |

#### Exemplar `render()`

```python
def render(lr: ListRegion) -> str:
    """Model → list-region root wrapper."""
    return f'<div class="dz-list-region" data-dz-list-region>{lr.body_html}</div>'
```

## Notes

Dual-lock root is data-dz-list-region (contracts/list_region.py). CSV export is wired with data-dz-csv-endpoint + data-dz-csv-filename and window.dz.downloadCsv (gallery serves sample-list-export.csv as the downloadable artifact). Sortable headers are dz-list-sort-link anchors with hx-get ?sort=&dir= — leftover-honest include_closed / as_of ride the hx-get (cycle 2172); dropping them invents open-only / current after a sort click. Rest-state gallery omits them (oral #33). The host re-renders the region; the active column shows a caret. Rows with a drill URL carry is-clickable. For selection/filters/pagination use the grid Hyperpart.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/list_region.py`
