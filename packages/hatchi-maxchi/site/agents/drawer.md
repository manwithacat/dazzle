# Drawer (`drawer`)

Edge-anchored panel on the native <dialog> — a drawer with a modal's guarantees (focus trap, inert background, Esc, backdrop). Built on the dialog: shares its opener, adds a side + slide. No drawer-specific JS.

> **Layer:** L1 surface · **Recipe:** `overlay-dialog` — modal / drawer overlay
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

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

## Server exchange

When the client affordance finishes, htmx issues **this** request. Return the **response fragment** in the table (usually HTML, not JSON). Dazzle often implements these from the app model; a standalone HTMX4 app implements them explicitly.

> **Do not reimplement the gallery.** Flash toasts (e.g. confirm’s > “Deleted (demo).”), `/mock/*` paths, and other static-site > scaffolding are **demo-only** (`MOCK_HTMX` in `site/build_site.py`). > They are not Hyperpart surface and not a product API. If you are > stuck making a toast or mock URL work, stop — implement the > exchange row below instead. See AGENTS.md › *Gallery demos are not > the product API*.

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `GET /app/records/{id}?peek=1` | the opener button's click — the SAME click also fires the dz-dialog.js opener (`data-dz-dialog-open`), so the drawer shows while the body loads | the record's detail body HTML — swapped into the drawer's `dz-drawer__body` target | innerHTML | — |

## Morph / swap

Stem: `stems/morph-safe-hypermedia.md` · decisions 0005–0007. Morph for **stable** surfaces; replacement for **disposable** fragments. Gallery mocks may approximate morph with `innerHTML` — production follows the swap column in **Server exchange**.

### Replace / `innerHTML` (reset OK)

- `GET /app/records/{id}?peek=1` → innerHTML

### Identity rules

- Morph participants need **stable** `id` / domain keys (not loop indexes).
- Carry selection/edit affordances in the **DOM** (checked, `data-*`, ARIA) — not Alpine/`x-data` or a JS array a morph would orphan.
- Mark third-party widgets as explicit islands / morph-skip boundaries.

## How to use it

No extended guidance authored yet — start from Copy this and the dependency chips.

### Seams

- copy the partial under Copy this; keep root class and data-* modifiers so the CSS/JS bundle matches
- implement Server exchange endpoints; return HTML fragments, not JSON
- no typed contracts/ module yet — the partial is the surface of record

## DOM contract

No typed dual-lock module in `contracts/` for this part yet. Treat **Copy this** as the required surface — preserve root class and `data-*` modifiers. Author `contracts/<part>.py` when CI should stop-ship attribute drift (`contracts/AUTHORING.md`).

## Notes

Opened by the shared dz-dialog.js ([data-dz-dialog-open]); close is native (method=dialog submit, Esc, backdrop). Anchor the edge with data-dz-side="right|left"; the panel slides in via the native @starting-style transition, honouring prefers-reduced-motion. The second trigger shows the HYPERMEDIA drawer (the Dazzle row-peek contract): one button carries both an hx-get targeting the drawer body and data-dz-dialog-open — the exchange and the opener fire together. data-dz-width="sm|md|lg|xl|full" picks a width preset on viewports that can afford it.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
