# Pagination (`pagination`)

The footer beneath a data table — a summary and page buttons. Each button hx-gets a page into the list body (an Exchange, not a widget).

## Partial (copy-paste; the live demo renders this exact string)

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

## Exchanges (the endpoint contract your server must satisfy)

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `GET /app/{region}?page={n}&page_size={size}` | a page button, on click | the list body fragment for page n — the rows the region renders, with the current-page button marked `is-current` + `aria-current='page'` | innerMorph of the region's body (`#{region}-body`) | loading populated error |

## Guidance (prose; HTML from the registry notes field)

Each page button carries its own <code>hx-get</code>; here a mock htmx swaps a canned page into <code>#hm-pag-body</code>. In Dazzle the button hits the region endpoint (<code>?page=N&amp;page_size=…</code>) and the server returns the repainted list body (via <code>innerMorph</code>) plus the moved <code>is-current</code> marker.
