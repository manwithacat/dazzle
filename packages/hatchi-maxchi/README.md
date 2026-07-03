# HaTchi-MaXchi

An **htmx4-native design system** — the maturity of the modern component
aesthetic (shadcn-grade), without a client framework. Server-rendered
markup, semantic `dz-*` classes + `data-dz-*` modifiers, design tokens for
all variation, and interactions built on the htmx request lifecycle.

Developed in-tree inside [Dazzle](https://github.com/manwithacat/dazzle)
(`packages/hatchi-maxchi/`), published standalone at
[manwithacat/hatchi-maxchi](https://github.com/manwithacat/hatchi-maxchi)
via `git subtree split` (Stage 3 of the extraction plan). The Dazzle
monorepo remains the source of truth; changes flow outward with
`git subtree push --prefix=packages/hatchi-maxchi hm main`. The gallery
deploys to GitHub Pages from `site/` on every push. See
`docs/superpowers/specs/2026-07-03-hm-extraction-plan.md` in Dazzle.

## The map (start here)

| Path | What lives here |
|------|-----------------|
| `tokens/` | `tokens.css` — the OKLCH ramps + semantic tokens (`--colour-*`), type, spacing, shadow, motion, focus. The single colour vocabulary; the legacy HSL system was removed in Stage 2b. |
| `base/` | `base.css` (element defaults + focus net), `fonts.css` (Geist @font-face), `design-system.css` (non-colour app-shell tokens + vendor-widget theming, moved in Stage 2b). |
| `components/` | Component CSS (`alert.css`, `hm-core.css`, …). One semantic root class + `data-dz-*` modifiers; tokens carry the aesthetic. |
| `controllers/` | Vanilla-JS behaviour for the purely-client bits (`dz-confirm.js` = designed `hx-confirm`; `dz-command.js` = ⌘K palette keys). htmx-aware, no framework. |
| `site/` | The catalogue + gallery (a committed build artifact — GitHub Pages serves it as-is). `registry.py` is the **source of truth for the component list**; `build_site.py` renders the static gallery where every example IS its copy-paste snippet (they cannot drift). Includes a mock htmx4 so interactive demos run with no server, and the vendored Geist fonts (OFL). |
| `.github/` | Pages deploy workflow — inert inside the Dazzle monorepo, live in the standalone repo. |

Planned (not yet populated): `oracle/` (the taste rubric + blind-panel
harness), `dist/` (a design-system-only bundle — today `site/hatchi-maxchi.css`
is the full Dazzle bundle), and `assets/` (the Lucide icon registry, which
still lives in Dazzle's `render/fragment/icon_registry.py` — `build_site.py`
imports it from the Dazzle tree, so **gallery rebuilds happen in-tree**).

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

## Use (in any htmx4 app)

```html
<link rel="stylesheet" href="hatchi-maxchi.css">
<script src="hatchi-maxchi.js" defer></script>
```

Copy any component's HTML from the gallery; point its `hx-*` attributes at
your endpoints. Geist (OFL) and Lucide (ISC) are vendored.
