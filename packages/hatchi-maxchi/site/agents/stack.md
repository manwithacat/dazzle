# Stack (`stack`)

Vertical rhythm: children flow top-to-bottom with one gap token. The workhorse — most page sections are a stack of stacks.

> **Layer:** L1 surface · **Recipe:** `layout-primitive` — layout primitive
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="stack" data-gap="md">
  <div class="hm-demo-box">One</div>
  <div class="hm-demo-box">Two</div>
  <div class="hm-demo-box">Three</div>
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

### `contracts/stack.py`

- **Required root:** `.dz-stack` (part `stack`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-stack` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: stack — vertical layout group.

Dual-lock unit is the stack root. Gap scale rides ``data-dz-gap``. Child
fragments are host-owned. Class ``.dz-stack`` is the stable substrate root.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="stack",
    root=".dz-stack",
    nodes=(Node(".dz-stack", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

Flex column + gap — margins stay on the children's insides, so any fragment composes without margin-collapse surprises. data-dz-gap takes xs|sm|md|lg|xl (the spacing token scale); unset = md. Nest freely: a stack inside a stack is the normal way to vary rhythm between groups.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/stack.py`
