# Predicting task context from a code graph: how far does cheap get you?

*An empirical investigation, June 2026.*

## Abstract

Agentic coding tools fail in predictable ways when the code they need isn't in
the context window — they re-implement helpers that already exist, and edit code
on assumptions the unloaded files would have corrected. This note asks whether a
**pre-flight step** could predict, before a task starts, which code must be in
context. We build a deliberately cheap baseline — a keyword seed resolver plus a
static import-graph closure — and evaluate it on 11 real tasks reconstructed from
this repository's git history (commit subject = task, changed files = ground
truth). The result: a naive keyword seed finds the right file only **45%** of the
time, a forward import closure lifts that to **73%**, and adding **bidirectional**
edges (reverse dependents + siblings) reaches **91%** — all in ~50 lines of
deterministic Python, microseconds per query, no new dependencies and no
graph-native database. The remaining difficulty is not the graph: it is mapping a
natural-language task to an entry point, which is a semantic-retrieval problem.

## Motivation

A companion investigation — [agent self-reflection](../architecture/agent-self-reflection.md)
— found that the *real*, defensible failure modes of agentic code production are
driven by **bounded context**: the agent re-derives a helper because the existing
one isn't in its window (duplication-instead-of-reuse), or it edits against
assumptions an unloaded file would have corrected. That suggests a structural fix:
instead of catching these post-hoc, predict the relevant code *before* the task
and load it on purpose. This note tests how tractable that prediction is.

The problem decomposes into three sub-predictions:

- **(A) Capacity** — will the relevant code fit in the window? Arithmetic, *given*
  the relevant set.
- **(B-i) Missing dependencies** — code the task will modify or call. A graph
  reachability problem.
- **(B-ii) Missing reuse candidates** — existing code the task will needlessly
  re-derive. *Not* a closure problem — the helper you should reuse is, by
  definition, not in your call graph. It's a capability search. Out of scope here;
  it is the harder, higher-value half.

## What the substrate already provided

The host framework (Dazzle) ships a knowledge graph backed by SQLite. Two findings
shaped the spike:

- The schema **already defines** `file:` / `module:` / `class:` / `function:`
  entity types — it anticipates code-symbol granularity — but the default seeder
  populates only a concept/knowledge layer. The code graph was *schema-ready but
  unpopulated*.
- An AST indexer (`auto_populate`) already existed, extracting modules, classes,
  functions, and import / inheritance / (basic) call edges — but wasn't run as
  part of the standard seed.

So roughly 80% of the B-i machinery existed already; the gap was running it and
everything *around* the graph (seeding, relevance).

## Method

Three throwaway prototypes (all in [`scripts/`](scripts/), runnable against the
repo):

1. **Closure + capacity** (`ctx_manifest_proto.py`): given a seed module, compute
   the first-party import closure via `ast` and estimate tokens.
2. **Seed resolver** (`seed_plus_closure_eval.py`): index each module by its
   path-terms and `def`/`class` names; score a task by weighted term overlap;
   rank. Evaluate against ground truth.
3. **Bidirectional closure** (`bidir_eval.py`): add reverse dependents and sibling
   co-imports to the closure.

**Evaluation set:** 11 real tasks from this repo's history. For each, the commit
subject is the task description and the changed `src/**.py` files are ground
truth. We measure *recall* — does the candidate set contain a truly-changed file?

## Results

### The closure explodes without a cut

Full first-party import closure of three representative seed files:

| Seed (task file) | depth-1 | depth-2 | full closure |
|---|---|---|---|
| an HTTP-runtime hub | 8 mod / 35k tok | 26 / 74k | **110 / 382k** |
| a `core.ir` leaf | 1 / 1.4k | — | **1 / 1.4k** |
| a pure-render module | 2 / 10k | 4 / 15k | **4 / 15k** |

The hub's full closure (382k tokens) exceeds a typical context window — naive
"take the closure" fails — but depth-2 (8–26 modules) is the sweet spot. A useful
side effect: **closure size is a free coupling metric.** The pure render layer's
closure is 4 modules; the HTTP hub's is 110, tracking the project's documented
layer architecture exactly.

### The recall ladder

| Step | Recall | Working set |
|---|---|---|
| naive keyword seed (top-3) | **45%** | — |
| + depth-2 forward closure | **73%** | ~31 modules |
| + bidirectional (reverse + siblings) | **91%** | ~49 modules |

- **Seed resolution is weak (45%)** because of a *symptom-vs-cause gap*: task words
  describe where a feature *appears* (a "catalogue" view) but the fix lives in a
  different layer (the orchestration that builds it).
- **The forward closure rescues fuzzy seeds (45% → 73%)** — validating the core
  design: *approximate seed + deterministic closure*, not exact resolution.
- **Bidirectional closure reaches 91%.** Forward closure cannot reach a sibling
  file that merely shares a common importer; adding direct reverse edges plus the
  seed's siblings fixes this. It specifically recovered a real case where the
  resolver picked a plausible sibling (`aggregate_where_parser`) but the fix was in
  `condition_to_predicate` — reachable only via their shared importer.

### What didn't work

Adding content-grep to the resolver improved seed quality but blew the working set
up to 131 modules on a hub case (the relevance cut becomes the binding constraint
once recall rises) *and* still failed to recover the last miss. The one persistent
failure — a task whose vocabulary genuinely doesn't point at the changed file —
survives both keyword and content matching. That is the irreducible
**semantic-retrieval tail**.

## A note on rigour

The first evaluation run reported **0%** — which was a *measurement bug* (a
module-prefix mismatch in the ground-truth comparison), caught because the
closures implausibly collapsed to 3 modules. The corrected numbers are above. We
flag this deliberately: applying "does this measurement measure what I think it
measures?" to one's own evaluation is the same discipline the companion
self-reflection programme applies to code.

## Limitations

- The keyword resolver is a **lower bound** — names only, no content or embeddings;
  a real harness using the agent's own search would beat it.
- **n = 11**, all from one feature arc — directional, not a benchmark.
- A commit subject already contains the fix's vocabulary, so the 45% seed figure is
  likely **optimistic** for a genuinely fresh task.
- Static Python call resolution is approximate under dynamic dispatch; the import
  edges used here are reliable, the call edges less so.

## Conclusion

The graph half is genuinely cheap and effectively solved as a spike: **91% recall
in ~50 lines, deterministic, microseconds, no new dependencies, no graph-native
database** (which would buy nothing at this scale — hundreds of nodes, tiny
closures). The binding constraints from here are both *non-graph*: a token-budget
relevance cut on the candidate pool, and semantic seed retrieval for the last tail.
The original question — "is this a straightforward code-graph problem?" — resolves
to: *the graph part is; the hard part is intent → entry-point retrieval, a
different problem wearing a graph costume.*

## Reproduce

```bash
python docs/research/scripts/ctx_manifest_proto.py    # closure + capacity
python docs/research/scripts/bidir_eval.py            # the full recall ladder
```

Scripts are self-contained (stdlib `ast` only) and derive the repo root from their
own location.
