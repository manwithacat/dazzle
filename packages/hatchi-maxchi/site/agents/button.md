# Button (`button`)

Primary, outline, ghost, destructive — chromatic accent CTAs.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="hm-demo-row">
  <button class="button" data-variant="primary">Save changes</button>
  <button class="button" data-variant="outline">Cancel</button>
  <button class="button" data-variant="ghost">Learn more</button>
  <button class="button" data-variant="destructive">Delete</button>
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

### `contracts/button.py`

- **Required root:** `.dz-button` (part `button`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-button` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: button — chromatic CTA control.

Dual-lock unit is the control root. Variant/size/htmx attrs are host-owned.
Gallery and Dazzle substrate both use class ``.dz-button`` (plus
``data-dz-variant`` / ``data-dz-size`` when styled).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="button",
    root=".dz-button",
    nodes=(Node(".dz-button", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/button.py`
