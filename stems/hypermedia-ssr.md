# Stem: Hypermedia SSR

## Claim

The UI is **server-rendered HTML**. Interactivity is **HTMX** (fragment swaps).
There is no React/Vue SPA as the product surface. State lives on the server and
in the DOM (attributes, checked, aria), not a client state graph.

## Reconstruct

- Prefer HTML fragment responses over JSON view-models for UI.
- Morph/swap survival: don’t park edit state in JS objects the morph drops.
- Design system: HaTchi-MaXchi Hyperparts (partial + exchange).
- HM specialisation: morph for stable surfaces, DOM identity/state, no Alpine
  in core — `packages/hatchi-maxchi/stems/morph-safe-hypermedia.md`.

## Not this

- Hydrated SPA as the default app shell.
- Parallel client domain store “because HTMX is limited.”
- Gallery `/mock/*` as product API (HM).
- “htmx + Alpine” as the default product stack (HM core forbids Alpine).

## Expressions

- ADR-0011 (SSR+HTMX), ADR-0023 (typed fragments)
- `packages/hatchi-maxchi/stems/` (Hyperpart stems)
- `packages/hatchi-maxchi/stems/morph-safe-hypermedia.md` + decisions 0005–0008
- `src/dazzle/page/`, `src/dazzle/render/`
