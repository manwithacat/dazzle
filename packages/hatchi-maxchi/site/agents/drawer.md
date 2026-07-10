# Drawer (`drawer`)

Edge-anchored panel on the native <dialog> — a drawer with a modal's guarantees (focus trap, inert background, Esc, backdrop). Built on the dialog: shares its opener, adds a side + slide. No drawer-specific JS.

## Partial (copy-paste; the live demo renders this exact string)

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<button class="button" data-variant="outline" data-dialog-open="hm-drawer-demo">Open filters</button>
<dialog class="drawer" id="hm-drawer-demo" data-side="right" aria-labelledby="hm-drawer-demo-title" closedby="any">
  <form method="dialog">
    <div class="drawer__header">
      <h2 class="drawer__title" id="hm-drawer-demo-title">Filters</h2>
      <button type="submit" class="drawer__close" aria-label="Close drawer"><svg class="icon" aria-hidden="true"><use href="#i-x"/></svg></button>
    </div>
    <div class="drawer__body" tabindex="0" aria-label="Drawer content">
      <p>Drawer content scrolls independently of the page — filters, a record preview, or a quick form live here.</p>
    </div>
    <div class="drawer__footer"><button type="submit" class="button" data-variant="ghost">Reset</button><button type="submit" class="button" data-variant="primary" value="apply">Apply</button></div>
  </form>
</dialog>
<button class="button" data-variant="outline" hx-get="/mock/drawer/detail" hx-target="#hm-drawer-lazy-body" hx-swap="innerHTML" data-dialog-open="hm-drawer-lazy">Open record</button>
<dialog class="drawer" id="hm-drawer-lazy" data-width="md" closedby="any" aria-label="Record detail">
  <header class="drawer__header">
    <h2 class="drawer__title">Record detail</h2>
    <form method="dialog"><button type="submit" class="drawer__close" aria-label="Close"><svg class="icon" aria-hidden="true"><use href="#i-x"/></svg></button></form>
  </header>
  <div id="hm-drawer-lazy-body" class="drawer__body">
    <p>Loading…</p>
  </div>
</dialog>
```

## Exchanges (the endpoint contract your server must satisfy)

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `GET /app/records/{id}?peek=1` | the opener button's click — the SAME click also fires the dz-dialog.js opener (`data-dz-dialog-open`), so the drawer shows while the body loads | the record's detail body HTML — swapped into the drawer's `dz-drawer__body` target | innerHTML | — |

## Guidance (prose; HTML from the registry notes field)

Opened by the shared <code>dz-dialog.js</code> (<code>[data-dz-dialog-open]</code>); close is native (method=dialog submit, Esc, backdrop). Anchor the edge with <code>data-dz-side=&quot;right|left&quot;</code>; the panel slides in via the native <code>@starting-style</code> transition, honouring <code>prefers-reduced-motion</code>. The second trigger shows the HYPERMEDIA drawer (the Dazzle row-peek contract): one button carries both an <code>hx-get</code> targeting the drawer body and <code>data-dz-dialog-open</code> — the exchange and the opener fire together. <code>data-dz-width=&quot;sm|md|lg|xl|full&quot;</code> picks a width preset on viewports that can afford it.
