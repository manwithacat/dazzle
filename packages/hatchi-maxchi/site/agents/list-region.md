# List region (`list-region`)

The in-card data table: an actions row with CSV export, a horizontally scrollable table, and an overflow count.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="list-region" data-list-region>
  <div class="list-actions">
    <div class="list-action-group"><button type="button" class="list-csv-button" title="Export CSV" aria-label="Export CSV"><svg class="icon" aria-hidden="true"><use href="#i-download"/></svg></button></div>
  </div>
  <div class="list-scroll">
    <table class="list-table">
      <thead>
        <tr>
          <th><a href="#" class="list-sort-link">Name<span>▲</span></a></th>
          <th>Owner</th>
          <th>Status</th>
        </tr>
      </thead>
      <tbody>
        <tr class="list-row is-clickable">
          <td>Quarterly audit</td>
          <td>M. Reyes</td>
          <td>Active</td>
        </tr>
        <tr class="list-row ">
          <td>Vendor renewal</td>
          <td>A. Osei</td>
          <td>Draft</td>
        </tr>
      </tbody>
    </table>
  </div>
  <p class="list-overflow">Showing 2 of 14</p>
</div>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

No extended guidance authored yet — start from Copy this and the dependency chips.

### Seams

- copy the partial under Copy this; keep root class and data-* modifiers so the CSS/JS bundle matches
- no Server exchange on this part — pure presentation or client chrome
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

Dual-lock root is data-dz-list-region (contracts/list_region.py). The CSV button is ALWAYS rendered in the actions row. The snippet omits its wiring: the real emitter adds data-dz-csv-endpoint/data-dz-csv-filename and an onclick that calls window.dz.downloadCsv(endpoint, filename) against the server export route. Sortable headers are dz-list-sort-link anchors carrying an hx-get with ?sort=<col>&dir=<asc|desc> — the server re-renders the region; the active column shows a text caret. Rows wired to a drill URL carry is-clickable; the overflow line reports what the page cut. For the full hypermedia table primitive (selection, filters, pagination) use the grid Hyperpart — this one is the lighter in-card region.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/list_region.py`
