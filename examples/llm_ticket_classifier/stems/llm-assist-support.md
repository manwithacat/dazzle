# Stem: Support ops with LLM classification/extraction as assistive, deterministic-first

## Claim

LLM intents **assist** ticket ops; human and deterministic paths remain first-class. Domain is support tickets + classification, not 'AI replaces the model'.

## Reconstruct

- Prefer DSL LLM intents with clear I/O over unbounded agent loops.
- Keep ticket entities/scopes authoritative; LLM output is enrichment.

## Not this

- Making the LLM the system of record for ticket state.

## Expressions

- `dsl/`, SPECIFICATION
- Framework: `stems/dsl-first.md`, `stems/authoring-boundary.md`
