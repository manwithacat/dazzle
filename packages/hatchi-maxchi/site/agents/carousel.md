# Carousel (`carousel`)

Content strip for media or HTML fragments — fixed viewport, object-fit media, DOM-local prev/next/dots (or server re-render).

> **Layer:** L1 surface · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="carousel" data-carousel data-carousel-index="0" aria-roledescription="carousel" aria-label="Cat gallery">
  <div class="carousel__viewport">
    <div class="carousel__track">
      <div class="carousel__slide carousel__slide--media" data-active>
        <div class="carousel__media"><img src="media/carousel/cat-wide.svg" width="640" height="360" alt="Landscape cat · 16 by 9 illustration"></div>
      </div>
      <div class="carousel__slide carousel__slide--media">
        <div class="carousel__media"><img src="media/carousel/cat-tall.svg" width="300" height="400" alt="Portrait cat · 3 by 4 illustration"></div>
      </div>
      <div class="carousel__slide carousel__slide--media">
        <div class="carousel__media"><img src="media/carousel/cat-square.svg" width="400" height="400" alt="Square cat · 1 by 1 illustration"></div>
      </div>
      <div class="carousel__slide carousel__slide--rich">
        <div class="card card-body">
          <div class="card-label">Hypermedia slide</div>
          <div class="card-value" style="font-size:var(--text-base)">Adopt Mochi</div>
          <p class="carousel__caption" style="margin-top:var(--space-xs)">Slides are HTML fragments — media, KPI cards, or <code>hx-get</code> actions. The strip is not image-only.</p>
          <button type="button" class="button" data-variant="primary" style="margin-top:var(--space-sm)" hx-get="/mock/carousel/adopt" hx-target="#hm-carousel-adopt" hx-swap="innerHTML">Request visit</button>
          <div id="hm-carousel-adopt" class="carousel__caption" style="margin-top:var(--space-sm)" aria-live="polite"></div>
        </div>
      </div>
    </div>
  </div>
  <div class="carousel__controls">
    <button type="button" class="carousel__btn" data-carousel-prev aria-label="Previous slide" disabled>‹</button>
    <div class="carousel__dots" role="group" aria-label="Slides"><button type="button" class="carousel__dot" aria-current="true" aria-label="Slide 1, landscape cat"></button><button type="button" class="carousel__dot" aria-label="Slide 2, portrait cat"></button><button type="button" class="carousel__dot" aria-label="Slide 3, square cat"></button><button type="button" class="carousel__dot" aria-label="Slide 4, adopt call to action"></button></div>
    <button type="button" class="carousel__btn" data-carousel-next aria-label="Next slide">›</button>
  </div>
  <p class="hm-demo-muted" style="margin:0;font-size:var(--text-xs)">Viewport is 16∶9; wide / tall / square media use <code>object-fit: contain</code>. Last slide is a live HTML fragment (not an image).</p>
</div>
```

## Server exchange

This Hyperpart has **no server exchange** — presentation or client chrome only. If you put `hx-*` on a control that uses this markup, that action's exchange belongs to the action, not this part.

## How to use it

### Seams

- root [data-dz-carousel] + data-dz-carousel-index
- slides .dz-carousel__slide with data-dz-active on the visible one
- media: .dz-carousel__slide--media > .dz-carousel__media > img|svg (object-fit contain in a fixed 16/9 viewport)
- rich HTML: .dz-carousel__slide--rich (cards, hx-* CTAs, live regions)
- prev [data-dz-carousel-prev] / next [data-dz-carousel-next] / .dz-carousel__dot peers

### Do / Don't

| Do | Don't |
|---|---|
| update data-dz-active + aria-current + disabled ends in the DOM | keep slide index only in a JS variable (orphaned on morph) |
| clamp at first/last with disabled buttons | infinite-wrap without an explicit product requirement |
| letterbox mixed aspect ratios with object-fit: contain | force every asset to fill and crop without intent |
| put media, cards, or hx-* actions in slides as HTML fragments | treat the carousel as an image-only widget with no server story |

### Pitfalls

- do not ship prev/next without a controller or server re-render (gallery demo must change data-dz-active on click)
- do not wrap at ends — clamp and disable Previous/Next (matches SSR disabled affordance on first slide)
- dots use role=group, not tablist (no tabpanels — axe)
- do not invent a JS slide model outside the DOM
- do not stretch mixed media with object-fit:cover unless product requires cropping — contain preserves aspect honestly
- do not assume slides are images only — hypermedia fragments and server-swapped strips are first-class

### Keyboard / AT

- aria-label on prev/next; aria-current on the active dot
- meaningful alt text on media; aria-roledescription=carousel on root
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

Only [data-dz-active] slides show. dz-carousel.js advances prev/next/dots (clamps at ends). Media: fixed viewport + object-fit: contain so mixed intrinsic sizes letterbox honestly. Hypermedia: a slide is any HTML fragment — image, card, or hx-* affordance; the server can also re-render the whole strip. shadcn parity (HMC-037).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/carousel.py`
- `controllers/dz-carousel.js`
