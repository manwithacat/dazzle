# 0010 — HM controller coding standards

**Status:** Accepted
**Date:** 2026-07-13
**Stems:** `stems/morph-safe-hypermedia.md`, `stems/three-layers.md`,
`stems/hyperpart-not-component.md` (DOM-carried state via decision 0006)

## Context

HM Hyperpart controllers under `controllers/` are **vanilla, document-delegated
IIFEs** that discover affordances via dual-lock attributes and keep state in the
DOM. They ship as plain script in `dist/hatchi-maxchi.js` (and gallery mirrors).

That shape has been implicit. Agents and humans still reach for patterns that
fight it:

- TypeScript / build steps for “real” front-end quality
- Alpine or reactive scopes (forbidden in core — decision 0007)
- Per-instance mount graphs and parallel JS state models
- Style-opinion linters that thrash diffs without catching morph bugs

Meanwhile quality *does* need machine gates: structural errors (`no-undef`,
unreachable code), dual-lock contracts, and Playwright settlement that waits for
attrs **and** layout (not fixed sleeps alone).

## Decision

### Shipped controllers stay vanilla

| Rule | Detail |
|------|--------|
| Language | ES2022-or-below **plain JS**, one file per Hyperpart when needed |
| Packaging | IIFE + `"use strict"`; no module graph for core controllers |
| TypeScript | **Not** used for shipped controller sources |
| Optional later | `// @ts-check` + JSDoc on the largest files only if it pays for itself |
| Framework | No Alpine, React, Vue, or client component runtime in core |

**Types for HM are the contracts and the DOM**, not a TS project:

- dual-lock / Exchange surface → Python contracts + template lint
- behaviour → Playwright (and pure helpers extracted when logic is non-trivial)

### Coding shape (normative)

Preferred controller behaviour (extends decision 0007):

1. **Discover** roots and slots via `data-dz-*` (dual-lock); accept legacy
   `data-*` / class fallbacks only where gallery or product still emit them.
2. **Delegate** from `document` (or a stable shell root), not per-instance
   mount/unmount trees that die under morph.
3. **Read/write state in the DOM** (`data-*`, ARIA, open attributes, form
   controls, URL when contracted). Avoid a second source of truth.
4. **Survive morph**: re-query the DOM on each event; do not cache detached
   nodes as truth.
5. **Header chrome / focus**: settle active affordances after open (e.g. expand
   resting class, focus off chrome) with `requestAnimationFrame` when layout or
   pseudo-state races matter.
6. **Timers / motion**: honour `prefers-reduced-motion` where timed advance is
   optional (see decision 0009 for carousel).

### Lint posture

**Structural ESLint only** — no style/formatting opinions.

- Config: monorepo `eslint.config.mjs`
- Globs: `packages/hatchi-maxchi/controllers/**/*.js` (and product page JS under
  `src/dazzle/page/**` where still present)
- Rules: errors that mean broken code (`no-undef`, `no-unreachable`, duplicate
  keys/cases, invalid regexp, etc.)

Style is left to existing conventions and human review. Prettier/style ESLint
plugins are out of scope for core controllers.

### Testing posture

| Layer | Owns |
|-------|------|
| Dual-lock + contract modules | Public selectors, attrs, exchange honesty |
| Template lint | Morph/Alpine/identity classes in fixtures |
| Playwright behaviour | Click/keyboard paths, clamp/loop, expand width, etc. |
| Shared settlement helpers | Wait for attribute **and** layout bands (avoid mid-transition flakes) |
| Optional pure-unit later | Extract pure helpers (index math, label text) when logic is dense |

Prefer `wait_for_function` / shared conftest helpers over long `wait_for_timeout`
as the primary gate. Fixed short sleeps only as a post-settlement paint frame
when engines need it.

### Not decided here

- Full TypeScript migration of product or HM (rejected for shipped controllers).
- Moving every `dazzle.page` runtime script into HM (see monorepo audit issue:
  HM owns design-system UI; product glue may remain in page until audited).
- Pure-function unit harness for all controllers (optional follow-on).

## Consequences

- Agents must not “upgrade” controllers to TS or Alpine for quality theatre.
- ESLint is a real gate for HM controller sources, not a dead glob at a renamed
  path.
- New interaction complexity gets decision/stem coverage when product policy
  changes (e.g. 0009), not only code.
- Playwright helpers live in package `tests/conftest.py` so drawer, carousel, and
  future chrome tests share settlement language.

## See also

- `docs/decisions/0006-dom-identity-and-state.md`
- `docs/decisions/0007-no-alpine-in-core.md`
- `docs/decisions/0008-template-lint-posture.md`
- `docs/decisions/0009-carousel-stage-and-motion.md`
- `docs/agent/mutate-a-primitive.md`
- `stems/morph-safe-hypermedia.md`
