# Item (`item`)

Generic list row — optional media, title, description, trailing actions. Compose into lists, pickers, and search results.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="item-group hm-measure-lg">
  <div class="item" data-item data-variant="outline">
    <span class="item__media" aria-hidden="true">MR</span>
    <div class="item__content">
      <div class="item__title">Maya Reyes</div>
      <div class="item__description">Operations · North grid</div>
    </div>
    <div class="item__actions"><button type="button" class="button" data-variant="ghost" data-size="sm">View</button></div>
  </div>
  <div class="item" data-item data-variant="outline">
    <span class="item__media" aria-hidden="true">JK</span>
    <div class="item__content">
      <div class="item__title">Jordan Kim</div>
      <div class="item__description">Support · Escalations</div>
    </div>
    <div class="item__actions"><button type="button" class="button" data-variant="ghost" data-size="sm">View</button></div>
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

### `contracts/item.py`

- **Required root:** `.dz-item` (part `item`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-item` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: item — generic list row (media + title + description + actions).

Dual-lock unit is the item root. Media, content, trailing actions, and
``data-dz-variant`` are host-owned. Class ``.dz-item`` is the stable substrate
root (gallery CSS; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="item",
    root=".dz-item",
    nodes=(Node(".dz-item", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

PLACEHOLDER — shadcn parity (HMC-033). Flex row anatomy only; no controller. Actions stop at product buttons. Dual-lock root .dz-item (HMC-145).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/item.py`
