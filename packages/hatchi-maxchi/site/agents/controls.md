# Selection controls (`controls`)

Designed checkbox / radio / switch on native inputs — semantics free.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="hm-demo-row">
  <label class="hm-inline"><input type="checkbox" class="checkbox" checked> Checkbox</label>
  <label class="hm-inline"><input type="radio" class="radio" checked> Radio</label>
  <label class="hm-inline"><input type="checkbox" class="switch" checked> Switch</label>
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

### `contracts/controls.py`

- **Required root:** `.dz-checkbox, .dz-radio, .dz-switch` (part `controls`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-checkbox, .dz-radio, .dz-switch` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: controls — selection controls (checkbox / radio / switch).

Dual-lock unit is the designed native-input family. Label chrome is host-owned.
Classes ``.dz-checkbox``, ``.dz-radio``, and ``.dz-switch`` are the stable
substrate roots (gallery partial; no FragmentRenderer emit yet). Switch also
has a dedicated contracts/switch.py for data-dz-switch progressive enhancement.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="controls",
    root=".dz-checkbox, .dz-radio, .dz-switch",
    nodes=(Node(".dz-checkbox, .dz-radio, .dz-switch", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

### `contracts/switch.py`

- **Required root:** `[data-dz-switch]` (part `switch`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-switch]` | `data-dz-switch` | present (any value) |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: switch — on/off control over a native checkbox.

Dual-lock unit is the switch input root. Label chrome and track styling are
host-owned. Selector ``[data-dz-switch]`` is the stable substrate root
(gallery CSS progressive enhancement; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="switch",
    root="[data-dz-switch]",
    nodes=(
        Node(
            "[data-dz-switch]",
            attrs={"data-dz-switch": Present()},
        ),
    ),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

Dual-lock roots .dz-checkbox / .dz-radio / .dz-switch (HMC-150). Switch also dual-locks via contracts/switch.py ([data-dz-switch]).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/controls.py`
- `contracts/switch.py`
