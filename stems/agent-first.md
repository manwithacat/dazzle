# Stem: Agent-first

## Claim

The primary **writer** of Dazzle DSL and framework-shaped work is an AI agent.
Humans review and steer. Formal precision beats human-only ergonomic sugar when
the two conflict.

## Reconstruct

- Ambiguity in DSL is a bug (explicit paths, personas, scopes).
- Agents update all callers in one change (pairs with clean-breaks).
- MCP for cheap reads; CLI for long process/writes (ADR-0002).
- Counter-priors and model-driven failure modes exist so agents don’t recreate
  known 4GL pathologies.

## Not this

- Designing DSL primarily for “nice for humans typing once.”
- Shipping shims so agents can leave dead code paths.
- Out-of-context API that authors idiomatic DSL without repo stems.

## Expressions

- ADR-0004, ADR-0002, ADR-0003
- `AGENTS.md` › Authoring vs API Boundary, Counter-Prior Catalogue, Deferred decisions
- `docs/counter-priors/`, `docs/architecture/model-driven-failure-modes.md`
- `docs/architecture/epistemic-engineering-practice.md` (didactics + assessment)
- `make ship-surface` / drift gates — post-hoc prior correction (not a substitute for stems)
- Parked residual work: `docs/decisions/` (do not speculative-build PARKED DDs)
