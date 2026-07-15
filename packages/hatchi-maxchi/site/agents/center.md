# Center (`center`)

A measure-capped, centred column — reading width for prose and forms.

> **Layer:** L1 surface · **Recipe:** `layout-primitive` — layout primitive
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="center" data-measure="prose">
  <p class="hm-demo-muted">A comfortable reading measure tops out around 65 characters; this block centres itself and caps its width so lines stay scannable on any screen.</p>
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

### `contracts/center.py`

- **Required root:** `.dz-center` (part `center`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-center` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: center — measure-capped, centred column (prose/forms).

Dual-lock unit is the center root. Children and ``data-dz-measure``
(prose/wide/full) are host-owned. Class ``.dz-center`` is the stable
substrate root (gallery partial; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="center",
    root=".dz-center",
    nodes=(Node(".dz-center", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

margin-inline: auto + max-inline-size. data-dz-measure: prose (65ch), wide (90ch), full (no cap, still a centring context). This is the published form of the measure the gallery's own chrome uses. Dual-lock root .dz-center (HMC-137).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/center.py`
