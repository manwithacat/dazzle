# Do agent-written code biases persist across model generations?

*An empirical investigation, June 2026.*

## Abstract

If agentic code production has predictable construct-level biases, a sharp
question follows: does a newer, more capable model **shed** them, or do they
**persist**? A construct a better model fixes on its own needs no permanent
inoculation; one that survives — or worsens — across generations is a structural
prior worth correcting. We test this on a codebase that is almost entirely
agent-generated across four real model generations (Claude Opus 4.5 → 4.6 → 4.7 →
4.8), attributing every diff to its authoring model via the commit trailer, and
measuring construct *introduction* rates per 1,000 added lines. The result is a
clean four-way taxonomy — **model-shed**, **substrate-held**, **disciplined-rise**,
and **campaign-noise** — and a reassuring headline: **no measured construct gets
worse with newer models.** The one construct that *looked* model-amplified (rising
`# noqa`) acquits on inspection — the rise is entirely in the *disciplined*
targeted form, with zero blanket suppressions in any generation. That acquittal is
the same convict/acquit discipline the [self-reflection
programme](../architecture/agent-self-reflection.md) applies to code, now applied
to the temporal axis.

## Motivation

The [agent self-reflection programme](../architecture/agent-self-reflection.md)
proposed *epoch stratification* as the falsifiable test for whether a flagged
construct is a real prior: measure its prevalence across model generations *in one
codebase under one instruction set*. Persistence implies a structural bias;
disappearance implies a weak-model tic the field has already moved past. This note
runs that test.

## Method

This repository records the **authoring model in each commit's `Co-Authored-By`
trailer**. That is the key enabler — and the reason naive date-bucketing is wrong:
the model generations **overlap in calendar time** (4.6 and 4.7 were both in use
across an overlapping window), so epoch must be attributed by *trailer*, not date.

A single streaming pass over the full `.py` diff history
([`epoch_stratify.py`](scripts/epoch_stratify.py)) attributes each commit to its
model, counts construct **introductions** in added (`+`) lines via regex, and
normalises per 1,000 added lines (controlling for the very different volumes each
model produced).

**Sample** (Opus line only — the cleanest progression):

| model | commits | added .py lines |
|---|---|---|
| 4.5 | 473 | 234k |
| 4.6 | 2,359 | 383k |
| 4.7 | 834 | 145k |
| 4.8 | 710 | 90k |

## Results

Construct introductions per 1,000 added `.py` lines:

| construct | 4.5 | 4.6 | 4.7 | 4.8 | pattern |
|---|---|---|---|---|---|
| `todo_marker` (TODO/FIXME/XXX) | 0.179 | 0.010 | 0.007 | **0.000** | **model-shed** ↓ |
| `broad_except` (`except:` / `except Exception:`) | 0.705 | 0.985 | 0.695 | 0.653 | **substrate-held** → |
| `noqa_blanket` (`# noqa`, no code) | 0.000 | 0.000 | 0.000 | 0.000 | absent throughout |
| `noqa_targeted` (`# noqa: CODE`) | 0.598 | 0.721 | 1.011 | **2.137** | disciplined-rise ↑ |
| `type_ignore` | 0.650 | 1.763 | 1.631 | 0.786 | campaign-noise ∿ |
| `mock_interact` (assert-on-mock) | 0.150 | 0.522 | 0.310 | 0.199 | campaign-noise ∿ |

### The four patterns

- **Model-shed — `todo_marker` declines monotonically to zero.** Opus 4.5 left
  TODO/FIXME markers at 0.18/kline; by 4.8 it leaves essentially none. Newer models
  punt with markers far less. (A convention shift can't be fully excluded — there
  is no hard TODO-ban gate — but the smooth four-point decline is consistent with
  model behaviour, not a step-change rule.) **A construct that self-corrects across
  generations does not need a permanent counter-prior.**

- **Substrate-held — `broad_except` stays flat** (~0.65–0.99) regardless of model.
  The project has a gate (`test_no_bare_except_pass`) for exactly this construct;
  the flatness is the gate doing its job — the *substrate*, not the model, sets this
  floor. This is the inoculation thesis working as designed.

- **Disciplined-rise — `noqa` rises 3.6×, but it acquits.** Targeted `# noqa: CODE`
  climbs 0.60 → 2.14 across generations. Taken alone, that reads as a model-amplified
  anti-pattern (suppress the linter rather than fix the code). But the
  blanket-vs-targeted split is decisive: **blanket `# noqa` is zero in every
  generation; the entire rise is the disciplined, single-rule form.** Targeted
  suppression with a named code is the *correct* way to silence a specific rule when
  justified — not an anti-pattern. The apparent regression dissolves on the
  principled distinction.

- **Campaign-noise — `type_ignore` and `mock_interact` rise-then-fall**, peaking at
  4.6, returning to baseline. Non-monotonic, tracking project-wide campaigns (a mypy
  push) rather than model generation.

### The headline

Across every construct measured, **none gets monotonically worse with newer
models.** The patterns are: a construct newer models *shed* (todos), a construct
the *substrate* holds flat (broad-except), a rise that is entirely *disciplined*
(targeted noqa), and *campaign* noise. The substrate sets the floor; the models, if
anything, raise the ceiling.

### The methodological moment

The rising-`noqa` acquittal is the point of the study, not a footnote. A crude
construct count flagged an apparent model-amplified anti-pattern; a single
principled split (blanket vs targeted) acquitted it. This is *exactly* the move the
[self-reflection dialectic](../architecture/agent-self-reflection.md) makes on
code — and it was just as necessary on the epoch data. Measuring construct counts
without the convict/acquit discipline would have manufactured a false finding.

## Limitations

- **Calendar confound.** Models overlap in time, and a later-used model faces a
  later (stricter) lint ruleset on average — so the *targeted*-noqa rise is
  confounded with ruleset growth. The robust finding (blanket = 0) is immune to
  this; the headline (no construct worsens) does not depend on the noqa magnitude.
- **Introductions, not standing prevalence.** We count added-line introductions in
  diffs; a construct introduced and later removed still counts.
- **Approximate regexes.** `broad_except` misses `except X as e:` (conservative
  undercount); these are screening patterns, not a type-aware analysis.
- **Volume skew.** 4.8's sample (90k lines) is ~4× smaller than 4.6's; single-point
  bumps are less trustworthy than monotonic four-point trends.
- **One codebase, one instruction set, one author's workflow.** This is a
  *within-substrate* measurement, not a claim about agentic coding at large.

## Conclusion

The epoch axis is measurable and genuinely discriminating: with real model labels
from commit trailers, it separates model-shed, substrate-held, disciplined, and
campaign-driven constructs. On this substrate, the answer to "do agent-written code
biases persist across model generations?" is, for every construct measured: they do
not worsen — the substrate holds the floor and newer models improve on their own
(TODO markers vanish). And the one apparent counter-example acquitted under the same
adversarial discipline the broader programme uses on code. The constructs that would
most justify a permanent counter-prior are the *model-amplified* ones — and on these
axes, in this substrate, none were found. That is a quietly important result: it is
evidence that a substrate of gates plus instructions, paired with improving models,
keeps construct-level quality stable across generations rather than letting it drift.

## Reproduce

```bash
python docs/research/scripts/epoch_stratify.py
```

Self-contained (stdlib only); attributes by commit trailer and derives the repo
root from its own location.
