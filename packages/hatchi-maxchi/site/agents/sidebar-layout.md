# Sidebar (`sidebar-layout`)

Two panes: a fixed-ish side and a fluid content pane that wraps UNDER the side when it would get too narrow — responsive without a media query.

> **Layer:** L1 surface · **Recipe:** `layout-primitive` — layout primitive
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="sidebar-layout" style="--sidebar-width: 12rem">
  <div class="hm-demo-box">Side (12rem)</div>
  <div class="hm-demo-box">Content — wraps under the side when narrower than its minimum comfortable width.</div>
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

### `contracts/sidebar_layout.py`

- **Required root:** `.dz-sidebar-layout` (part `sidebar_layout`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-sidebar-layout` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: sidebar_layout — two-pane flex wrap (side + fluid content).

Dual-lock unit is the layout root. Side/content children, ``--dz-sidebar-width``,
and ``data-dz-side`` are host-owned. Class ``.dz-sidebar-layout`` is the stable
substrate root (gallery layout primitive; no FragmentRenderer emit yet).
Distinct from contracts/sidebar.py (``.dz-sidebar`` nav rail).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="sidebar_layout",
    root=".dz-sidebar-layout",
    nodes=(Node(".dz-sidebar-layout", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

The Every-Layout sidebar: flex + wrap; the side gets flex-basis: var(--dz-sidebar-width) (a PUBLIC knob — set it inline or at :root), the content gets flex-grow: 999 with min-inline-size: var(--dz-sidebar-content-min, 50%) — when the content can't hold that minimum on the line, it wraps to a full-width row. data-dz-side="end" puts the side after the content. No media query: the breakpoint is the CONTENT'S minimum, so the same markup works in a page, a card, or a drawer. Dual-lock root .dz-sidebar-layout (HMC-152).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/sidebar_layout.py`
