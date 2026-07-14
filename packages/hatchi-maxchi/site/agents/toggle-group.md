# Toggle group (`toggle-group`)

Segmented control on native radios.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<!-- icons: include the icon sheet once per page (see the Setup section, #setup) -->
<fieldset class="toggle-group" role="radiogroup">
  <label><input type="radio" name="hm-view" checked><span><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-list"/></svg> List</span></label>
  <label><input type="radio" name="hm-view"><span><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-kanban"/></svg> Board</span></label>
  <label><input type="radio" name="hm-view"><span><svg class="icon icon--size-sm" aria-hidden="true"><use href="#i-calendar"/></svg> Calendar</span></label>
</fieldset>
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

### `contracts/toggle_group.py`

- **Required root:** `.dz-toggle-group` (part `toggle_group`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-toggle-group` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: toggle_group — segmented control on native radios.

Dual-lock unit is the fieldset/radiogroup root. Segment labels and checked
state are host-owned. Class ``.dz-toggle-group`` is the stable substrate root
(gallery partial; no FragmentRenderer emit yet). Distinct from single
contracts/toggle.py.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="toggle_group",
    root=".dz-toggle-group",
    nodes=(Node(".dz-toggle-group", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

Dual-lock root .dz-toggle-group (HMC-153).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/toggle_group.py`
