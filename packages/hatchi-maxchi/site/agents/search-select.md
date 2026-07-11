# Search select (`search-select`)

The FK typeahead: a debounced combobox whose results panel opens on focus and closes on blur — state is one aria-expanded attribute; selection is an htmx exchange per row.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<div class="search-select hm-measure" data-widget="search_select">
  <input type="hidden" name="company" id="hm-ss-field" value="">
  <input type="text" id="hm-ss-input" class="search-select-input" placeholder="Search companies…" autocomplete="off" role="combobox" aria-expanded="false" aria-controls="hm-ss-results" aria-autocomplete="list" aria-haspopup="listbox" hx-get="/mock/typeahead" hx-trigger="keyup changed delay:300ms" hx-target="#hm-ss-results" hx-params="q">
  <div id="hm-ss-results" role="listbox" aria-label="Company suggestions" class="search-select-results">
    <div class="search-select-prompt" role="option" aria-disabled="true">Type at least 3 characters to search...</div>
  </div>
</div>
```

## Server exchange

After the client affordance runs, htmx issues this request. Return the response fragment (not gallery mock toasts).

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `GET /app/fragments/search?source={source}&q=` | keyup on the combobox, debounced (`delay:{n}ms`) | result rows — each a `dz-search-result-row` div carrying its own hx-get to the select endpoint — or the `dz-search-result-empty` prompt | innerHTML | — |
| `GET /app/fragments/select?source={source}&id={id}` | a click on a result row | the `dz-select-result-confirm` line replacing the panel contents (the hidden FK input is set alongside) | innerHTML | — |

## How to use it

### Seams

- visible typeahead text is NOT the submit value — a hidden FK input is
- each result row carries its own hx-get to a select endpoint

### Do / Don't

| Do | Don't |
|---|---|
| swap the panel with a confirmation fragment that fills the hidden FK server-side | copy the visible label into a hidden field from client JS |

### Pitfalls

- 200ms blur grace — result rows are htmx affordances; the click must land first
- form posts the hidden input, never the visible text

### Keyboard / AT

- aria-expanded flips on focusin/focusout for the results panel
- result rows are activatable links/buttons inside the panel

### Related parts

- `field` — agents/field.md
- `search-box` — agents/search-box.md

## DOM contract

CI stop-ship (`tests/test_contracts.py`). Do not invent attrs or response shapes outside these modules.

### `contracts/search_select.py`

- **Required root:** `[data-dz-widget="search_select"]` (part `search-select`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-widget="search_select"]` | `—` | — |

#### Module source

```python
"""HYPERPART: search-select — typeahead open/close + hidden FK submit."""

from __future__ import annotations

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="search-select",
    root='[data-dz-widget="search_select"]',
    nodes=(Node('[data-dz-widget="search_select"]', attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

State-in-DOM: dz-search-select.js flips aria-expanded on focusin/focusout (200ms blur grace — result rows are htmx affordances, so the click must land before the panel hides) and CSS hides the panel off the attribute. Each result row carries its own hx-get to a select endpoint that swaps the panel with a confirmation and fills the hidden FK input server-side. The form posts the hidden input, never the visible text.

## Source files

- `controllers/dz-search-select.js`
