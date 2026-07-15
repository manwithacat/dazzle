# Alert (`alert`)

Tone-wash surfaces — an identity layer shadcn has no vocabulary for.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="alert hm-measure-lg" data-tone="warning" role="alert">
  <span class="alert__icon"><svg class="icon" aria-hidden="true"><use href="#i-triangle-alert"/></svg></span>
  <div class="alert__body">
    <div class="alert__title">Payment method expiring</div>
    <div class="alert__description">Your card ending 4242 expires next month.</div>
  </div>
</div>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

No extended guidance authored yet — start from Copy this and the dependency chips.

### Seams

- copy the partial under Copy this; keep root class and data-* modifiers so the CSS/JS bundle matches
- no Server exchange on this part — pure presentation or client chrome
- satisfy the DOM contract tables (CI stop-ship)

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/alert.py`

- **Required root:** `.dz-alert` (part `alert`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-alert` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: alert — tone-wash feedback surface.

Dual-lock unit is the alert root. Tone (``data-dz-tone``), icon, title, and
description are host-owned. Class ``.dz-alert`` is the stable substrate root
(gallery CSS; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="alert",
    root=".dz-alert",
    nodes=(Node(".dz-alert", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

Dual-lock root .dz-alert (HMC-140).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/alert.py`
