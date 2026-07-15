# Cell grid (`grid-list`)

A responsive grid of plain record cells — title plus label: value lines, 1 → 2 → 3 columns as the container widens.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="grid-region">
  <div class="grid-list">
    <div class="grid-cell ">
      <h4 class="grid-cell-title">Aurora Substation</h4>
      <p class="grid-cell-field"><span class="grid-cell-field-label">Region:</span> North</p>
      <p class="grid-cell-field"><span class="grid-cell-field-label">Load:</span> 82%</p>
    </div>
    <div class="grid-cell ">
      <h4 class="grid-cell-title">Beacon Substation</h4>
      <p class="grid-cell-field"><span class="grid-cell-field-label">Region:</span> East</p>
      <p class="grid-cell-field"><span class="grid-cell-field-label">Load:</span> 47%</p>
    </div>
    <div class="grid-cell ">
      <h4 class="grid-cell-title">Cinder Substation</h4>
      <p class="grid-cell-field"><span class="grid-cell-field-label">Region:</span> West</p>
      <p class="grid-cell-field"><span class="grid-cell-field-label">Load:</span> 91%</p>
    </div>
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

### `contracts/grid_list.py`

- **Required root:** `.dz-grid-list` (part `grid_list`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-grid-list` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: grid_list — responsive grid of plain record cells.

Dual-lock unit is the grid-list root. Cells, titles, and field lines are
host-owned. Class ``.dz-grid-list`` is the stable substrate root (gallery CSS;
no FragmentRenderer emit yet). Often nested under ``.dz-grid-region``.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="grid_list",
    root=".dz-grid-list",
    nodes=(Node(".dz-grid-list", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

Cells are deliberately chrome-free — the surrounding card owns borders and title. The column count is a viewport response (1 column, then 2 at 40rem, 3 at 64rem). The is-clickable hover/cursor affordance is styled but currently a LEGACY reserve — the substrate grid emitter does not yet wire cell drill URLs (follow-up on the Dazzle side). Dual-lock root .dz-grid-list (HMC-144).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/grid_list.py`
