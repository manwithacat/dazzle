# Aspect ratio (`aspect-ratio`)

Media frame that locks width/height — images and embeds fill with object-fit cover.

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="hm-demo-row" style="gap: var(--space-md); align-items: flex-start;">
  <div class="aspect-ratio" data-ratio="1/1" style="width: 6rem;" aria-label="1:1 frame"><span style="display:grid;place-items:center;background:var(--colour-brand-soft);color:var(--colour-brand-text);font-size:var(--text-xs);">1:1</span></div>
  <div class="aspect-ratio" data-ratio="16/9" style="width: 10rem;" aria-label="16:9 frame"><span style="display:grid;place-items:center;background:var(--colour-brand-soft);color:var(--colour-brand-text);font-size:var(--text-xs);">16:9</span></div>
  <div class="aspect-ratio" data-ratio="4/3" style="width: 8rem;" aria-label="4:3 frame"><span style="display:grid;place-items:center;background:var(--colour-brand-soft);color:var(--colour-brand-text);font-size:var(--text-xs);">4:3</span></div>
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

### `contracts/aspect_ratio.py`

- **Required root:** `.dz-aspect-ratio` (part `aspect-ratio`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-aspect-ratio` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: aspect-ratio — media frame that locks width/height.

Dual-lock unit is the frame root. ``data-dz-ratio`` presets and child
fill (object-fit) are host-owned. Class ``.dz-aspect-ratio`` is the stable
substrate root (gallery CSS; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="aspect-ratio",
    root=".dz-aspect-ratio",
    nodes=(Node(".dz-aspect-ratio", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

PLACEHOLDER — shadcn parity (HMC-036). Pure CSS aspect-ratio + data-dz-ratio presets (1/1, 4/3, 16/9, 21/9). Dual-lock root .dz-aspect-ratio (HMC-132). No controller.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/aspect_ratio.py`
