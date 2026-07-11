# Stem: DSL-first

## Claim

Dazzle applications are specified in `.dsl` files. The parser produces a
**frozen AppSpec IR**. The runtime executes that IR. Business logic does not
live in generated Python trees or a parallel object model you maintain by hand.

## Reconstruct

- Edit `dsl/`, validate, serve — the model is the product surface for domain behaviour.
- Downstream (HTTP, page, specs, MCP) **read the same IR**.
- Generated artefacts (clients, fixtures) are projections, not the source of truth.

## Not this

- “Scaffold once then abandon the DSL.”
- A second domain model in ORM/Python that must stay in sync by convention.
- Treating AppSpec as mutable session state mid-request.

## Expressions

- ADR-0004 agent-first (pair stem), ADR-0006 frozen IR
- `docs/philosophy.md` › DSL → IR → runtime
- `src/dazzle/core/` parser + IR
- Examples: every `examples/*/dsl/`
