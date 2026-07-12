# Menu (`menu`)

Disclosure menu (`<details>`) — no JS for open state. A disclosure, not a full ARIA menu: no roving tabindex or typeahead.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<details class="menu">
  <summary class="button" data-variant="outline">Actions</summary>
  <div class="menu__panel">
    <button type="button" class="menu__item"><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-pencil"/></svg> Edit</button>
    <button type="button" class="menu__item"><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-copy"/></svg> Duplicate</button>
    <hr class="menu__separator">
    <button type="button" class="menu__item" data-tone="destructive"><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-trash-2"/></svg> Delete</button>
  </div>
</details>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

### Seams

- `details.dz-menu` + `summary` (usually `.dz-button`) + `.dz-menu__panel`
- disclosure chevron is presentation on summary::after — not label text
- light-dismiss: Esc + pointerdown outside (dz-details-light-dismiss.js)
- pick-a-surface: local actions from one button → menu (not menubar / navigation-menu)

### Do / Don't

| Do | Don't |
|---|---|
| label text only + CSS chevron that rotates when [open] | Actions ▾ as a single text string for the expand signal |
| one Actions control with an item list on a host (toolbar/row) | a horizontal multi-trigger strip (that is menubar or navigation-menu) |
| Esc + outside abandon for transient overlays (touch: outside) | require re-tapping the summary as the only way to cancel |

### Pitfalls

- do not bake ▾/▼ into the summary text — house disclosure chrome is CSS/SVG
- not a full ARIA menu (no roving tabindex/typeahead) — do not invent role=menu half-contracts
- do not use menu for top product IA or File/Edit strips — wrong job
- native details do not Esc/outside-dismiss — ship the light-dismiss controller

### Keyboard / AT

- details/summary carry expand; chevron is decorative
- Keyboard: Enter/Space opens; Escape light-dismisses
- Touch: tap outside to abandon (no Esc key)

### Related parts

- `button` — agents/button.md

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/menu.py`

- **Required root:** `details.dz-menu, .dz-menu` (part `menu`)

| Node | Attr | Constraint |
|---|---|---|
| `details.dz-menu, .dz-menu` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: menu — details disclosure root (light-dismiss enhanced)."""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="menu",
    root="details.dz-menu, .dz-menu",
    nodes=(Node("details.dz-menu, .dz-menu", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

**Pick:** local actions from one control — not app File/Edit chrome (menubar) and not product/site go-to nav (navigation-menu). See docs/agent/pick-a-surface.md › Menus / panels / chrome strips. Trigger label is plain text; open-panel signal is CSS ::after chevron. Light-dismiss (stem overlay-light-dismiss): Esc + outside pointer via dz-details-light-dismiss.js — native details alone do not. Honest disclosure, not ARIA menu with roving tabindex.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/menu.py`
- `controllers/dz-details-light-dismiss.js`
