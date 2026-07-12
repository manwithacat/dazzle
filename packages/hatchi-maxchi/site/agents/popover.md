# Popover (`popover`)

Disclosure popover (`<details>`) — free-content panel; body can lazy-load via htmx. Not a focus-trapped/positioned popover.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<details class="popover">
  <summary class="button" data-variant="outline">Details</summary>
  <div class="popover__panel">
    <div class="hm-demo-title">Dimensions</div>
    <p class="hm-demo-muted">Filters, previews, quick forms.</p>
  </div>
</details>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

### Seams

- `details.dz-popover` + summary + `.dz-popover__panel`
- data-dz-dismiss / data-dz-dismiss-ms — spatial vs temporal (stem overlay-light-dismiss)
- shared controller with menu (dz-details-light-dismiss.js)

### Do / Don't

| Do | Don't |
|---|---|
| spatial Esc+outside by default; opt-in data-dz-dismiss-ms for glance only | auto-close content the user is still editing |
| data-dz-dismiss=none when the host owns dismiss | assume a global timer on every popover instance |

### Pitfalls

- not a modal dialog — no focus trap; use dialog when you need modal
- not a tooltip — do not put a default timeout on form/filter popovers
- native details do not Esc/outside-dismiss without the controller
- do not light-dismiss accordion/tree (in-flow structure)

### Keyboard / AT

- Keyboard: Enter/Space on summary; Escape dismisses (if esc enabled)
- Touch: pointer outside dismisses (if outside enabled)

### Related parts

- `button` — agents/button.md

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/popover.py`

- **Required root:** `details.dz-popover, .dz-popover` (part `popover`)

| Node | Attr | Constraint |
|---|---|---|
| `details.dz-popover, .dz-popover` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: popover — details free-content panel (light-dismiss enhanced).

Optional instance attrs (controller reads; not required by DomContract):
  data-dz-dismiss, data-dz-dismiss-ms — see stems/overlay-light-dismiss.md
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="popover",
    root="details.dz-popover, .dz-popover",
    nodes=(Node("details.dz-popover, .dz-popover", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

**Pick:** free content under a trigger — not an action list (menu). Not a tooltip (no auto-timeout by default). Light-dismiss: spatial Esc+outside; optional data-dz-dismiss-ms for glance previews only. data-dz-dismiss=none for native toggle only. Controller dz-details-light-dismiss.js.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/popover.py`
- `controllers/dz-details-light-dismiss.js`
