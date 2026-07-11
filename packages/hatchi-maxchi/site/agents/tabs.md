# Tabs (`tabs`)

A lazy tab strip — an honest link-strip (buttons + aria-current, no unkept role=tablist). Each panel hx-gets its content the first time it is shown.

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="tabs" data-tabs>
  <div class="tabs__list"><button class="tabs__tab" aria-current="true" data-tab-target="hm-tab-overview">Overview</button><button class="tabs__tab" data-tab-target="hm-tab-activity">Activity</button><button class="tabs__tab" data-tab-target="hm-tab-settings">Settings</button></div>
  <div id="hm-tab-overview" class="tabs__panel">
    <p class="hm-demo-muted">Active on the Pro plan, renewing 1 August.</p>
  </div>
  <div id="hm-tab-activity" class="tabs__panel" hidden hx-get="/mock/tabs/activity" hx-trigger="intersect once" hx-swap="innerHTML">
    <div class="tabs__loading"><svg class="icon" aria-hidden="true"><use href="#i-loader-circle"/></svg></div>
  </div>
  <div id="hm-tab-settings" class="tabs__panel" hidden hx-get="/mock/tabs/settings" hx-trigger="intersect once" hx-swap="innerHTML">
    <div class="tabs__loading"><svg class="icon" aria-hidden="true"><use href="#i-loader-circle"/></svg></div>
  </div>
</div>
```

## Server exchange

When the client affordance finishes, htmx issues **this** request. Return the HTML fragment described (not gallery mock toasts). Dazzle often implements these from the app model; a standalone HTMX4 app implements them explicitly.

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `GET /app/{region}/{tab}` | a panel, the first time it is revealed (`intersect once`); an eager panel on `load` | the panel's content fragment (rows, a form, a chart — whatever the tab shows) | innerHTML of the panel itself (no hx-target) | loading populated error |

## How to use it

### Seams

- tabs are buttons with aria-current; panels toggle visibility scoped to .dz-tabs
- hidden panels may carry intersect once lazy-load; first panel is eager

### Do / Don't

| Do | Don't |
|---|---|
| mark the active tab with aria-current and show its panel | fake tabs with links that reload the whole page for every panel |

### Pitfalls

- no role=tablist without the roving-tabindex/arrow-key contract — honest buttons
- panel reveal is scoped to THIS root so multiple tab sets coexist

### Keyboard / AT

- Tab reaches each tab button; activation is Enter/Space (button default)
- lazy panels load on first reveal via intersect once

### Related parts

- `button` — agents/button.md

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/tabs.py`

- **Required root:** `[data-dz-tabs]` (part `tabs`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-tabs]` | `—` | — |
| `[data-dz-tab-target]` | `data-dz-tab-target` | present (any value) |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: tabs — tablist root + panel targets."""


from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="tabs",
    root="[data-dz-tabs]",
    nodes=(
        Node("[data-dz-tabs]", attrs={}),
        Node("[data-dz-tab-target]", attrs={"data-dz-tab-target": Present()}),
    ),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

The tabs are <button>s with aria-current — no role=tablist without the roving-tabindex/arrow-key contract to back it (honest, like the menu). dz-tabs.js reveals the chosen panel scoped to its .dz-tabs root; showing a hidden panel triggers its intersect once lazy load. The first panel is eager (content inline).

## Source files

- `controllers/dz-tabs.js`
