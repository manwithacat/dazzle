# Pagination (`pagination`)

The footer beneath a data table — a summary and page buttons. Each button hx-gets a page into the list body (an Exchange, not a widget).

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="hm-stack hm-measure-lg">
  <div id="hm-pag-body" class="hm-pag-list">
    <div class="hm-pag-row">INV-001 · Acme</div>
    <div class="hm-pag-row">INV-002 · Globex</div>
    <div class="hm-pag-row">INV-003 · Initech</div>
  </div>
  <nav class="pagination" aria-label="Pagination">
    <span class="pagination-summary">42 rows</span>
    <div class="pagination-pages"><button class="pagination-page" disabled aria-label="Previous page">‹</button><button class="pagination-page is-current" aria-current="page">1</button><button class="pagination-page" hx-get="/mock/pagination/2" hx-target="#hm-pag-body" hx-swap="innerHTML">2</button><button class="pagination-page" hx-get="/mock/pagination/3" hx-target="#hm-pag-body" hx-swap="innerHTML">3</button><span class="pagination-ellipsis" aria-hidden="true">…</span><button class="pagination-page" hx-get="/mock/pagination/9" hx-target="#hm-pag-body" hx-swap="innerHTML">9</button><button class="pagination-page" hx-get="/mock/pagination/2" hx-target="#hm-pag-body" hx-swap="innerHTML" aria-label="Next page">›</button></div>
  </nav>
</div>
```

## Server exchange

When the client affordance finishes, htmx issues **this** request. Return the **response fragment** in the table (usually HTML, not JSON). Dazzle often implements these from the app model; a standalone HTMX4 app implements them explicitly.

> **Do not reimplement the gallery.** Flash toasts (e.g. confirm’s > “Deleted (demo).”), `/mock/*` paths, and other static-site > scaffolding are **demo-only** (`MOCK_HTMX` in `site/build_site.py`). > They are not Hyperpart surface and not a product API. If you are > stuck making a toast or mock URL work, stop — implement the > exchange row below instead. See AGENTS.md › *Gallery demos are not > the product API*.

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `GET /app/{region}?page={n}&page_size={size}` | a page button, on click | the list body fragment for page n — the rows the region renders, with the current-page button marked `is-current` + `aria-current='page'` | innerMorph of the region's body (`#{region}-body`) | loading populated error |

## How to use it

No extended guidance authored yet — start from Copy this and the dependency chips.

### Seams

- copy the partial under Copy this; keep root class and data-* modifiers so the CSS/JS bundle matches
- implement Server exchange endpoints; return HTML fragments, not JSON
- no typed contracts/ module yet — the partial is the surface of record

## DOM contract

No typed dual-lock module in `contracts/` for this part yet. Treat **Copy this** as the required surface — preserve root class and `data-*` modifiers. Author `contracts/<part>.py` when CI should stop-ship attribute drift (`contracts/AUTHORING.md`).

## Notes

Each page button carries its own hx-get; here a mock htmx swaps a canned page into #hm-pag-body. In Dazzle the button hits the region endpoint (?page=N&page_size=…) and the server returns the repainted list body (via innerMorph) plus the moved is-current marker.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
