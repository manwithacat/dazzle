# Stem: Pragmatic gallery aesthetics

## Claim

A Hyperpart demo is a **teaching product surface**, not a QA fixture. If the
gallery looks broken, agents and humans learn the wrong contract—even when
behaviour tests pass. Prefer **one clear visual story** per demo region;
technical variety must still read as intentional design.

## Reconstruct

### Demo obligations (beyond “it works”)

| Obligation | Fail mode |
|------------|-----------|
| **Behaviour is observable** | Autoplay that never runs (reduced-motion, perpetual pause, timer never armed) |
| **One primary job per region** | Clamp + loop + form + aspect demos mashed into one confusing strip |
| **Visual consistency** | Letterbox gutters, black bars, or mixed padding that look like bugs |
| **Hypermedia in-family** | A form/card that looks dropped into the stage from another page |
| **Captions teach policy** | Relying on ugly side-effects (uneven crop, borders) to “show” a concept |

### Media stages

- Prefer **full-bleed** media in a fixed stage (`object-fit: cover`) for gallery
  polish unless the Hyperpart’s *job* is letterboxing.
- Teach mixed intrinsic sizes with **captions / chips** (“Source 3∶4 · cover”),
  not with large empty letterbox regions that look like missing CSS.
- **Aspect-ratio** composes for deliberate crop frames; don’t leave cover vs
  contain unexplained in the live preview.

### Temporal chrome (autoplay, loop)

- Autoplay must **actually advance** in the ambient demo when motion is allowed.
- Pause only on **intentional** hover/focus of that root—not on every child
  mouseenter that never re-arms.
- Avoid `tabindex="0"` on autoplay roots unless keyboard is the primary path;
  focus-within pause will kill the demo while the page merely holds focus.
- Under `prefers-reduced-motion: reduce`, **say so** in chrome copy and keep
  manual prev/next/loop working.

### Hypermedia slides

- In-slide actions should share the **same stage language** as media (e.g. hero
  overlay on an image), not a padded admin card that breaks immersion.
- Still declare Exchanges for `hx-*`; aesthetics never waive contract gates.

### Agent checklist before shipping a gallery change

1. Would a designer think this is broken, or intentional?
2. Can a cold viewer see the behaviour in **under five seconds**?
3. Does each demo region have **one sentence** of purpose above it?
4. Are letterboxes / crops / pauses **labelled** when they are the lesson?

## Not this

- Shipping “technically correct” demos with fixture energy (raw Lorem, grey
  boxes, dead controls).
- Using reduced-motion users as an excuse for no ambient demo—document the
  off state and keep manual navigation.
- Multiple conflicting policies in one carousel without labels (clamp + loop +
  cover + contain + form).

## Expressions

- `docs/decisions/0009-carousel-stage-and-motion.md`
- Carousel gallery demos (`site/registry.py` · carousel)
- `docs/agent/compose-or-refuse.md` (demo must exercise behaviour)
- host-chrome-symmetry “Demos must exercise the behaviour”
