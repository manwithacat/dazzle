# Search box (`search-box`)

The FTS search region: a debounced search input, an aria-live results panel, and a coaching line that hides — via pure CSS — the moment the user types.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="search-box-region hm-measure" data-search-box>
  <div class="search-box-input-row">
    <label for="hm-search-input" class="visually-hidden">Search records</label>
    <input id="hm-search-input" type="search" name="q" class="search-box-input" placeholder="Search records…" autocomplete="off" hx-get="/mock/search" hx-trigger="input changed delay:250ms[this.value.trim().length>0], search[this.value.trim().length>0]" hx-target="#hm-search-results" hx-swap="innerHTML">
  </div>
  <div id="hm-search-results" class="search-box-results" role="region" aria-live="polite">
    <div class="search-box-empty">Type a title or keyword</div>
  </div>
</div>
```

## Server exchange

When the client affordance finishes, htmx issues **this** request. Return the **response fragment** in the table (usually HTML, not JSON). Dazzle often implements these from the app model; a standalone HTMX4 app implements them explicitly.

> **Do not reimplement the gallery.** Flash toasts (e.g. confirm’s > “Deleted (demo).”), `/mock/*` paths, and other static-site > scaffolding are **demo-only** (`MOCK_HTMX` in `site/build_site.py`). > They are not Hyperpart surface and not a product API. If you are > stuck making a toast or mock URL work, stop — implement the > exchange row below instead. See AGENTS.md › *Gallery demos are not > the product API*.

| Request | Trigger | Response fragment | Swap | Envelope | States |
|---|---|---|---|---|---|
| `GET /app/fts/{entity}?q=&html=1` | the input, debounced 250ms when q is non-empty (native `search` / Esc/clear restores coaching — no GET) | the results fragment: a `dz-search-box-result-count` line + a `dz-search-box-result-list` of linked rows with `<mark>`-highlighted snippets; zero hits return the `--no-results` variant of the empty line (which the CSS toggle deliberately never hides). Empty queries aren't sent (min length 1) | innerHTML | `body_only` | — |

## Swap contract

Agent-visible HTMX topology (ADR-0054 / decision 0012). **Exchange envelope** = what the response may re-emit relative to the persistent slot (`body_only` | `outer` | `none` | `host_owned` | `document`). Dual-lock validates part markup only — not this envelope. Stem: `stems/morph-safe-hypermedia.md`.

Gallery mocks may approximate morph with `innerHTML` — production follows the swap column in **Server exchange**.

### Exchanges (swap · envelope)

- `GET /app/fts/{entity}?q=&html=1` → innerHTML · **envelope=`body_only`**

### Replace / other HTML swap

- `GET /app/fts/{entity}?q=&html=1` → body_only

### Envelope rules

- **`body_only`** — innerHTML / innerMorph into a slot; response is interior only (no re-wrap of slot id / nested `data-dz-region`).
- **`outer`** — outerHTML / outerMorph; response may carry identity.
- **`none`** — no HTML swap (JSON/204/bytes; client or OOB companion).
- **`host_owned`** — swap target/mode chosen by the host button's `hx-target` / `hx-swap` (part does not fix the envelope).
- **`document`** — full navigation / document load (not a fragment).
- Slot owns stable `id` / domain keys; state in DOM, not Alpine.

### Envelope response examples

What the **server returns** for each exchange. Match the **exchange envelope**; dual-lock still applies to interior markup.

#### `GET /app/fts/{entity}?q=&html=1` · envelope=`body_only`

Correct response for body_only into .dz-search-box-results (innerHTML / innerMorph). Wrong: re-wrapping the slot.

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

- native type=search is the query; [data-dz-search-box] owns the results slot
- hx-trigger debounce + min-length filter; controller restores coaching on clear

### Do / Don't

| Do | Don't |
|---|---|
| stop empty exchanges and restore the coaching empty line | GET empty q= and let /mock/search invent Aurora/Beacon hits |
| filter leftover q= so zzz is empty and substation still hits | path-only /mock/search that ignores q= and invents Aurora |

### Pitfalls

- empty / whitespace query must not hx-get a silent or fake result list
- clear after a hit must restore coaching — do not leave stale Aurora rows
- leftover typed q (zzz) must not invent Aurora — /mock/search filters

### Keyboard / AT

- type=search keeps Esc/clear and the native search event
- results region stays aria-live=polite; coaching is not a live hit list

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/search_box.py`

- **Required root:** `[data-dz-search-box]` (part `search-box`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-search-box]` | `data-dz-search-box` | present (any value) |

#### Ingestion model `SearchBox`

| Field | Type | Required |
|---|---|---|
| `name` | `string` | no |
| `label` | `string` | no |
| `placeholder` | `string` | no |
| `coaching_message` | `string` | no |
| `endpoint` | `string` | no |
| `results_html` | `string` | no |

#### Exemplar `render()`

```python
def render(s: SearchBox) -> str:
    """Model → search-box region."""
    results_id = f"dz-search-results-{html.escape(s.name, quote=True)}"
    endpoint = html.escape(s.endpoint, quote=True)
    placeholder = html.escape(s.placeholder or "Search…", quote=True)
    label_text = html.escape(s.label or s.placeholder or "Search")
    coaching = html.escape(s.coaching_message or "Type a title or keyword")
    results_body = s.results_html.strip() or (f'<div class="dz-search-box-empty">{coaching}</div>')
    return (
        f'<div class="dz-search-box-region" data-dz-search-box>'
        f'<div class="dz-search-box-input-row">'
        f'<label for="{results_id}-input" class="visually-hidden">{label_text}</label>'
        f'<input id="{results_id}-input" type="search" name="q" '
        f'class="dz-search-box-input" placeholder="{placeholder}" '
        f'autocomplete="off" '
        f'hx-get="{endpoint}" '
        f'hx-trigger="input changed delay:250ms[this.value.trim().length>0], '
        f'search[this.value.trim().length>0]" '
        f'hx-target="#{results_id}" '
        f'hx-swap="innerHTML">'
        f"</div>"
        f'<div id="{results_id}" class="dz-search-box-results" '
        f'role="region" aria-live="polite">'
        f"{results_body}"
        f"</div>"
        f"</div>"
    )
```

## Notes

Dual-lock root is data-dz-search-box (contracts/search_box.py). The 250ms debounce is hx-trigger with a min-length filter; dz-search-box.js still blocks empty/whitespace queries (gallery mock ignores the filter) and restores the coaching line so clear does not swap a fake hit list. The input posts name=q so leftover text reaches /mock/search — leftover zzz is empty, not canned Aurora (cycle 2148). Results land in an aria-live="polite" region; the coaching line is hidden by :has(input:not(:placeholder-shown)) until a swap. Results are server-rendered dz-search-box-result rows (title + per-field <mark>-highlighted snippets, count line above); the no-results state reuses dz-search-box-empty with the --no-results modifier.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/search_box.py`
- `controllers/dz-search-box.js`
