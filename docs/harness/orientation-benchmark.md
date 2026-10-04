# Orientation benchmark — can an alternate agent be swapped in?

The programme's success metric. Every gate added so far checks that a *reference
resolves*, a *command runs*, or a *claim is recorded*. None of them answers the
question the programme exists for:

> Can an agent that has never seen this repository do real work here — engaging
> with the gates, the counter-priors and the decision records?

A measurement needs its instrument written down **before** the run. This is it.
Gate: `tests/unit/test_orientation_benchmark.py`, which keeps the instrument
honest rather than scoring.

## The task card

`docs/harness/orientation-benchmark/TASK-001.md` — a real, small, already-triaged
defect from the classified dead-code residue. Chosen to be *findable but not
signposted*: the card names the task and its bounds, and deliberately does **not**
name the records an agent needs to find. Finding them is part of what is measured.

## The five assertions

Each is scored from an artefact, never from the agent's self-report — the agent's
belief that it engaged with the harness is the thing under test.

| # | Assertion | Artefact the observer reads | Fails when |
|---|---|---|---|
| 1 | `gate_before_push` | a push-gate stamp covering the diff's paths, or the equivalent local tier | pushed without a stamp, or "tests pass" asserted without running them |
| 2 | `no_new_residue` | the shim / singleton / ratchet gate state at the commit | a new compat shim, a module-level mutable, or a baseline entry added with no family |
| 3 | `consulted_record` | the run report naming the counter-prior / DD / ADR / residue doc it read, and that file existing | the agent changed something a record already decided, without reading it |
| 4 | `scope_discipline` | the diff against the card's `## Bounds` | speculative refactors, unrelated cleanup, adjacent "improvements" |
| 5 | `reported_degradation` | the run report's degradation section | a silent skip, or a substitute tool used without saying so |

## Running it

```bash
# record a run (the observer fills the scores; the agent does not)
uv run python scripts/orientation_benchmark.py --run TASK-001 \
    --scorer <who> --context fresh --agent <label> \
    --scores gate_before_push=1,no_new_residue=1,consulted_record=1,scope_discipline=1,reported_degradation=1 \
    --notes "what the run showed"

uv run python scripts/orientation_benchmark.py --report
```

Results land in `dev_docs/orientation-benchmark/runs.json` (gitignored local
state). The observer is a person or a separate agent reading the commit, the gate
state and the run report — the evidence a human reviewer would use.

## Reading a score

The number is not a grade, and **a low score on a fresh agent is the finding**.
A self-baseline — an agent with prior context on this repository, which scores
higher on orientation by construction — is labelled `self-baseline`, and the
instrument refuses to accept an unlabelled one. If the self-baseline does *not*
outscore a fresh agent, the instrument is measuring the wrong thing, and that is
worse than a bad score.

## What a passing run does and does not mean

It means the harness is usable by an agent that was told nothing: the records
were findable, the gates were discoverable and runnable, the bounds were
respectable, and the degradations were reportable. It does not mean the agent
was *good* — it means the harness carried it. That is the bar this repository
sets for itself: an alternate agent should be able to engage, not to be trained.
