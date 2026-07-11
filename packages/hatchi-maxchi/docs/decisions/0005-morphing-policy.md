# 0005 — Morphing policy (htmx4)

**Status:** Accepted
**Date:** 2026-07-11
**Stem:** `stems/morph-safe-hypermedia.md`

## Context

htmx4 treats morphing as a first-class swap (`innerMorph`, `outerMorph`, and
related morph-style updates): mutate existing DOM toward server HTML while
preserving browser continuity where appropriate. Agents either (a) treat morph
as mandatory everywhere, or (b) ignore it and lose focus, selection, and open
menus on every table refresh.

HM needs a **strategic default** without a universal moral preference.

## Decision

**Morphing is the preferred update strategy for stable application surfaces.**
**Plain replacement remains correct for disposable fragments.**

Use morphing by default for:

- persistent application shells and regions;
- data tables and list bodies whose row identity should survive refresh;
- menus and toolbars that should keep open/focus state when structure is stable;
- form surfaces where focus preservation matters;
- interactive Hyperparts that are structurally stable between updates.

Use replacement (or full reset) for:

- disposable content and flash messages;
- simple one-shot responses;
- fragments that should fully reset;
- security-sensitive UI clears;
- third-party widgets that cannot tolerate reconciliation;
- cases where teardown is clearer than preservation.

Agents **must not** blindly rewrite every `hx-swap` to morph. Choose per region
from the list above. Prefer explicit, stable `hx-target` ids over brittle
ancestry selectors for morph roots.

## Consequences

- Hyperpart contracts and gallery demos document morph vs replace where it
  matters (especially hosts like `grid`).
- DOM identity (decision 0006) becomes load-bearing for morph success.
- Controllers must not park essential UI state only in JS objects the morph
  drops (pair with DOM-carried state).
- Swap-policy linting may start advisory (warn morph on flash; warn replace on
  persistent table roots) before becoming fatal.

## See also

- `stems/morph-safe-hypermedia.md`
- `docs/decisions/0006-dom-identity-and-state.md`
- Framework stem: monorepo `stems/hypermedia-ssr.md`
