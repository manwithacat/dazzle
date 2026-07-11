# Pagination (`pagination`)

The footer beneath a data table — a summary and page buttons. Each button hx-gets a page into the list body (an Exchange, not a widget).

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

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

When the client affordance finishes, htmx issues **this** request. Return the HTML fragment described (not gallery mock toasts). Dazzle often implements these from the app model; a standalone HTMX4 app implements them explicitly.

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `GET /app/{region}?page={n}&page_size={size}` | a page button, on click | the list body fragment for page n — the rows the region renders, with the current-page button marked `is-current` + `aria-current='page'` | innerMorph of the region's body (`#{region}-body`) | loading populated error |

## Notes

Each page button carries its own hx-get; here a mock htmx swaps a canned page into #hm-pag-body. In Dazzle the button hits the region endpoint (?page=N&page_size=…) and the server returns the repainted list body (via innerMorph) plus the moved is-current marker.
