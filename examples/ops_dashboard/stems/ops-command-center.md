# Stem: Ops command center

## Claim

This app demonstrates a **COMMAND_CENTER**-style workspace: personas, engine
hints, and attention-oriented regions (metrics, charts). Scope and persona
binding are part of the model, not post-hoc UI filters.

## Reconstruct

- Prefer DSL personas + scopes over handler-only auth.
- Charts/regions are Hypermedia SSR fragments, not client chart state stores.
- Extend domain via DSL entities/surfaces; don’t invent a parallel metrics API
  as the source of truth.

## Not this

- Treating the dashboard as unscoped admin-only by default without modelling it.
- Rebuilding charts as a SPA inside the example.

## Expressions

- `dsl/`, `SPEC.md`, `SPECIFICATION.md`, `trial.toml`
- Framework: `stems/rbac-and-scope.md`, `stems/hypermedia-ssr.md`
- HM: chart Hyperparts under `packages/hatchi-maxchi/`
