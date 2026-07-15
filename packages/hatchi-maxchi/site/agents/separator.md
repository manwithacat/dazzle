# Separator (`separator`)

A hairline divider on the border token — horizontal (`<hr>`) or vertical (`role=separator`).

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="hm-stack hm-measure">
  <p class="hm-demo-muted">Account details</p>
  <hr class="separator">
  <p class="hm-demo-muted">Billing and invoices</p>
  <div class="hm-demo-row">
    <span class="hm-demo-muted">Draft</span>
    <div class="separator--vertical" role="separator" aria-orientation="vertical"></div>
    <span class="hm-demo-muted">Published</span>
    <div class="separator--vertical" role="separator" aria-orientation="vertical"></div>
    <span class="hm-demo-muted">Archived</span>
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

### `contracts/separator.py`

- **Required root:** `.dz-separator, .dz-separator--vertical` (part `separator`)

| Node | Attr | Constraint |
|---|---|---|
| `.dz-separator, .dz-separator--vertical` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: separator — hairline divider (horizontal or vertical).

Dual-lock unit is the separator root. Orientation and placement are
host-owned. Class ``.dz-separator`` (and ``.dz-separator--vertical``) is
the stable substrate root (gallery partial; no FragmentRenderer emit yet).
"""

from contracts._kit import DomContract, Node

DOM_CONTRACT = DomContract(
    part="separator",
    root=".dz-separator, .dz-separator--vertical",
    nodes=(Node(".dz-separator, .dz-separator--vertical", attrs={}),),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

The horizontal rule is a native <hr> (implicitly role=separator); the vertical divider is a zero-width element with an explicit role=separator + aria-orientation="vertical". Dual-lock root .dz-separator (HMC-138).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/separator.py`
