# Stem: Authoring boundary

## Claim

**Structural Dazzle authoring** (DSL, IR types, examples, schema that define the
app’s shape) happens **in the agent session** with full repo context. Remote
APIs may return **data** (extraction, classification), not idiomatic DSL writes.

## Reconstruct

- LLM call → structured analysis → **in-session agent** writes `.dsl`.
- Warning sign: API that *writes* DSL without stems/AGENTS.

## Not this

- “Generate the whole app from a single out-of-band prompt API.”
- Silent DSL mutation from a webhook with no validation loop.

## Expressions

- `AGENTS.md` › Authoring vs API Boundary (#1222)
- MCP tools: validate/inspect/lookup — not author-as-service
