# Stem: Hypermedia SSR

## Claim

The UI is **server-rendered HTML**. Interactivity is **HTMX** (fragment swaps).
There is no React/Vue SPA as the product surface. State lives on the server and
in the DOM (attributes, checked, aria), not a client state graph.

## Reconstruct

- Prefer HTML fragment responses over JSON view-models for UI.
- Morph/swap survival: don’t park edit state in JS objects the morph drops.
- Design system: HaTchi-MaXchi Hyperparts (partial + exchange).

## Not this

- Hydrated SPA as the default app shell.
- Parallel client domain store “because HTMX is limited.”
- Gallery `/mock/*` as product API (HM).

## Expressions

- ADR-0011 (SSR+HTMX), ADR-0023 (typed fragments)
- `packages/hatchi-maxchi/stems/` (Hyperpart stems)
- `src/dazzle/page/`, `src/dazzle/render/`
