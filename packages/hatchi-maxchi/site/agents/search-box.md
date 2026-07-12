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
    <input id="hm-search-input" type="search" name="q" class="search-box-input" placeholder="Search records…" autocomplete="off" hx-get="/mock/search" hx-trigger="input changed delay:250ms, search" hx-target="#hm-search-results" hx-swap="innerHTML">
  </div>
  <div id="hm-search-results" class="search-box-results" role="region" aria-live="polite">
    <div class="search-box-empty">Type a title or keyword</div>
  </div>
</div>
```

## Server exchange

When the client affordance finishes, htmx issues **this** request. Return the **response fragment** in the table (usually HTML, not JSON). Dazzle often implements these from the app model; a standalone HTMX4 app implements them explicitly.

> **Do not reimplement the gallery.** Flash toasts (e.g. confirm’s > “Deleted (demo).”), `/mock/*` paths, and other static-site > scaffolding are **demo-only** (`MOCK_HTMX` in `site/build_site.py`). > They are not Hyperpart surface and not a product API. If you are > stuck making a toast or mock URL work, stop — implement the > exchange row below instead. See AGENTS.md › *Gallery demos are not > the product API*.

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `GET /app/fts/{entity}?q=&html=1` | the input, debounced 250ms (and the native `search` event — Esc/clear on type=search) | the results fragment: a `dz-search-box-result-count` line + a `dz-search-box-result-list` of linked rows with `<mark>`-highlighted snippets; zero hits return the `--no-results` variant of the empty line (which the CSS toggle deliberately never hides). Empty queries aren't sent (min length 1) | innerHTML | — |

## Morph / swap

Stem: `stems/morph-safe-hypermedia.md` · decisions 0005–0007. Morph for **stable** surfaces; replacement for **disposable** fragments. Gallery mocks may approximate morph with `innerHTML` — production follows the swap column in **Server exchange**.

### Replace / `innerHTML` (reset OK)

- `GET /app/fts/{entity}?q=&html=1` → innerHTML

### Identity rules

- Morph participants need **stable** `id` / domain keys (not loop indexes).
- Carry selection/edit affordances in the **DOM** (checked, `data-*`, ARIA) — not Alpine/`x-data` or a JS array a morph would orphan.
- Mark third-party widgets as explicit islands / morph-skip boundaries.

## How to use it

No extended guidance authored yet — start from Copy this and the dependency chips.

### Seams

- copy the partial under Copy this; keep root class and data-* modifiers so the CSS/JS bundle matches
- implement Server exchange endpoints; return HTML fragments, not JSON
- satisfy the DOM contract tables (CI stop-ship)

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
        f'hx-trigger="input changed delay:250ms, search" '
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

Dual-lock root is data-dz-search-box (contracts/search_box.py). No JS beyond htmx: the 250ms debounce is hx-trigger="input changed delay:250ms, search", the results land in an aria-live="polite" region, and the coaching line is hidden by :has(input:not(:placeholder-shown)) — no client state. Results are server-rendered dz-search-box-result rows (title + per-field <mark>-highlighted snippets, count line above); the no-results state reuses dz-search-box-empty with the --no-results modifier.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/search_box.py`
