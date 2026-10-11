# HM marketing-vision gap — CTA prominence + feature-card finish (#1565)

**Date:** 2026-07-10
**Issue:** #1565
**Status:** Design approved

## Context

The HM sitespec-convergence arc (Goal 2 — marketing/sitespec design modernity)
shipped the `expressive` aesthetic family + families-reflavor-marketing in v0.99.2.
The on-subscription vision-score pilot then established the residual gap to
best-in-class exemplars (Stripe/Linear ~8.3–8.6):

| | colour_conf | hero_impact | cta_prominence | finish_polish | avg |
|---|---|---|---|---|---|
| baseline | 4 | 5 | 5 | 5 | ~5.1 |
| `expressive` | 8 | 8 | **6** | **7** | ~7.1 |

`expressive` closed the colour/hero gap. The two remaining weak dimensions are
`cta_prominence` and `finish_polish`. This design closes them.

Two exploration findings shaped the scope:
1. **The reinforced-CTA capability already exists** — `SectionKind.CTA` is a
   first-class sitespec section (`CTASpec` model + `.dz-section-cta` CSS). Nothing
   new is needed to render a CTA band; it just needs styling + a page that
   declares one.
2. **The vision score judges the 1440×1024 hero fold only** (`full_page=False`).
   A reinforced CTA *below* that fold does not move the number. The score-moving
   levers are above-fold.

Decision (user): keep the score fold-only; deliver the measured above-fold win
**and** style + wire the existing reinforced-CTA section as a genuine (unmeasured)
scrolling-user UX improvement.

## Goal

Push the marketing vision score from ~7.1 toward ~8 by lifting `cta_prominence`
(6→8) and `finish_polish` (7→8+), and give real users a reinforced CTA down the
page — all as delegated HM design (no app-side CSS), with the deterministic
hygiene floor (`test_sitespec_hygiene`, 97.2) staying green.

## Design

Three parts, all in HM. Structure lives in
`packages/hatchi-maxchi/components/sitespec.css`; per-family accent/flavor lives in
each family's marketing-reflavor block in `packages/hatchi-maxchi/families/*.css`.

### A. Hero CTA button prominence (above-fold — moves the score)

`.dz-section-hero .btn-primary` / `.btn-secondary` currently read timid on the
bold hero gradient. Changes:
- **Primary CTA** → a confident solid fill with strong contrast against the hero
  gradient (bright/near-white surface, high-contrast dark or accent text), heavier
  weight (~700), larger padding + font-size, generous radius.
- **Secondary CTA** → a clear outline/ghost (visible border, legible on gradient).
- **Designed hover** → lift (`translateY(-1px)`) + elevated shadow; snappy per the
  family motion tokens.
- Tokenize the fill/text/glow so each family flavors it: `expressive` gets a subtle
  accent glow; `stripe`/`paper`/`linear-dark` get restrained variants for parity.

### B. Feature-card finish (above-fold, in the 1024px fold — moves the score)

`.dz-card-item` and the features-section cards are flat (`0 1px 3px` shadow, plain
hover). Changes:
- **Crisp hairline border** (tinted `--dz-border-*`).
- **Refined multi-stop shadow** — depth, not flat grey.
- **Hover-lift** — `translateY(-2px)` + elevated shadow + accent-tinted border.
- **Icon treatment** — the `.dz-card-icon` container gets the family accent tint
  (`--dz-feature-icon-bg`) + a subtle ring/inner highlight so icons read as crafted.

### C. Reinforced CTA band (below-fold — unmeasured UX bonus)

- Style the existing `.dz-section-cta` into a confident full-width band: family
  gradient/tint background, bold headline, and a prominent CTA that reuses the
  Part-A button styling.
- Declare a `cta` section in `examples/llm_ticket_classifier`'s sitespec so a real
  marketing page exercises the band end-to-end.

## Measurement & gates

- **Vision pilot (subscription, no API cost):** boot `DAZZLE_OVERRIDE_THEME=expressive`
  in `examples/llm_ticket_classifier`, Playwright-capture the 1440×1024 fold, judge
  against `SITESPEC_VISION_DIMENSIONS` (`src/dazzle/core/sitespec_vision_rubric.py`).
  Target: `cta_prominence` 6→8, `finish_polish` 7→8+, avg ~7.1 → ~8.
- **Deterministic hygiene floor** (`tests/unit/test_sitespec_hygiene.py`, 97.2) must
  stay green.
- **Rebuild the HM dist** (`scripts/build_dist.py`) — sitespec.css flows to the served
  bundle; regen the drift-gated ux-catalogue (`test_ux_catalogue`).
- **Human review:** present before/after screenshots — the vision number is a
  self-judge; the user makes the aesthetic call.

## Files

- `packages/hatchi-maxchi/components/sitespec.css` — CTA buttons, feature cards,
  `.dz-section-cta` band.
- `packages/hatchi-maxchi/families/{expressive,stripe,paper,linear-dark}.css` —
  marketing-reflavor blocks (CTA fill/glow + card/icon accent tokens).
- `examples/llm_ticket_classifier/` sitespec — declare a reinforced `cta` section.
- Rebuild: `scripts/build_dist.py` output (served dist + generated theme families).

## Out of scope

- Full-page vision measurement (the fold-only metric is retained; reconciliation
  option 1 was declined).
- Any renderer/DSL change — the CTA section capability already exists.
- App-side CSS — all styling stays in HM (delegated design).
