# Search box (`search-box`)

The FTS search region: a debounced search input, an aria-live results panel, and a coaching line that hides — via pure CSS — the moment the user types.

## Partial (copy-paste; the live demo renders this exact string)

```html
<div class="search-box-region hm-measure">
  <div class="search-box-input-row">
    <label for="hm-search-input" class="visually-hidden">Search records</label>
    <input id="hm-search-input" type="search" name="q" class="search-box-input" placeholder="Search records…" autocomplete="off" hx-get="/mock/search" hx-trigger="input changed delay:250ms, search" hx-target="#hm-search-results" hx-swap="innerHTML">
  </div>
  <div id="hm-search-results" class="search-box-results" role="region" aria-live="polite">
    <div class="search-box-empty">Type a title or keyword</div>
  </div>
</div>
```

## Exchanges (the endpoint contract your server must satisfy)

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `GET /app/fts/{entity}?q=&html=1` | the input, debounced 250ms (and the native `search` event — Esc/clear on type=search) | the results fragment: a `dz-search-box-result-count` line + a `dz-search-box-result-list` of linked rows with `<mark>`-highlighted snippets; zero hits return the `--no-results` variant of the empty line (which the CSS toggle deliberately never hides). Empty queries aren't sent (min length 1) | innerHTML | — |

## Guidance (prose; HTML from the registry notes field)

No JS beyond htmx: the 250ms debounce is <code>hx-trigger=&quot;input changed delay:250ms, search&quot;</code>, the results land in an <code>aria-live=&quot;polite&quot;</code> region, and the coaching line is hidden by <code>:has(input:not(:placeholder-shown))</code> — no client state. Results are server-rendered <code>dz-search-box-result</code> rows (title + per-field <code>&lt;mark&gt;</code>-highlighted snippets, count line above); the no-results state reuses <code>dz-search-box-empty</code> with the <code>--no-results</code> modifier.
