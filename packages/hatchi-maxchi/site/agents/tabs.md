# Tabs (`tabs`)

A lazy tab strip — an honest link-strip (buttons + aria-current, no unkept role=tablist). Each panel hx-gets its content the first time it is shown.

## Partial (copy-paste; the live demo renders this exact string)

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="tabs">
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

## Exchanges (the endpoint contract your server must satisfy)

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `GET /app/{region}/{tab}` | a panel, the first time it is revealed (`intersect once`); an eager panel on `load` | the panel's content fragment (rows, a form, a chart — whatever the tab shows) | innerHTML of the panel itself (no hx-target) | loading populated error |

## Guidance (structured)

### Seams

- tabs are buttons with aria-current; panels toggle visibility scoped to .dz-tabs
- hidden panels may carry intersect once lazy-load; first panel is eager

### Pitfalls

- no role=tablist without the roving-tabindex/arrow-key contract — honest buttons
- panel reveal is scoped to THIS root so multiple tab sets coexist

### Keyboard / AT

- Tab reaches each tab button; activation is Enter/Space (button default)
- lazy panels load on first reveal via intersect once

### Do / Don't

| Do | Don't |
|---|---|
| mark the active tab with aria-current and show its panel | fake tabs with links that reload the whole page for every panel |

### Composes with

- `button` (agents/button.md)

## Guidance (prose; HTML from the registry notes field)

The tabs are <code>&lt;button&gt;</code>s with <code>aria-current</code> — no <code>role=tablist</code> without the roving-tabindex/arrow-key contract to back it (honest, like the menu). <code>dz-tabs.js</code> reveals the chosen panel scoped to its <code>.dz-tabs</code> root; showing a hidden panel triggers its <code>intersect once</code> lazy load. The first panel is eager (content inline).

## Controller files

- `controllers/dz-tabs.js`
