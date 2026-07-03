# HaTchi-MaXchi

An **htmx4-native design system** — the maturity of the modern component
aesthetic (shadcn-grade), without a client framework. Server-rendered
markup, semantic `dz-*` classes + `data-dz-*` modifiers, design tokens for
all variation, and interactions built on the htmx request lifecycle.

Currently developed inside [Dazzle](../../) (the "develop in-tree, extract
when stable" strategy). This directory is the **extraction seed**: it will
become a standalone repo via `git subtree split`, and Dazzle will consume
the published bundle back. See
[`../../docs/superpowers/specs/2026-07-03-hm-extraction-plan.md`](../../docs/superpowers/specs/2026-07-03-hm-extraction-plan.md).

## The map (start here)

| Path | What lives here |
|------|-----------------|
| `components/` | Component CSS (`alert.css`, `hm-core.css`, …). One semantic root class + `data-dz-*` modifiers; tokens carry the aesthetic. |
| `controllers/` | Vanilla-JS behaviour for the purely-client bits (`dz-confirm.js` = designed `hx-confirm`; `dz-command.js` = ⌘K palette keys). htmx-aware, no framework. |
| `site/` | The catalogue + gallery. `registry.py` is the **source of truth for the component list**; `build_site.py` renders the static gallery where every example IS its copy-paste snippet (they cannot drift). Includes a mock htmx4 so interactive demos run with no server. |
| `assets/` | Vendored Geist (OFL) + the Lucide icon registry (ISC). |
| `oracle/` | The taste rubric + blind-panel harness — the design system carries its own quality gate. |
| `dist/` | Built `hatchi-maxchi.{css,js}` — vendored back into Dazzle. |
| `tokens/` | OKLCH ramps, type, spacing, shadow, motion, focus (Stage 2 lands the token sheet here). |

## Add a component (the agent workflow)

1. Write its CSS in `components/` (or extend `hm-core.css`) — one root class,
   `data-dz-*` for variants, tokens for all values. No utility soup.
2. Add its canonical HTML to `site/registry.py` (`Component(...)`). That
   entry is both the gallery demo and the copy-paste snippet.
3. If it needs client behaviour, add a controller in `controllers/`.
4. Register the CSS file in Dazzle's three build lists (until extraction):
   `scripts/build_dist.py` (`CSS_SOURCES`, use the `HM / …` path),
   `src/dazzle/page/runtime/css_loader.py` (`CSS_SOURCE_FILES`, use the
   `@hm:…` sentinel), and the `dazzle.css` mirror comment.
5. `python scripts/build_dist.py` and re-render the gallery
   (`python packages/hatchi-maxchi/site/build_site.py`).
6. The gate `tests/unit/test_hm_tranche1.py` asserts the bundle carries the
   new selectors.

## Identity — familiar, not identical

HaTchi-MaXchi matches shadcn's *quality* signals (complete states, spacing
discipline, focus rings, layered elevation, dark-as-material) but owns its
*identity* signals — a chromatic accent (not monochrome zinc), colour+icon+text
semantics, tone-wash surfaces, htmx-lifecycle motion, and ops-app data density.
The review test for every component: credible to a shadcn-fluent developer,
but not mistakable for shadcn side-by-side.

## Use (in any htmx4 app, post-extraction)

```html
<link rel="stylesheet" href="hatchi-maxchi.css">
<script src="hatchi-maxchi.js" defer></script>
```

Copy any component's HTML from the gallery; point its `hx-*` attributes at
your endpoints. Geist (OFL) and Lucide (ISC) are vendored.
