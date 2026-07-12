# Carousel (`carousel`)

Media / content strip — active slide is data-dz-active; prev/next and dots update DOM state via dz-carousel.js (or a server re-render).

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="carousel" data-carousel data-carousel-index="0">
  <div class="carousel__viewport">
    <div class="carousel__track">
      <div class="carousel__slide" data-active>Slide 1 · hero</div>
      <div class="carousel__slide">Slide 2 · details</div>
      <div class="carousel__slide">Slide 3 · CTA</div>
    </div>
  </div>
  <div class="carousel__controls">
    <button type="button" class="carousel__btn" data-carousel-prev aria-label="Previous slide" disabled>‹</button>
    <div class="carousel__dots" role="group" aria-label="Slides"><button type="button" class="carousel__dot" aria-current="true" aria-label="Slide 1"></button><button type="button" class="carousel__dot" aria-label="Slide 2"></button><button type="button" class="carousel__dot" aria-label="Slide 3"></button></div>
    <button type="button" class="carousel__btn" data-carousel-next aria-label="Next slide">›</button>
  </div>
</div>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

### Seams

- root [data-dz-carousel] + data-dz-carousel-index
- slides .dz-carousel__slide with data-dz-active on the visible one
- prev [data-dz-carousel-prev] / next [data-dz-carousel-next] / .dz-carousel__dot peers

### Do / Don't

| Do | Don't |
|---|---|
| update data-dz-active + aria-current + disabled ends in the DOM | keep slide index only in a JS variable (orphaned on morph) |
| clamp at first/last with disabled buttons | infinite-wrap without an explicit product requirement |

### Pitfalls

- do not ship prev/next without a controller or server re-render (gallery demo must change data-dz-active on click)
- do not wrap at ends — clamp and disable Previous/Next (matches SSR disabled affordance on first slide)
- dots use role=group, not tablist (no tabpanels — axe)
- do not invent a JS slide model outside the DOM

### Keyboard / AT

- aria-label on prev/next; aria-current on the active dot
- dot hit targets are 24×24 (visual pip via ::before)

## DOM contract

What emitted markup must satisfy (CI: `tests/test_contracts.py`). Do not invent attrs outside the tables. Python modules under `contracts/` are **package-internal dual-locks** (`from contracts._kit import …`) — not FastAPI business handlers. App servers implement **Server exchange** endpoints; this section constrains the HTML those endpoints return.

### `contracts/carousel.py`

- **Required root:** `[data-dz-carousel]` (part `carousel`)

| Node | Attr | Constraint |
|---|---|---|
| `[data-dz-carousel]` | `—` | — |
| `[data-dz-carousel-index]` | `data-dz-carousel-index` | present (any value) |
| `[data-dz-carousel-prev]` | `—` | — |
| `[data-dz-carousel-next]` | `—` | — |
| `[data-dz-active]` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: carousel — slide strip with prev/next/dots (DOM-local state)."""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="carousel",
    root="[data-dz-carousel]",
    nodes=(
        Node("[data-dz-carousel]", attrs={}),
        # Optional index stamp on the root (controller keeps it in sync).
        Node("[data-dz-carousel-index]", attrs={"data-dz-carousel-index": Present()}),
        Node("[data-dz-carousel-prev]", attrs={}),
        Node("[data-dz-carousel-next]", attrs={}),
        # Active slide marker (also mirrored as data-active after prefix strip).
        Node("[data-dz-active]", attrs={}),
    ),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

Only [data-dz-active] slides show. dz-carousel.js advances prev/next/dots (clamps at ends — Previous disabled on first, Next on last). Product hosts may re-render the strip over the wire; the controller is the local affordance when the page stays put. shadcn parity (HMC-037).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/carousel.py`
- `controllers/dz-carousel.js`
