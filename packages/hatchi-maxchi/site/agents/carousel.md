# Carousel (`carousel`)

Ordered peer slides in a stable stage — media and/or HTML fragments; DOM-local prev/next/dots (clamp or loop); optional autoplay.

> **Layer:** L2 host · **Recipe:** _(unset — see docs/agent/pick-a-surface.md)_
> Curriculum: `AGENTS.md` · pick matrix: `docs/agent/pick-a-surface.md` · blast radius: `CONSUMER_MAP.md`

> **Dialect:** Partial below is **unprefixed** (gallery / standalone HM). DOM contract Python often uses the **source token** `data-dz-*` / `dz-*` (Dazzle dual-lock). Match the CSS/JS bundle you load.

> **Demo vs contract:** Live gallery behaviour may use `/mock/*` or flash toasts. Those are **offline demos only** — implement **Server exchange** + **DOM contract**, not the mock. See AGENTS.md › Gallery demos.

## Copy this

```html
<div class="stack" data-gap="lg">
  <div>
    <p class="hm-demo-muted" style="margin:0 0 var(--space-sm);font-size:var(--text-xs)"><strong>Clamp</strong> — ends disable. Media fills the stage (<code>object-fit: cover</code>); chips name the source aspect. Last slide is a hero overlay (hypermedia in the same visual language).</p>
    <div class="carousel" data-carousel data-carousel-index="0" data-carousel-wrap="none" data-size="lg" aria-roledescription="carousel" aria-label="Cat gallery">
      <div class="carousel__viewport" data-ratio="16/9">
        <div class="carousel__track">
          <div class="carousel__slide carousel__slide--media" data-active>
            <div class="carousel__media"><img src="media/carousel/cat-wide.svg" width="640" height="360" alt="Landscape cat illustration"><span class="carousel__chip">Source 16∶9 · cover</span></div>
          </div>
          <div class="carousel__slide carousel__slide--media">
            <div class="carousel__media"><img src="media/carousel/cat-tall.svg" width="300" height="400" alt="Portrait cat illustration"><span class="carousel__chip">Source 3∶4 · cover</span></div>
          </div>
          <div class="carousel__slide carousel__slide--media">
            <div class="carousel__media"><img src="media/carousel/cat-square.svg" width="400" height="400" alt="Square cat illustration"><span class="carousel__chip">Source 1∶1 · cover</span></div>
          </div>
          <div class="carousel__slide carousel__slide--hero">
            <div class="carousel__media"><img src="media/carousel/cat-wide.svg" width="640" height="360" alt=""></div>
            <div class="carousel__hero">
              <p class="carousel__hero-kicker">Hypermedia slide</p>
              <p class="carousel__hero-title">Adopt Mochi</p>
              <p class="carousel__hero-text">Same stage as media — CTA and live region ride the strip, not a separate admin card.</p>
              <button type="button" class="button" data-variant="primary" hx-get="/mock/carousel/adopt" hx-target="#hm-carousel-adopt" hx-swap="innerHTML">Request visit</button>
              <div id="hm-carousel-adopt" class="carousel__hero-live" aria-live="polite"></div>
            </div>
          </div>
        </div>
      </div>
      <div class="carousel__controls">
        <button type="button" class="carousel__btn" data-carousel-prev aria-label="Previous slide" disabled>‹</button>
        <div class="carousel__dots" role="group" aria-label="Slides"><button type="button" class="carousel__dot" aria-current="true" aria-label="Slide 1, landscape"></button><button type="button" class="carousel__dot" aria-label="Slide 2, portrait"></button><button type="button" class="carousel__dot" aria-label="Slide 3, square"></button><button type="button" class="carousel__dot" aria-label="Slide 4, adopt call to action"></button></div>
        <button type="button" class="carousel__btn" data-carousel-next aria-label="Next slide">›</button>
      </div>
      <p class="carousel__status" data-carousel-status aria-live="polite">Slide 1 of 4</p>
    </div>
  </div>
  <div>
    <p class="hm-demo-muted" style="margin:0 0 var(--space-sm);font-size:var(--text-xs)"><strong>Loop + autoplay</strong> — <code>data-carousel-wrap="loop"</code> · <code>data-carousel-interval="3000"</code>. Advances every 3s; pauses while the pointer is over this strip; off under <code>prefers-reduced-motion</code> (status says so).</p>
    <div class="carousel" id="hm-carousel-ambient" data-carousel data-carousel-index="0" data-carousel-wrap="loop" data-carousel-interval="3000" data-size="lg" aria-roledescription="carousel" aria-label="Ambient cat loop">
      <div class="carousel__viewport" data-ratio="16/9">
        <div class="carousel__track">
          <div class="carousel__slide carousel__slide--media" data-active>
            <div class="carousel__media"><img src="media/carousel/cat-wide.svg" width="640" height="360" alt="Ambient slide 1, landscape cat"></div>
          </div>
          <div class="carousel__slide carousel__slide--media">
            <div class="carousel__media"><img src="media/carousel/cat-tall.svg" width="300" height="400" alt="Ambient slide 2, portrait cat"></div>
          </div>
          <div class="carousel__slide carousel__slide--media">
            <div class="carousel__media"><img src="media/carousel/cat-square.svg" width="400" height="400" alt="Ambient slide 3, square cat"></div>
          </div>
        </div>
      </div>
      <div class="carousel__controls">
        <button type="button" class="carousel__btn" data-carousel-prev aria-label="Previous ambient slide">‹</button>
        <div class="carousel__dots" role="group" aria-label="Ambient slides"><button type="button" class="carousel__dot" aria-current="true" aria-label="Ambient slide 1"></button><button type="button" class="carousel__dot" aria-label="Ambient slide 2"></button><button type="button" class="carousel__dot" aria-label="Ambient slide 3"></button></div>
        <button type="button" class="carousel__btn" data-carousel-next aria-label="Next ambient slide">›</button>
      </div>
      <p class="carousel__status" data-carousel-status aria-live="polite">Slide 1 of 3</p>
    </div>
  </div>
</div>
```

## Server exchange

When the client affordance finishes, htmx issues **this** request. Return the **response fragment** in the table (usually HTML, not JSON). Dazzle often implements these from the app model; a standalone HTMX4 app implements them explicitly.

> **Do not reimplement the gallery.** Flash toasts (e.g. confirm’s > “Deleted (demo).”), `/mock/*` paths, and other static-site > scaffolding are **demo-only** (`MOCK_HTMX` in `site/build_site.py`). > They are not Hyperpart surface and not a product API. If you are > stuck making a toast or mock URL work, stop — implement the > exchange row below instead. See AGENTS.md › *Gallery demos are not > the product API*.

| Request | Trigger | Response fragment | Swap | States |
|---|---|---|---|---|
| `GET /app/adoptions/request` | Request visit CTA inside a rich (non-media) slide | confirmation fragment into the slide live region (badge / status line) — not a full strip re-render | #hm-carousel-adopt innerHTML (gallery) / live region in the slide | populated error |

### `GET /app/adoptions/request` — example handler

Application code (not the dual-lock module). FastAPI-shaped; do not use `from __future__ import annotations` in route files (ADR-0014).

```python
@app.get("/app/adoptions/request")
async def adoption_request():
    return HTMLResponse('<span class="badge" data-tone="success">Visit requested</span>')
```

## Morph / swap

Stem: `stems/morph-safe-hypermedia.md` · decisions 0005–0007. Morph for **stable** surfaces; replacement for **disposable** fragments. Gallery mocks may approximate morph with `innerHTML` — production follows the swap column in **Server exchange**.

### Replace / `innerHTML` (reset OK)

- `GET /app/adoptions/request` → #hm-carousel-adopt innerHTML (gallery) / live region in the slide

### Identity rules

- Morph participants need **stable** `id` / domain keys (not loop indexes).
- Carry selection/edit affordances in the **DOM** (checked, `data-*`, ARIA) — not Alpine/`x-data` or a JS array a morph would orphan.
- Mark third-party widgets as explicit islands / morph-skip boundaries.

## How to use it

### Seams

- root [data-dz-carousel] + data-dz-carousel-index
- wrap: data-dz-carousel-wrap=none|loop (default none = clamp)
- autoplay: data-dz-carousel-interval=ms (absent = off; min 500)
- stage: .dz-carousel__viewport[data-dz-ratio] (1/1, 4/3, 16/9, 21/9)
- slides .dz-carousel__slide with data-dz-active on the visible one
- media full-bleed cover by default; chips name source aspect
- optional contain: .dz-carousel__media--contain; cover frame: .dz-carousel__media--cover + aspect-ratio
- hero hypermedia: .dz-carousel__slide--hero + .dz-carousel__hero overlay
- status: [data-dz-carousel-status] (“Slide N of M · Autoplay …”)
- prev / next / dots; keyboard when a control inside is focused
- decision 0009 + stem pragmatic-gallery-aesthetics

### Do / Don't

| Do | Don't |
|---|---|
| update data-dz-active + aria-current + disabled ends in the DOM | keep slide index only in a JS variable (orphaned on morph) |
| full-bleed cover media with source-aspect chips for gallery polish | leave uneven black bars that look like missing CSS |
| hero overlay for CTAs inside the same stage as media | orphan form/card that breaks the strip’s visual continuity |
| show autoplay state in status (on / paused / reduced motion) | silent timer that agents cannot observe |

### Pitfalls

- do not ship prev/next without a controller or server re-render
- do not loop by default — clamp is the honest task-UI default
- do not pause autoplay with document-level mouseenter on children (timer never re-arms) — pause only on root pointerenter/leave
- do not put tabindex=0 on autoplay roots unless required (focus-within kills ambient demos)
- do not teach mixed media with large letterbox gutters that look broken — full-bleed cover + chips; contain only when letterbox is the lesson
- do not drop a padded admin card into the stage as 'hypermedia' — use hero overlay language
- dots use role=group, not tablist
- in-slide hx-* needs its own Exchange

### Keyboard / AT

- aria-label on prev/next; aria-current on the active dot
- aria-live status including autoplay state; aria-roledescription=carousel
- ArrowLeft/Right when focus is on a control inside the root
- autoplay pauses while pointer is over the strip; off under reduced motion
- dot hit targets are 24×24

### Related parts

- `aspect-ratio` — agents/aspect-ratio.md
- `button` — agents/button.md
- `card` — agents/card.md
- `badge` — agents/badge.md

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
| `[data-dz-carousel-wrap]` | `data-dz-carousel-wrap` | present (any value) |
| `[data-dz-carousel-interval]` | `data-dz-carousel-interval` | present (any value) |
| `[data-dz-carousel-status]` | `—` | — |

#### Module source

Monorepo dual-lock only — import `contracts._kit` from the HM package. Do not paste into app route modules.

```python
"""HYPERPART: carousel — slide strip with prev/next/dots (DOM-local state).

See docs/decisions/0009-carousel-stage-and-motion.md for wrap / autoplay / stage.
"""

from contracts._kit import DomContract, Node, Present

DOM_CONTRACT = DomContract(
    part="carousel",
    root="[data-dz-carousel]",
    nodes=(
        Node("[data-dz-carousel]", attrs={}),
        Node("[data-dz-carousel-index]", attrs={"data-dz-carousel-index": Present()}),
        Node("[data-dz-carousel-prev]", attrs={}),
        Node("[data-dz-carousel-next]", attrs={}),
        Node("[data-dz-active]", attrs={}),
        # Optional chrome / policy (present when authored)
        Node("[data-dz-carousel-wrap]", attrs={"data-dz-carousel-wrap": Present()}),
        Node("[data-dz-carousel-interval]", attrs={"data-dz-carousel-interval": Present()}),
        Node("[data-dz-carousel-status]", attrs={}),
    ),
)

__all__ = ["DOM_CONTRACT"]
```

## Notes

Decision docs/decisions/0009-carousel-stage-and-motion.md. Only [data-dz-active] slides show. Clamp (default) disables ends; data-dz-carousel-wrap="loop" cycles. Autoplay via data-dz-carousel-interval (pause on hover/focus; off under reduced motion). Stage: viewport data-dz-ratio; media contain by default; cover via composed aspect-ratio. Hypermedia: slides are fragments; in-slide hx-* declares its own Exchange. shadcn/Embla parity job with DOM-carried state (HMC-037).

## Source files

- `site/registry.py` (partial + exchanges + guidance)
- `contracts/carousel.py`
- `controllers/dz-carousel.js`
