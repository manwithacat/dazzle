# 0009 — Carousel: stage, composition, wrap, and autoplay

**Status:** Accepted
**Date:** 2026-07-13
**Stems:** three-layers, composition-declared, DOM identity/state, morph-safe hypermedia, overlay-light-dismiss (pause/secondary timing analogy)

## Context

shadcn’s Carousel is a React shell over **Embla**: a fixed stage, ordered peers,
prev/next (and optional loop/autoplay plugins). The job is **navigating a
sequence of full-frame peers inside a stable box** — not a generic layout
container and not a tab strip.

HaTchi-MaXchi’s carousel started as SSR markup + deferred controller, then
gained DOM-local prev/next/dots (clamp only) and a mixed-media demo. We need
explicit product policy for:

1. What a slide *is* (media vs hypermedia fragment)
2. How stage geometry relates to **aspect-ratio**
3. Wrap (last → first) vs clamp
4. Timed advance (autoplay) without violating “state in the DOM”

## Decision

### Job

**Carousel** = L1 surface that presents an **ordered sequence of peer slides**
in one **stage** (viewport). Navigation is prev / next / dots / keyboard.
Slides are **HTML fragments** (images, cards, `hx-*` CTAs). The common case is
media; the ceiling is hypermedia, not image-only.

Not carousel: mode switches (**tabs**), searchable catalogues (**grid**),
record peeks (**drawer**).

### Stage vs aspect-ratio

| Concern | Owner |
|---------|--------|
| **Stage geometry** (how tall is the strip?) | Carousel **viewport** — default 16/9; author may set `data-dz-ratio` on the viewport (same presets as aspect-ratio) |
| **How media fills a slide** | Media policy: **contain** (letterbox mixed intrinsic sizes) by default; **cover** by composing **aspect-ratio** *inside* a media slide |

- **Compose** `aspect-ratio` inside a slide for cover/crop frames.
- **Do not** put prev/next state on aspect-ratio; carousel owns sequence index.
- Hosts should not wrap the whole carousel in aspect-ratio (controls fall outside the stage).

### Wrap

| Value | Behaviour | Default |
|-------|-----------|---------|
| `data-dz-carousel-wrap="none"` (or absent) | **Clamp** — disable Previous on first, Next on last | **Yes** |
| `data-dz-carousel-wrap="loop"` | **Loop** — last→first, first→last; ends stay enabled | Opt-in |

Clamp is the default so finite task UIs and SSR “Previous disabled” stay honest.
Loop is for ambient/marketing strips.

### Autoplay (temporal secondary)

| Rule | Detail |
|------|--------|
| Off by default | No `data-dz-carousel-interval` ⇒ no timer |
| Interval | `data-dz-carousel-interval="{ms}"` (minimum 500) |
| State | Timer only advances the same DOM attrs as prev/next (`data-dz-active`, index) |
| Pause | While `:hover` or `:focus-within` on the root; while `document.hidden` |
| Reduced motion | If `prefers-reduced-motion: reduce`, never arm the timer |
| At last slide | **Clamp:** stop autoplay. **Loop:** continue |

Autoplay is **secondary chrome**, not the only path to content. Critical copy
must be reachable without waiting.

### Hypermedia

- In-slide `hx-*` belongs to the **action’s Exchange**, not a carousel toast API.
- Servers may re-render the whole strip; the controller is the local affordance
  when the page stays put.
- Lazy slide bodies / server-paged strips are allowed later; demos must exercise them.

### Affordances (normative minimum)

Root: `[data-dz-carousel]`, `data-dz-carousel-index`, optional wrap/interval.
Slides: `.dz-carousel__slide` + one `[data-dz-active]`.
Controls: prev/next/dots; optional `[data-dz-carousel-status]` (“Slide N of M”).
Keyboard: ArrowLeft/Right (and optional Home/End) when focus is inside the root.

## Consequences

- Controller grows wrap + autoplay + keyboard + status; still no Alpine / no
  parallel slide model outside the DOM.
- Gallery ships **two** demos: clamp media+hypermedia (default), and loop+autoplay
  ambient (explicit attrs).
- Contract module documents wrap/interval/status selectors.
- Tests pin clamp ends, loop wrap, status text, autoplay advance (with pause /
  reduced-motion as feasible).

## Not decided here

- Embla / drag physics in core (invention ladder: prefer CSS scroll-snap or
  stay click/keyboard until product requires a drag engine).
- Thumbnail strip as a separate Hyperpart vs composition of a second carousel.

## Related

- Gallery + `controllers/dz-carousel.js`, `components/carousel.css`
- `aspect-ratio` Hyperpart (frame primitive)
- `docs/agent/compose-or-refuse.md`, stems `composition-declared`, `three-layers`
