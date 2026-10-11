# HaTchi-MaXchi extraction — the spin-out

**Date:** 2026-07-03
**Status:** Seed built; extraction pending James's go.
**Parent:** `docs/superpowers/specs/2026-07-03-hatchi-maxchi-standalone-design.md`

## The seed exists

`scripts/hm_site/build_site.py` generates a **self-contained static site**
from the Dazzle source of truth into `hatchi-maxchi/`:

- `hatchi-maxchi.css` — the shipping bundle (fonts rewritten to relative).
- `hatchi-maxchi.js` — the behaviour controllers (`dz-confirm`, `dz-command`)
  plus a **mock htmx4** so interactive components (command palette, confirm
  dialog) work with no server. Swap the mock for real htmx in an app.
- `fonts/` — vendored Geist (OFL).
- `index.html` — the component gallery: each registry component rendered
  live AND shown as its copy-paste HTML from the SAME string, so docs
  cannot drift from the demo (the shadcn ownership model, hypermedia-native).
- `README.md`.

The registry (`scripts/hm_site/registry.py`) is the catalogue: 15 components
today, growing with each tranche. It doubles as the agent-facing reference.

Regenerate: `python scripts/hm_site/build_site.py`. The built dir is
committed so it can be previewed and lifted directly.

## The logical spin-out point

Extract when the **contract stops churning** — practically, once the
component set covers shadcn breadth and the `dz-*` class names are stable
(no renames in flight). The extraction is a directory move, not a rewrite,
because we kept `dz-*` and developed in an extraction-ready shape.

### Stage 3 EXECUTED (2026-07-03, v0.93.15)

The split went out as a **subtree split, not a cp** — the Dazzle monorepo
stays the source of truth while the standalone repo publishes:

- `git subtree split --prefix=packages/hatchi-maxchi` →
  [manwithacat/hatchi-maxchi](https://github.com/manwithacat/hatchi-maxchi)
  (history-preserving; the package commits ARE the new repo's history).
- Sync outward: `git subtree push --prefix=packages/hatchi-maxchi hm main`
  (remote `hm` = the standalone repo). Run after HM-touching Dazzle ships.
- CI: `.github/workflows/pages.yml` lives inside the package prefix (inert
  in Dazzle, live standalone) and deploys the committed `site/` gallery to
  GitHub Pages — no build step, because gallery rebuilds need Dazzle's
  icon registry and run in-tree.
- Still in-tree by design (follow-ons): the oracle port, icon-registry
  vendoring, npm publish, and flipping Dazzle to consume published
  releases via `update-vendors.yml`.

### Post-split hardening (2026-07-03, v0.93.16 / standalone v0.1.0)

- **Standalone build**: `build.py` (stdlib-only, runs in the split repo's
  CI) builds `dist/hatchi-maxchi.{css,js}` + fonts from package sources —
  the gallery now ships this design-system-only bundle, not the full
  Dazzle bundle.
- **Configurable prefix**: `python build.py --prefix ax-` renames the
  whole `dz-` namespace (classes, `data-dz-*`, keyframes) — `dz-` is the
  default and the contract Dazzle emits, not a requirement.
- **Regression gates** (`tests/`, run by `ci.yml`): console domain =
  contract tests (every published class has a rule; committed gallery
  artifacts match a fresh build; prefix transform is total) + behaviour
  tests (palette ⌘K/Esc/arrows, hx-confirm interception, theme toggle,
  persistence) in headless Chromium; visual domain = light+dark gallery
  screenshots vs committed baselines (1% differing-pixel tolerance,
  `HM_UPDATE_BASELINES=1` to regenerate).
- **Versioning**: semver from 0.1.0; `package.json` is the source of
  truth; `release.yml` gates tag==version and attaches the built bundle
  to the GitHub release.
- Launch bugs fixed: Esc now closes the palette on the first press
  (type=search swallowed it to clear the query); the theme toggle works
  (the gallery's page CSS re-declared `color-scheme` after the bundle,
  overriding the `[data-theme]` binding at equal specificity).

### Original mechanics sketch (superseded by the above)

1. `cp -r hatchi-maxchi/ ../hatchi-maxchi/` → `git init` the new repo.
2. Move the *sources* too (not just the built site): the component CSS
   (`static/css/components/*.css` + `hm-core.css` + tokens/fonts/base),
   the JS controllers, the icon registry + generator, and the site
   generator + registry. These become the new repo's `src/`.
3. New repo's CI: build the site → GitHub Pages; run the taste oracle
   (rubric + blind panel) as the design system's own quality gate.
4. Dazzle vendors the built CSS/JS back via the existing
   `update-vendors.yml` pattern (like htmx/lucide today). Dazzle's
   Fragment substrate stays in Dazzle and emits the contract.
5. Cross-repo contract test: Dazzle's `test_fragment_primitive_css`
   ("every emitted class has a rule") generalises to validate emitted
   markup against the published contract.
6. ~~Migrate the 249 legacy `hsl(var(--…))` call sites onto OKLCH semantic
   tokens during the move (they don't belong in the clean system).~~
   **DONE (Stage 2b, v0.93.14):** every call site migrated to
   `var(--colour-*)` / `color-mix(...)`, the HSL definition blocks
   deleted, and `design-system.css` moved to `base/`. The package's
   token sheet is the sole colour vocabulary.

## The feedback loop this unlocks

Once split: the design system iterates on its own gallery + oracle (fast,
visual, no Dazzle boot), and Dazzle consumes stable releases. An agent
building ANY htmx4 app reads one published contract. That is the
"agent-first structures + world-class aesthetics" separation James wants.

## Not yet (stays in-tree until extraction)

Breadth stragglers (calendar, context-menu, carousel, input-otp, toast
stacking) and adoption (column-menu→dz-menu, breadcrumb/avatar emitters)
are cheaper to build in-tree where the oracle + walks run. They land in
the registry as they ship, so the seed grows toward the extraction bar.
