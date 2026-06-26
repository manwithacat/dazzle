# Agent self-reflection: discovering agent-era counter-priors

Dazzle's [counter-prior catalogue](../counter-priors/INDEX.md) corrects **corpus
priors** — bad code shapes that dominate LLM training data because humans wrote
them at scale (Rails polymorphic associations, exceptions-as-control-flow, raw SQL
string-building). Each entry is a small permanent inoculation against a recurring
drift.

But corpus idioms are only half the story. Agentic code *production* has its own
predictable failure modes — the agent-era analogue of the patterns the catalogue
already corrects. The [model-driven failure-modes
register](model-driven-failure-modes.md) names this gap directly: **MDF-14,
"agent-amplified abstraction debt"**, is the one failure mode the historical
4GL/MDE literature cannot supply, because that literature predates agent-authored
change. This document describes the mechanism we use to *discover* such
agent-era counter-priors — and, just as importantly, the epistemology that keeps
the search honest.

## The reframe: human critique of AI code is a prior, not a verdict

The naive approach is to mine the growing body of commentary on "AI slop" and
treat it as ground truth: collect the constructs humans complain about in
AI-generated code, and forbid them. **This is wrong, and importing it would
corrupt the catalogue.**

Human critique of AI coding is *itself* a prior to be skeptical of. A human
reviewer flags constructs against a working-memory limit that the agent may not
share. Two common charges show the trap:

- **"Premature abstraction."** The word *premature* assumes the author couldn't
  see the whole problem. An agent that genuinely held the context and recognised a
  real generalisation may have abstracted *correctly* — the human flags it because
  the human couldn't see what the agent saw. The flaw is not abstraction; it is
  abstraction the agent *itself cannot justify against a concrete need*.

- **"Tautological tests."** A redundant-looking assertion may be one cell of a
  parameterised matrix buying *provable completeness*. The redundancy is
  exhaustiveness — a minor efficiency cost for a real guarantee. The flaw is not
  redundancy; it is an assertion that verifies the *mock* instead of the
  *behaviour*.

### The discriminating principle

> **The anti-pattern is never the shape. It is the unexamined assumption behind
> the shape.** The same construct is appropriate when the agent can articulate a
> justification, and an anti-pattern when it is a reflexive default. Only
> reflection separates them — and the agent is *better placed than a human critic*
> to do that separation, because it holds the context and can introspect the
> assumption.

So the criterion is not *"is this bad from a human perspective?"* It is:

> **After reflection, can an AI coding agent identify a flawed assumption in its
> own production?**

This is aspirational. Today's agents self-critique weakly. We build the mechanism
now; more introspective future agents run the same protocol and yield sharper
results. The protocol is the asset, not any single run's output.

## The reflection protocol

For a construct the agent produced, a structured self-interrogation — the
agent-era analogue of the four-question interrogation that governs
[ADR-0027](../adr/0027-no-polymorphic-ref.md):

1. **Name the assumption.** What did I implicitly believe when I wrote this?
   ("flexibility will be needed", "more guards = safer", "more assertions = more
   coverage")
2. **Concrete-need test.** What present or near-certain need does it serve? Can I
   point at the consumer, or am I serving a hypothetical?
3. **Counterfactual.** Would I still write it if the cost were fully visible to me
   and I were optimising only for the goal — or is it a default I reach for
   regardless?
4. **Cost ledger.** Indirection, surface area, redundancy, reader trace-back — is
   that cost paid for by the need in (2)?
5. **Conditions of wrongness.** Under what conditions is this construct wrong? Do
   they hold *here*?
6. **Traceability.** Could a competent peer reconstruct *why this shape, not the
   simpler one*, from the code — or does the justification live only in my head?

Then a **dialectic**: a second, independent agent steelmans the construct — gives
it the best principled defense it can honestly mount. The verdict:

- **Acquitted** — the defense holds and its conditions are present here. *Not* an
  anti-pattern. Record the defense as a guard against a human (or a future agent)
  talking the agent out of a correct call.
- **Convicted** — the defense collapses. A genuine anti-pattern. The artifact is a
  *reflection prompt plus the discriminating question*, never a blanket "don't do
  X" — because the shape is only wrong under specific conditions.

This produces two outputs, both load-bearing: **agent anti-patterns** (convicted
constructs, candidate catalogue entries) and **refuted human critiques**
(acquitted constructs — explicit notes that a construct is fine for an agent even
when review flags it).

## A worked example

The method's most important move is its willingness to *acquit*. A run on a real,
agent-authored construct in this codebase:

> **The construct.** An agent wrote one function rendering N overlaid chart
> series. A cyclomatic-complexity gate flagged it (26 > 15). The agent extracted
> four helpers (axis model, reference-overlay layer, one-series layer, axis
> labels) and the gate passed.
>
> **The charge.** "Metric-driven decomposition" — the agent split the function to
> get under a number, not because the boundaries were real. Unexamined assumption:
> *"passing the gate = better code."*
>
> **The verdict (independent steelman): acquitted.** All four boundaries tracked
> real domain concepts; three are extractions a competent engineer makes with no
> metric present; the residual orchestrator read as a *pipeline*, not incoherent
> glue. The durable insight: **metric-as-trigger ≠ metric-as-goal.** A complexity
> gate is a smoke detector — "go look," not "the house is on fire." The defect to
> hunt is not "the agent looked because the gate fired" but "the agent looked,
> found nothing real, and cut anyway." The tell is whether the orchestrator reads
> as a narrative or a tangle.

A human reviewer applying "the agent gamed the metric" reflexively would have
convicted good design. The programme's job is to refuse that — and, in the same
run, to surface the *genuine* residual smell the human framing missed (here: wide
parameter lists threaded by hand instead of a named coordinate-frame object).

## Measuring it: persistence across agent epochs

The strongest corpus for this programme is **Dazzle's own history**. The codebase
is almost entirely agent-generated, across many months and several successive
model generations ("agent epochs"), under largely one instruction set. That gives
us a discriminator nothing external can supply:

> Does a construct bias **persist across agent epochs**, or did a better model shed
> it?

- **Persists across epochs** → a structural prior. It will not self-correct; a
  counter-prior earns its keep.
- **Epoch-specific** → a weaker model's tic that newer models already fixed. Note
  and drop.

This turns the catalogue's "compounds across model generations" claim from
rhetoric into a **falsifiable measurement**: a bias that survives several agent
epochs in the same repository under the same instructions is a real prior, not
noise. It is also the cleanest test of the reframe above — a human-flagged
construct that *newer* agents stopped producing was never an agent anti-pattern,
only a human-legible artifact of an older model. (The project's own issue log is a
useful seam here: closed tech-debt and refactor issues are a record of past agent
sessions already convicting their own code.)

## Status

Aspirational by design. The value is the protocol and the measurement, not any
single run. As models improve at introspection, the same mechanism yields sharper
agent-era counter-priors — the catalogue thesis, applied to the agent's *own*
production rather than the training corpus it inherited.

## See also

- [Counter-prior catalogue](../counter-priors/INDEX.md) — where promoted entries land
- [Model-driven failure modes](model-driven-failure-modes.md) — MDF-14 is the home mode; its five-question rubric is the promotion gate
- [ADR-0027](../adr/0027-no-polymorphic-ref.md) — the four-question interrogation that is this protocol's structural ancestor
- [Research: predicting task context from a code graph](../research/context-bounds-prediction.md) — an empirical spike motivated by this programme's "bounded context" finding
