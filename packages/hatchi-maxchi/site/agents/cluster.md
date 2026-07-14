# Cluster (`cluster`)

A wrapping horizontal group — buttons, chips, metadata rows. Items keep their size and wrap when the line runs out.

> **Layer:** L1 surface · **Recipe:** `layout-primitive` — layout primitive
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="cluster" data-gap="sm"><button class="button" data-variant="primary">Save</button><button class="button" data-variant="outline">Cancel</button><span class="badge" data-tone="neutral">Draft</span></div>
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

### `contracts/cluster.py`

- **Required root:** `.dz-cluster` (part `cluster`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-cluster` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: cluster — horizontal wrapping group (substrate Row).

Dual-lock unit is the cluster root. Gap rides ``data-dz-gap``; optional
``data-dz-align``. Child fragments are host-owned. Class ``.dz-cluster`` is
the stable substrate root (``_emit_row``).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="cluster",
    root=".dz-cluster",
    nodes=(Node(".dz-cluster", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

Flex row + flex-wrap + gap. data-dz-gap as on stack. data-dz-align (center|start|end|baseline, default center) sets cross-axis alignment; data-dz-justify (start|end|between|center, default start) distributes the line. Never fixes widths — that's what makes it safe for translation-length and zoom changes.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/cluster.py`
