# Keyboard key (`kbd`)

Shortcut chip for docs and command chrome — <kbd class=dz-kbd>.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="hm-demo-row">
  <kbd class="kbd">⌘K</kbd>
  <kbd class="kbd">Esc</kbd>
  <kbd class="kbd">↵</kbd>
  <kbd class="kbd">⇧</kbd>
</div>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

### Seams

- `<kbd class="dz-kbd">` — always the house chip, never bare Unicode
- layout roles: adjacent (button:has kbd gap) vs trailing (list/menu auto)

### Do / Don't

| Do | Don't |
|---|---|
| visually secondary chip + adjacent gap or trailing auto | glue ⌘K to the action label or invent a Lucide keyboard as the only hint |

### Pitfalls

- 0px gap between primary label and kbd under-signals secondary metadata
- do not apply affordance-disclosure-chrome (chevrons) rules to shortcuts
- do not put a kbd on every dense toolbar control (clutter)

### Keyboard / AT

- kbd is presentational hint; the control still needs its own accessible name

### Related parts

- `command` — agents/command.md
- `button` — agents/button.md

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/kbd.py`

- **Required root:** `.dz-kbd` (part `kbd`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-kbd` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: kbd — keyboard shortcut chip for docs and command chrome.

Dual-lock unit is the kbd root. Glyph content and layout role (adjacent vs
trailing) are host-owned. Class ``.dz-kbd`` is the stable substrate root
(gallery / hm-core; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="kbd",
    root=".dz-kbd",
    nodes=(Node(".dz-kbd", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

Stem shortcut-hint-chrome: keyboard chips are visually secondary (mono, small, muted keycap) and spatially secondary — layout roles adjacent (flex gap next to a label) vs trailing (row end via margin-inline-start: auto). Not disclosure iconography. Styles in hm-core.css; pure presentation. Dual-lock root .dz-kbd (HMC-151).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/kbd.py`
