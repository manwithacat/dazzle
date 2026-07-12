# Carousel (`carousel`)

Media / content strip — server marks the active slide; prev/next are hypermedia affordances (re-render or future controller).

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

No extended guidance authored yet — start from Copy this and the dependency chips.

### Seams

- copy the partial under Copy this; keep root class and data-* modifiers so the CSS/JS bundle matches
- no Server exchange on this part — pure presentation or client chrome
- no typed contracts/ module yet — the partial is the surface of record

## DOM contract

No typed dual-lock module in `contracts/` for this part yet. Treat **Copy this** as the required surface — preserve root class and `data-*` modifiers. Author `contracts/<part>.py` when CI should stop-ship attribute drift (`contracts/AUTHORING.md`).

## Notes

PLACEHOLDER — shadcn parity (HMC-037). Only [data-dz-active] slides show. Prefer server page index or OOB swap over client-only slide state. Controller that cycles data-dz-active is deferred.

## Source files

- `site/registry.py` (partial + exchanges + guidance)
