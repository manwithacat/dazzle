# HM ⇄ Dazzle boundary + WCAG gate — design

**Date:** 2026-07-03
**Status:** ALL PHASES SHIPPED (v0.93.25/29/30) — the design is COMPLETE.
Phase 2 verification: full suite green, fleet pixel-compare 0-diff both
themes, adversarial review clean (2 stale-doc SEV-3s fixed in-commit). Phase 3's lockstep gate found REAL DRIFT on
its first run: `fragment-primitives.css` had been lost from the dev concat at
the Stage 2a move (dist had it, dev didn't — `serve --local` shipped without
`.dz-submit` styling); restored. The HM-side gallery-regen gate now runs in
standalone CI, byte-comparing a fresh dazzle-free rebuild to the committed
artifact. First axe run found 10 real
contrast failures (incl. a 1.08:1 invisible dark-mode alert title) — tone text
tokens are now scheme-aware (`light-dark()`), washes flip dark, white-text
fills use fixed ramp steps, and the old 3.0:1 token-gate threshold is 4.5:1.
**Parent:** `2026-07-03-hm-extraction-plan.md`

## Problem

Two goals appear to pull apart: real separation of concerns between
HaTchi-MaXchi and Dazzle, and the monorepo-with-subtree-publishing model.
They don't — the monorepo is a *locality* choice; separation is a
*dependency-direction* property. The direction leaks in two places today:

1. **HM → Dazzle (upstream imports downstream).** The gallery builder
   imports `dazzle.render.fragment.{icon_html,icon_registry}`, so the
   split repo cannot regenerate its own docs.
2. **Dazzle → HM internals.** Dazzle's build concatenates HM *sources*
   (`@hm:` sentinel entries) instead of consuming the drift-gated
   published artifact (`dist/`).

## Rule (the whole design in one line)

**HM is upstream: it may not import or read anything of Dazzle's.
Dazzle is downstream: it may consume only HM's published artifacts
(dist bundle, icons registry, documented dz-\* contract) — never its
internals.** Both directions are enforced by CI, not discipline.

Acceptance test: *the split repo builds, tests, audits, regenerates its
gallery, and releases with zero Dazzle code.*

## Phase 1 — icon registry moves upstream (into HM)

- `packages/hatchi-maxchi/icons/registry.py` becomes the source of
  truth: the AUTO-GENERATED Lucide subset (name → inner SVG, pinned
  version) plus the small `lucide_icon_html` / `lucide_svg_html`
  helpers, no imports beyond stdlib.
- The generator (`scripts/taste/gen_icon_registry.py`) moves to
  `packages/hatchi-maxchi/icons/gen_registry.py` and gains a second
  output: it writes the HM registry AND the Dazzle vendored copy.
- `src/dazzle/render/fragment/icon_registry.py` becomes an
  AUTO-GENERATED vendored copy (byte-identical data); Dazzle imports are
  unchanged. A Dazzle-side drift test asserts vendored == HM source.
- `site/build_site.py` imports from `..icons`, dropping its `dazzle.*`
  imports — the gallery rebuild becomes standalone.

## Phase 2 — Dazzle consumes `dist/`, not sources (riskiest, last)

- `css_loader.CSS_SOURCE_FILES` / `build_dist.CSS_SOURCES` replace the
  per-file `@hm:` entries with the single `@hm:dist/hatchi-maxchi.css`
  (and `dist/hatchi-maxchi.js` for the controllers).
- Cascade risk: HM files currently interleave with Dazzle files
  (utilities between base and components). Mitigation: HM's internal
  order inside dist matches today's relative order; ship behind fleet
  verification (contract gates + e2e walks + composite DOM tests) and
  an adversarial review before the flip; revert is one-line.
- After the flip, editing HM CSS requires `python build.py` — the
  existing dist drift gate already fails CI when forgotten.

## Phase 3 — boundary gates (mechanical enforcement)

- **HM CI:** `test_boundary.py` — no `dazzle` import in any package
  .py; plus the gallery is REGENERATED in CI and compared to the
  committed artifact (now possible via Phase 1), replacing the
  "rebuilds are in-tree only" caveat.
- **Dazzle CI:** build lists may reference only `@hm:dist/…`; vendored
  icon registry must match HM's; no other `packages/hatchi-maxchi`
  reads from `src/dazzle`.

## Phase 4 — WCAG 2.2 AA gate (gallery-only, HM CI)

- `tests/test_wcag.py`: axe-core (vendored `tests/vendor/axe.min.js`,
  MPL-2.0) injected via the existing Playwright harness.
- Scans: full gallery page in **light and dark**, plus opened-overlay
  states (command palette, confirm dialog, dropdown menu open).
- Fail on any violation tagged `wcag2a, wcag2aa, wcag21a, wcag21aa,
  wcag22a, wcag22aa`. Axe "best-practice" excluded (conformance only).
- `tests/wcag-allowlist.json`: rule-id + selector + justification for
  known manual-only items; unknown violations fail; **unused allowlist
  entries also fail** (the list can only shrink).
- Wired into the existing `ci.yml` test job (adds seconds).
- Out of scope (documented): fleet-level audits (landmarks, heading
  order, focus across htmx swaps) — future report-only ratchet per the
  brainstorm; manual-only criteria (2.2.x timing, media alternatives).

## Order & shipping

1 (icons) → 4 (WCAG gate) → 3 (boundary gates) → 2 (dist flip, gated on
adversarial review). Each phase bumps + ships + subtree-syncs; v0.1.1
release completes first and is independent.
