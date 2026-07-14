# Avatar (`avatar`)

Initials or image; stacked groups.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="hm-demo-row">
  <span class="avatar-group"><span class="avatar">JD</span><span class="avatar">AK</span><span class="avatar">+3</span></span>
  <span class="avatar" data-size="lg">HM</span>
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

### `contracts/avatar.py`

- **Required root:** `.dz-avatar` (part `avatar`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-avatar` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: avatar — initials or image; optional stacked groups.

Dual-lock unit is the avatar root. Content, size, and grouping are
host-owned. Class ``.dz-avatar`` is the stable substrate root (gallery
partial; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="avatar",
    root=".dz-avatar",
    nodes=(Node(".dz-avatar", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

Dual-lock root .dz-avatar (HMC-149).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/avatar.py`
