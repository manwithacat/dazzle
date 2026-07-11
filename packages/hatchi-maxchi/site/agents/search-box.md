# Search box (`search-box`)

The FTS search region: a debounced search input, an aria-live results panel, and a coaching line that hides — via pure CSS — the moment the user types.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

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

## Server exchange

When the client affordance finishes, htmx issues **this** request. Return the HTML fragment described (not gallery mock toasts). Dazzle often implements these from the app model; a standalone HTMX4 app implements them explicitly.

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `GET /app/fts/{entity}?q=&html=1` | the input, debounced 250ms (and the native `search` event — Esc/clear on type=search) | the results fragment: a `dz-search-box-result-count` line + a `dz-search-box-result-list` of linked rows with `<mark>`-highlighted snippets; zero hits return the `--no-results` variant of the empty line (which the CSS toggle deliberately never hides). Empty queries aren't sent (min length 1) | innerHTML | — |

## How to use it

No extended guidance authored yet — start from Copy this and the dependency chips.

### Seams

- copy the partial under Copy this; keep root class and data-* modifiers so the CSS/JS bundle matches
- implement Server exchange endpoints; return HTML fragments, not JSON
- no typed contracts/ module yet — the partial is the surface of record

## DOM contract

No typed dual-lock module in `contracts/` for this part yet. Treat **Copy this** as the required surface — preserve root class and `data-*` modifiers. Author `contracts/<part>.py` when CI should stop-ship attribute drift (`contracts/AUTHORING.md`).

## Notes

No JS beyond htmx: the 250ms debounce is hx-trigger="input changed delay:250ms, search", the results land in an aria-live="polite" region, and the coaching line is hidden by :has(input:not(:placeholder-shown)) — no client state. Results are server-rendered dz-search-box-result rows (title + per-field <mark>-highlighted snippets, count line above); the no-results state reuses dz-search-box-empty with the --no-results modifier.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
