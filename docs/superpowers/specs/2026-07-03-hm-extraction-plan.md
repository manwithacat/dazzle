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

### Mechanics (when James says go)

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
6. Migrate the 249 legacy `hsl(var(--…))` call sites onto OKLCH semantic
   tokens during the move (they don't belong in the clean system).

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
