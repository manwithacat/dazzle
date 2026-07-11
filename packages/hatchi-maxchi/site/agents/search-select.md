# Search select (`search-select`)

The FK typeahead: debounced remote search into a listbox, then a per-row select exchange that fills a hidden id. Domain data maps into a fixed result-row anatomy (name / secondary / optional media) — do not invent a new combobox per entity. Demo: focus the input (or type) to open; media is optional so some rows are text-only.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="search-select hm-measure" data-widget="search_select" data-blur-grace-ms="200" data-confirm-hold-ms="1800">
  <input type="hidden" name="company" id="hm-ss-field" value="">
  <input type="text" id="hm-ss-input" class="search-select-input" placeholder="Search companies, people, SKUs…" autocomplete="off" role="combobox" aria-expanded="false" aria-controls="hm-ss-results" aria-autocomplete="list" aria-haspopup="listbox" hx-get="/mock/typeahead" hx-trigger="load, keyup changed delay:300ms" hx-target="#hm-ss-results" hx-params="q">
  <div id="hm-ss-results" role="listbox" aria-label="Suggestions" class="search-select-results">
    <div class="search-select-prompt" role="option" aria-disabled="true">Type to search — rows share one anatomy; media is optional</div>
  </div>
</div>
```

## Server exchange

When the client affordance finishes, htmx issues **this** request. Return the **response fragment** in the table (usually HTML, not JSON). Dazzle often implements these from the app model; a standalone HTMX4 app implements them explicitly.

> **Do not reimplement the gallery.** Flash toasts (e.g. confirm’s > “Deleted (demo).”), `/mock/*` paths, and other static-site > scaffolding are **demo-only** (`MOCK_HTMX` in `site/build_site.py`). > They are not Hyperpart surface and not a product API. If you are > stuck making a toast or mock URL work, stop — implement the > exchange row below instead. See AGENTS.md › *Gallery demos are not > the product API*.

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `GET /app/fragments/search?source={source}&q=` | keyup on the combobox, debounced (`delay:{n}ms`) | HTML fragment: zero-or-more `.dz-search-result-row` options (fixed anatomy: optional media + name + optional secondary; each row hx-gets the select endpoint) OR one `.dz-search-result-empty` prompt — never JSON | innerHTML into the listbox | prompt/min-chars results empty error |
| `GET /app/fragments/select?source={source}&id={id}` | click / activate on a result row | confirm fragment replacing the listbox (`dz-select-result-confirm`) and server-side fill of the hidden FK (and usually the typeahead label via OOB) | innerHTML (listbox) + OOB for hidden/input as needed | selected |

### `GET /app/fragments/search?source={source}&q=` — example handler

Application code (not the dual-lock module). FastAPI-shaped; do not use `from __future__ import annotations` in route files (ADR-0014).

```python
# Search exchange — map domain → fixed row anatomy.
# Do NOT invent a new picker per entity shape.
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

app = FastAPI()


@app.get("/app/fragments/search", response_class=HTMLResponse)
def search(source: str, q: str = Query("")) -> str:
    # rows = query_domain(source, q)
    # return "".join(render_result_row(SearchResultRow(
    #     id=r.id, name=r.title, secondary=r.meta,
    #     media_html=r.avatar_html or "",
    #     select_url=f"/app/fragments/select?source={source}&id={r.id}",
    #     results_target="#search-results-company",
    # )) for r in rows)
    return (
        '<div class="dz-search-result-row" role="option" '
        'hx-get="/app/fragments/select?source=companies&id=1" '
        'hx-target="#search-results-company" hx-swap="innerHTML">'
        '<div class="dz-search-result-body">'
        '<div class="dz-search-result-name">Acme Ltd</div>'
        '<div class="dz-search-result-secondary">Co. 123</div>'
        "</div></div>"
    )
```

### `GET /app/fragments/select?source={source}&id={id}` — example handler

Application code (not the dual-lock module). FastAPI-shaped; do not use `from __future__ import annotations` in route files (ADR-0014).

```python
# Select exchange — fill the hidden FK server-side.
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI()


@app.get("/app/fragments/select", response_class=HTMLResponse)
def select(source: str, id: str) -> str:
    # label = load_label(source, id)
    return (
        f'<div class="dz-select-result-confirm" role="status">'
        f"Selected {id}</div>"
        # + OOB: <input type=hidden name=… value=id hx-swap-oob>
        # + OOB: typeahead value=label hx-swap-oob
    )
```

## How to use it

### Seams

- shell: hidden FK + typeahead input + listbox panel (`data-dz-widget=search_select`)
- data-dz-blur-grace-ms (default 200) — blur→close delay so row clicks land; data-dz-confirm-hold-ms (default 1500, alias confirm-dwell-ms) — auto-dismiss hold after .dz-select-result-confirm paints
- search exchange returns N× fixed result-row fragments (or `.dz-search-result-empty`) — map domain into name / secondary / optional media (omit media for text-only rows)
- each row carries its own hx-get to the select exchange
- select exchange: confirm line (+ OOB hidden FK / label) — never client-side write of the id

### Do / Don't

| Do | Don't |
|---|---|
| map any record to SearchResultRow (id, name, secondary?, media_html?) and render_result_row | build a bespoke listbox DOM per entity or return JSON for the client to paint |
| set data-dz-confirm-hold-ms when the confirm line is user-facing | rely on blur grace alone to show select feedback |
| swap the panel with a confirmation fragment that fills the hidden FK server-side | copy the visible label into a hidden field from client JS |

### Pitfalls

- blur grace is NOT confirm hold — without confirm-hold-ms the select feedback is hidden as soon as focus leaves (~200ms)
- form posts the hidden input, never the visible text
- do not invent a new combobox Hyperpart for 'users vs companies' — same row anatomy, different field mapping; missing media is valid
- media is optional free HTML inside `.dz-search-result-media` (img, initials, icon) — keep primary text in `.dz-search-result-name`

### Keyboard / AT

- aria-expanded / data-dz-open flip on focusin/focusout for the results panel
- result rows are role=option with their own activatable hx-get
- media slot is aria-hidden when decorative (initials/icon)

### Related parts

- `field` — agents/field.md
- `search-box` — agents/search-box.md
- `avatar` — agents/avatar.md

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/search_select.py`

- **Required root:** `[data-dz-widget="search_select"]` (part `search-select`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-widget="search_select"]` | `—` | — |

#### Ingestion model `SearchResultRow`

| Field | Type | Required |
|---|---|---|
| `id` | `string` | yes |
| `name` | `string` | yes |
| `secondary` | `string` | no |
| `media_html` | `string` | no |
| `select_url` | `string` | yes |
| `results_target` | `string` | yes |

#### Exemplar `render()`

```python
def render(row: SearchResultRow) -> str:
    return render_result_row(row)
```

## Notes

One Hyperpart, two surfaces. (1) Shell — hidden FK + typeahead + listbox; dz-search-select.js opens/closes (data-dz-open / aria-expanded). Timing knobs on the root: data-dz-blur-grace-ms (default 200) — wait after blur so a result-row click can land; data-dz-confirm-hold-ms (default 1500; alias data-dz-confirm-dwell-ms) — how long to keep the panel open after a select exchange paints .dz-select-result-confirm (auto-dismiss hold; 0 = no hold). (2) Result rows — fixed micro-pattern: optional .dz-search-result-media + name + optional secondary. Different shapes in one list are intentional: media is optional — a company row without a badge and a person row with initials are the same Hyperpart. Map domain fields into slots; do not invent a picker per entity. Form posts the hidden input, never the visible text. contracts/search_select.py (SearchResultRow + render_result_row).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/search_select.py`
- `controllers/dz-search-select.js`
