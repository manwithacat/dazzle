# Badge (`badge`)

Colour + icon + text — status never relies on colour alone (WCAG 1.4.1).

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<div class="hm-demo-row">
  <span class="badge" data-tone="success"><span class="badge-icon"><svg class="icon" aria-hidden="true"><use href="#i-circle-check"/></svg></span>Approved</span>
  <span class="badge" data-tone="warning"><span class="badge-icon"><svg class="icon" aria-hidden="true"><use href="#i-triangle-alert"/></svg></span>Pending</span>
  <span class="badge" data-tone="destructive"><span class="badge-icon"><svg class="icon" aria-hidden="true"><use href="#i-circle-x"/></svg></span>Rejected</span>
  <span class="badge" data-tone="neutral">Draft</span>
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

### `contracts/badge.py`

- **Required root:** `.dz-badge` (part `badge`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-badge` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: badge — status chip (tone/variant + optional icon).

Dual-lock unit is the chip root. Icon markup and tone attrs are host-owned;
gallery uses ``data-dz-tone``; Dazzle ``Badge`` primitive uses variant BEM
modifiers. Class ``.dz-badge`` is the stable cross-path selector.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="badge",
    root=".dz-badge",
    nodes=(Node(".dz-badge", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/badge.py`
