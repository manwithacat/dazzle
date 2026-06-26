# Research notes

Empirical investigations spun off from building Dazzle — short, reproducible
studies of questions that came up while making an AI-collaborative software
substrate. Each note states a question, runs a real experiment, and reports what
held up (including what didn't, and any measurement mistakes caught along the way).

## Notes

- [Predicting task context from a code graph](context-bounds-prediction.md) — how
  far a *cheap* static-graph baseline gets you at predicting which code must be in
  an agent's context before a task. A naive keyword seed (45%) + forward closure
  (73%) + bidirectional edges (91%), in ~50 deterministic lines — and why the
  residual is a retrieval problem, not a graph or database problem. Runnable eval
  scripts included.
- [Do agent-written code biases persist across model generations?](epoch-stratification.md)
  — an epoch-stratified study across four real model generations (Opus 4.5 → 4.8),
  attributed by commit trailer. A four-way taxonomy (model-shed / substrate-held /
  disciplined-rise / campaign-noise) and the finding that no measured construct
  worsens with newer models — including a rising-`noqa` regression that *acquits*
  under the same convict/acquit discipline the reflection programme uses on code.
- [Can a cheap detector catch re-implemented capability before it's written?](reuse-detection.md)
  — a ~70-line Type-2 clone detector over the project's own agent-generated code.
  3.2% of functions sit in near-duplicate clusters, including genuine re-derived
  capability (one availability check re-implemented in four files) — but also
  parallel-by-design families, so the cheap reuse check is a *screen, not a
  verdict*. Tests the B(ii) reuse half the context-bounds spike left open.

## Related

- [Agent self-reflection](../architecture/agent-self-reflection.md) — the
  programme that motivated the context-prediction study: discovering counter-priors
  for *agentic* code production by having the agent adversarially interrogate its
  own assumptions.
- [Model-driven failure modes](../architecture/model-driven-failure-modes.md) — the
  4GL/MDE/CASE failure-mode threat model these investigations operate against.
