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
    <p class="hm-demo-muted" style="margin:0 0 var(--space-sm);font-size:var(--text-xs)"><strong>Clamp</strong> (default) — Previous disabled on first, Next on last. Mixed media letterboxes in a 16∶9 stage; last slide is hypermedia HTML.</p>
    <div class="carousel" data-carousel data-carousel-index="0" data-carousel-wrap="none" data-size="lg" aria-roledescription="carousel" aria-label="Cat gallery" tabindex="0">
      <div class="carousel__viewport" data-ratio="16/9">
        <div class="carousel__track">
          <div class="carousel__slide carousel__slide--media" data-active>
            <div class="carousel__media"><img src="media/carousel/cat-wide.svg" width="640" height="360" alt="Landscape cat · 16 by 9 illustration"></div>
          </div>
          <div class="carousel__slide carousel__slide--media">
            <div class="carousel__media"><img src="media/carousel/cat-tall.svg" width="300" height="400" alt="Portrait cat · 3 by 4 illustration"></div>
          </div>
          <div class="carousel__slide carousel__slide--media">
            <div class="carousel__media carousel__media--cover">
              <div class="aspect-ratio" data-ratio="1/1" aria-hidden="true"><img src="media/carousel/cat-square.svg" width="400" height="400" alt=""></div>
            </div>
            <span class="visually-hidden">Square cat cropped to 1:1 cover frame</span>
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
        <div class="carousel__dots" role="group" aria-label="Slides"><button type="button" class="carousel__dot" aria-current="true" aria-label="Slide 1, landscape cat"></button><button type="button" class="carousel__dot" aria-label="Slide 2, portrait cat"></button><button type="button" class="carousel__dot" aria-label="Slide 3, square cover"></button><button type="button" class="carousel__dot" aria-label="Slide 4, adopt call to action"></button></div>
        <button type="button" class="carousel__btn" data-carousel-next aria-label="Next slide">›</button>
      </div>
      <p class="carousel__status" data-carousel-status aria-live="polite">Slide 1 of 4</p>
    </div>
  </div>
  <div>
    <p class="hm-demo-muted" style="margin:0 0 var(--space-sm);font-size:var(--text-xs)"><strong>Loop + autoplay</strong> — <code>data-carousel-wrap="loop"</code> and <code>data-carousel-interval="4000"</code>. Pauses on hover/focus; off when <code>prefers-reduced-motion</code>.</p>
    <div class="carousel" id="hm-carousel-ambient" data-carousel data-carousel-index="0" data-carousel-wrap="loop" data-carousel-interval="4000" data-size="lg" aria-roledescription="carousel" aria-label="Ambient cat loop" tabindex="0">
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
- media contain: .dz-carousel__media > img; cover: compose aspect-ratio inside .dz-carousel__media--cover
- rich HTML: .dz-carousel__slide--rich (cards, hx-* CTAs, live regions)
- status: [data-dz-carousel-status] (“Slide N of M”)
- prev / next / .dz-carousel__dot; keyboard arrows when focused
- decision 0009: docs/decisions/0009-carousel-stage-and-motion.md

### Do / Don't

| Do | Don't |
|---|---|
| update data-dz-active + aria-current + disabled ends in the DOM | keep slide index only in a JS variable (orphaned on morph) |
| opt into loop with data-dz-carousel-wrap=loop | infinite-wrap without an explicit product requirement |
| letterbox mixed sizes with contain; crop via composed aspect-ratio | hardcode cover on every media slide without intent |
| compose aspect-ratio inside a media slide for cover frames | wrap the whole carousel in aspect-ratio (controls fall outside) |

### Pitfalls

- do not ship prev/next without a controller or server re-render
- do not loop by default — clamp is the honest task-UI default
- do not autoplay without data-dz-carousel-interval (and respect prefers-reduced-motion + hover/focus pause)
- dots use role=group, not tablist (no tabpanels — axe)
- do not invent a JS slide model outside the DOM
- do not put navigation state on aspect-ratio — it owns frame only
- in-slide hx-* needs its own Exchange (not a carousel toast API)

### Keyboard / AT

- aria-label on prev/next; aria-current on the active dot
- aria-live status “Slide N of M”; aria-roledescription=carousel
- ArrowLeft/Right (Home/End) when focus is inside the root
- autoplay pauses on hover/focus; disabled under reduced motion
- dot hit targets are 24×24 (visual pip via ::before)

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
