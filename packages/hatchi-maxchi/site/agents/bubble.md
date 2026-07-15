# Bubble (`bubble`)

Chat bubble shell — rounded content for inbound/outbound speech. Compose inside message rows.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="hm-demo-row" style="gap:1rem;flex-wrap:wrap;align-items:flex-end">
  <div class="bubble" data-bubble data-from="in">
    <p>Can we reschedule the walkthrough to Thursday?</p>
  </div>
  <div class="bubble" data-bubble data-from="out">
    <p>Thursday 14:00 works — I'll send a calendar hold.</p>
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

### `contracts/bubble.py`

- **Required root:** `.dz-bubble` (part `bubble`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-bubble` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: bubble — chat bubble content shell (inbound/outbound).

Dual-lock unit is the bubble root. Body copy and ``data-dz-from`` orientation
are host-owned. Class ``.dz-bubble`` is the stable substrate root (gallery CSS;
no FragmentRenderer emit yet). Compose inside message rows for full chat UI.
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="bubble",
    root=".dz-bubble",
    nodes=(Node(".dz-bubble", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

PLACEHOLDER — shadcn parity (HMC-040). data-dz-from=in|out picks surface colour. Prefer message Hyperpart for avatar + meta; bubble is the content shell only. Dual-lock root .dz-bubble (HMC-141).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/bubble.py`
