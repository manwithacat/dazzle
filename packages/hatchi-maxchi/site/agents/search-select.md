# Search select (`search-select`)

The FK typeahead: debounced remote search into a listbox, then a per-row select exchange that fills a hidden id. Domain data maps into a fixed result-row anatomy (name / secondary / optional media) — do not invent a new combobox per entity. Demo: focus the input (or type) to open; media is optional so some rows are text-only.

> **Layer:** L1 surface · **Recipe:** `remote-fk-typeahead` — remote FK typeahead
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="search-select hm-measure" data-widget="search_select" data-blur-grace-ms="200" data-confirm-hold-ms="1800">
  <input type="hidden" name="company" id="hm-ss-field" value="">
  <input type="text" id="hm-ss-input" class="search-select-input" name="q" form="hm-detached-q" placeholder="Search companies, people, SKUs…" autocomplete="off" role="combobox" aria-expanded="false" aria-controls="hm-ss-results" aria-autocomplete="list" aria-haspopup="listbox" hx-get="/mock/typeahead" hx-trigger="keyup changed delay:300ms[this.value.trim().length>0]" hx-target="#hm-ss-results" hx-params="q">
  <div id="hm-ss-results" role="listbox" aria-label="Suggestions" class="search-select-results">
    <div class="search-select-prompt" role="option" aria-disabled="true">Type to search — rows share one anatomy; media is optional</div>
  </div>
</div>
```

## Server exchange

When the client affordance finishes, htmx issues **this** request. Return the **response fragment** in the table (usually HTML, not JSON). Dazzle often implements these from the app model; a standalone HTMX4 app implements them explicitly.

> **Do not reimplement the gallery.** Flash toasts (e.g. confirm’s > “Deleted (demo).”), `/mock/*` paths, and other static-site > scaffolding are **demo-only** (`MOCK_HTMX` in `site/build_site.py`). > They are not Hyperpart surface and not a product API. If you are > stuck making a toast or mock URL work, stop — implement the > exchange row below instead. See AGENTS.md › *Gallery demos are not > the product API*.

| Request | Trigger | Response fragment | Swap | Envelope | States |
|---|---|---|---|---|---|
| `GET /app/fragments/search?source={source}&q=` | keyup on the combobox, debounced (`delay:{n}ms`) | HTML fragment: zero-or-more `.dz-search-result-row` options (fixed anatomy: optional media + name + optional secondary; each row hx-gets the select endpoint) OR one `.dz-search-result-empty` prompt — never JSON | innerHTML into the listbox | `body_only` | prompt/min-chars results empty error |
| `GET /app/fragments/select?source={source}&id={id}` | click / activate on a result row | confirm fragment replacing the listbox (`dz-select-result-confirm`) and server-side fill of the hidden FK (and usually the typeahead label via OOB) | innerHTML (listbox) + OOB for hidden/input as needed | `body_only` | selected |

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

## Swap contract

Agent-visible HTMX topology (ADR-0054 / decision 0012). **Exchange envelope** = what the response may re-emit relative to the persistent slot (`body_only` | `outer` | `none` | `host_owned` | `document`). Dual-lock validates part markup only — not this envelope. Stem: `stems/morph-safe-hypermedia.md`.

Gallery mocks may approximate morph with `innerHTML` — production follows the swap column in **Server exchange**.

### Exchanges (swap · envelope)

- `GET /app/fragments/search?source={source}&q=` → innerHTML into the listbox · **envelope=`body_only`**
- `GET /app/fragments/select?source={source}&id={id}` → innerHTML (listbox) + OOB for hidden/input as needed · **envelope=`body_only`**

### Replace / other HTML swap

- `GET /app/fragments/search?source={source}&q=` → body_only
- `GET /app/fragments/select?source={source}&id={id}` → body_only

### Envelope rules

- **`body_only`** — innerHTML / innerMorph into a slot; response is interior only (no re-wrap of slot id / nested `data-dz-region`).
- **`outer`** — outerHTML / outerMorph; response may carry identity.
- **`none`** — no HTML swap (JSON/204/bytes; client or OOB companion).
- **`host_owned`** — swap target/mode chosen by the host button's `hx-target` / `hx-swap` (part does not fix the envelope).
- **`document`** — full navigation / document load (not a fragment).
- Slot owns stable `id` / domain keys; state in DOM, not Alpine.

### Envelope response examples

What the **server returns** for each exchange. Match the **exchange envelope**; dual-lock still applies to interior markup.

#### `GET /app/fragments/search?source={source}&q=` · envelope=`body_only`

Correct response for body_only into .dz-search-results (innerHTML / innerMorph). Wrong: re-wrapping the slot.

**Do — correct response body**

```html
<!-- envelope=body_only → results list rows / empty prompt -->
<div class="dz-search-result-row" role="option">
  <div class="dz-search-result-name">Acme Ltd</div>
  <div class="dz-search-result-secondary">Co. 123</div>
</div>
```

**Don’t — violates `body_only`**

```html
<!-- WRONG: entire search field + listbox chrome -->
<div class="dz-search-box" data-dz-search-box id="slot">
  <input type="search" />
  <div>…results…</div>
</div>
```

#### `GET /app/fragments/select?source={source}&id={id}` · envelope=`body_only`

Correct response for body_only into .dz-search-results (innerHTML / innerMorph). Wrong: re-wrapping the slot.

**Do — correct response body**

```html
<!-- envelope=body_only → results list rows / empty prompt -->
<div class="dz-search-result-row" role="option">
  <div class="dz-search-result-name">Acme Ltd</div>
  <div class="dz-search-result-secondary">Co. 123</div>
</div>
```

**Don’t — violates `body_only`**

```html
<!-- WRONG: entire search field + listbox chrome -->
<div class="dz-search-box" data-dz-search-box id="slot">
  <input type="search" />
  <div>…results…</div>
</div>
```

## How to use it

### Seams

- shell: hidden FK + typeahead input + listbox panel (`data-dz-widget=search_select`)
- data-dz-blur-grace-ms (default 200) — blur→close delay so row clicks land; data-dz-confirm-hold-ms (default 1500, alias confirm-dwell-ms) — auto-dismiss hold after .dz-select-result-confirm paints
- search exchange returns N× fixed result-row fragments (or `.dz-search-result-empty`) — map domain into name / secondary / optional media (omit media for text-only rows)
- each row carries its own hx-get to the select exchange
- select exchange: confirm line (+ OOB hidden FK / label) — never invent a selected id client-side; typing clears a stale FK
- hx-trigger debounce + min-length filter; controller restores the prompt on empty/whitespace (do not hx-get q=)
- name=q on the typeahead (form=hm-detached-q so leftover is not posted; form="" is invalid HTML, cycle 2140) so leftover query reaches the search exchange — mock must filter; leftover zzz must not invent Aurora (cycle 2138)

### Do / Don't

| Do | Don't |
|---|---|
| map any record to SearchResultRow (id, name, secondary?, media_html?) and render_result_row | build a bespoke listbox DOM per entity or return JSON for the client to paint |
| set data-dz-confirm-hold-ms when the confirm line is user-facing | rely on blur grace alone to show select feedback |
| swap the panel with a confirmation fragment that fills the hidden FK server-side | copy the visible label into a hidden field from client JS |
| stop empty exchanges and restore the coaching prompt; leftover non-match returns empty | GET q= / load-seed / leftover zzz /mock/typeahead and invent Aurora rows |

### Pitfalls

- empty / whitespace query must not hx-get a canned hit list
- leftover typed query must not invent the canned Aurora list (name=q + mock filter; same class as command leftover 2130)
- clear after a hit must restore the prompt — do not leave stale Aurora rows
- blur grace is NOT confirm hold — without confirm-hold-ms the select feedback is hidden as soon as focus leaves (~200ms)
- form posts the hidden input, never the visible text (typeahead input clears a stale FK; required uses setCustomValidity)
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
