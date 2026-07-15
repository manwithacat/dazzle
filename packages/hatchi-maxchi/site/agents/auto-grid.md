# Auto grid (`auto-grid`)

A responsive card grid with no breakpoints: columns pack to fit, each at least the minimum width, all equal.

> **Layer:** L1 surface · **Recipe:** `layout-primitive` — layout primitive
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="auto-grid" style="--grid-min: 9rem">
  <div class="hm-demo-box">A</div>
  <div class="hm-demo-box">B</div>
  <div class="hm-demo-box">C</div>
  <div class="hm-demo-box">D</div>
  <div class="hm-demo-box">E</div>
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

### `contracts/auto_grid.py`

- **Required root:** `.dz-auto-grid` (part `auto_grid`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-auto-grid` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: auto_grid — responsive equal-column card grid (no breakpoints).

Dual-lock unit is the auto-grid root. Children, ``--dz-grid-min``, and
``data-dz-gap`` are host-owned. Class ``.dz-auto-grid`` is the stable
substrate root (gallery partial; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="auto_grid",
    root=".dz-auto-grid",
    nodes=(Node(".dz-auto-grid", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

grid-template-columns: repeat(auto-fit, minmax(min(var(--dz-grid-min, 14rem), 100%), 1fr)) — the inner min() stops overflow when the container is narrower than the minimum (the classic auto-fit footgun). --dz-grid-min is a PUBLIC knob; gap rides data-dz-gap as on stack. Dual-lock root .dz-auto-grid (HMC-136).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/auto_grid.py`
