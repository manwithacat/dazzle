# Tooltip (`tooltip`)

CSS-only visual hint (`data-dz-tooltip`) — zero JS. A hint, not an accessible tooltip: keep it non-critical (no touch/SR/keyboard path).

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<button class="button" data-variant="outline" data-tooltip="Saved 2 minutes ago">Hover me</button>
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

### `contracts/tooltip.py`

- **Required root:** `[data-dz-tooltip]` (part `tooltip`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-tooltip]` | `data-dz-tooltip` | present (any value) |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: tooltip — CSS-only visual hint (data-dz-tooltip).

Dual-lock unit is the tooltip host. Hint text and host chrome are host-owned.
Selector ``[data-dz-tooltip]`` is the stable substrate root (zero-JS gallery
hint; not an accessible tooltip — non-critical content only; no
FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="tooltip",
    root="[data-dz-tooltip]",
    nodes=(
        Node(
            "[data-dz-tooltip]",
            attrs={"data-dz-tooltip": Present()},
        ),
    ),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

Dual-lock root [data-dz-tooltip] (HMC-154).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/tooltip.py`
