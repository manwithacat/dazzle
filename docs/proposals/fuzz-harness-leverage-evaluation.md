# Giving Fuzz Testing More To Work With — Evaluation

**Date:** 2026-06-07
**Prompted by:** the fuzz catch in [2026-06-07-fuzz-catch-foreign-constraint-kind](../history/2026-06-07-fuzz-catch-foreign-constraint-kind.md) (a real parser bug the Hypothesis suite found during an unrelated pre-ship run).
**Companion to:** [Suite Distillation Strategy](./Suite%20Distillation%20Strategy.md).
**Status:** evaluation + prioritised menu. No code yet — pick the slices to build.

## The hypothesis under test

> Fuzzing works best on well-parameterised tests. It may be worth using test distillation
> to consolidate and optimise our test structures to support fuzzing.

**Verdict: correct, with one important sharpening.** "Well-parameterised" is necessary but
not sufficient. The fuzzable unit is a **property** — an *input space* mapped to an
*invariant* — not merely a test that takes arguments. A `@pytest.mark.parametrize` with five
hand-picked cases is parameterised yet un-fuzzable: its inputs are a fixed finite set. The
fuzzable form is `@given(st.<space>)` + an invariant the fuzzer can re-check on inputs nobody
hand-wrote. So the refinement is:

> Distillation should turn **clusters of same-shape example tests** into **property tests**,
> and a cluster is fuzzable only when its inputs are a *sample of an (infinite) space*, not an
> enumerable set.

## Where we are (grounded in the code)

**The fuzz harness is real and mature — for exactly one surface.** `src/dazzle/testing/fuzzer/`
is a full kit: a corpus loader (valid example `.dsl` files), six structural mutators
(`mutator.py`), an LLM near-miss generator (`generator.py`, Haiku), a subprocess oracle
(`oracle.py`, classifies VALID / CLEAN_ERROR / BAD_ERROR / HANG / CRASH), a campaign runner,
and a report. `tests/unit/test_parser_fuzz.py` drives it via Hypothesis. There's also a JS
runtime fuzzer (`fuzz_runtime/`) and strong JWT property tests (`test_jwt_fuzzing.py`).

**But property-based testing is a rounding error of the suite.** Of ~12,265 test functions
(`tests/audit/taxonomy_report.md`), Hypothesis appears in ~5 files / ~58 `@given` sites
(<<1%). 84.7% are "contract" example tests; only 3.4% (422) are `parametric_cluster`. The
parser is deeply fuzzed because it is the **one** subsystem expressed as a crisp property
("only `ParseError` escapes `parse_dsl`") *with* a corpus *and* mutators. Everywhere else the
fuzzer has nothing to grab: the behaviour is pinned example-by-example.

**The distillation tool already finds the raw material — it just doesn't name it.**
`scripts/distill/cluster.py` groups tests by `(file, class, assertion-shape)` and reports
(`tests/audit/redundancy_report.md`) **853 clusters of ≥3, 3,028 tests in clusters, ~2,175
collapsible (~15% of the suite).** A cluster of N tests with the *same assertion shape over
different inputs* is the fingerprint of a latent property test. But:

- `classify.py` has **no `property_based` archetype** — `@given` tests are statically
  indistinguishable from example tests, so we can't even *measure* the property ratio.
- `cluster.py` ranks clusters by size but **doesn't recommend parametrize vs property vs
  fuzz** — it can't tell "5 finite cases" from "5 samples of an infinite space."

So the loop the hypothesis describes — *distill clusters → property tests → fuzz targets* — is
**not closed**. Closing it is the highest-leverage move.

## The leverage model

Fuzz yield is the product of four factors. We have invested almost entirely in one (mutators).

| Factor | What it is | Parser today | Lever |
|--------|-----------|--------------|-------|
| **Surface** | # subsystems expressed as input→invariant | 1 (parser) | **Largest untapped lever** — most input-shaped code has only example tests |
| **Corpus** | seed diversity | example `.dsl` files | broaden (fixtures, generated, failing inputs) |
| **Mutators** | input perturbations | 6 + LLM | already strong |
| **Oracle** | invariants checked | "no crash / no hang" | **weak** — round-trip / idempotence / error-shape find deeper bugs |

The catch that prompted this (a token→enum `ValueError`) was found by the *weakest* oracle
("no crash") on the *one* fuzzed surface. Widening **surface** and strengthening **oracles** is
where the next bugs are.

## Recommendations (prioritised menu)

### 1. Close the distillation→property loop (the hypothesis, made real) — *high leverage, low cost*
- **1a. Add a `property_based` archetype to `classify.py`** (detect `@given` on the decorator
  list, exactly as `_parametrize_n` already detects `@pytest.mark.parametrize`). Now we can
  *measure* property-vs-example ratio and track it as a distillation metric (the strategy doc
  already wants metrics). ~1 file, mechanical.
- **1b. Add a refactor recommendation to `cluster.py`**: per cluster, classify the input space
  as *enumerable* (→ `@pytest.mark.parametrize`) vs *sampled-from-a-space* (→ `@given` property
  / fuzz). Heuristics from the data we already extract: assertion shape uniformity + whether
  the varying inputs are literals from a small set vs free-form strings/dicts. Output a
  `recommended_form` per cluster in `redundancy.json`. This turns the existing 2,175-test
  backlog into a *ranked worklist of fuzz-target candidates*.

### 2. Strengthen the parser oracle — ✅ DONE (v0.81.88)
Today's property was "never a non-`ParseError`." Added invariants that catch *wrong*
behaviour, not just crashes:
- **Error well-formedness:** ✅ `_safe_parse` now asserts every `ParseError` carries a
  line/column AND a non-empty message. Immediately caught **41 location-less errors** from the
  leaf `parse_duration` helper → fixed by threading the parser through (9 sites).
- **Determinism:** ✅ `TestParserDeterminism` — parse twice → same outcome.
- **Round-trip stability:** ❌ not feasible — Dazzle has no IR→DSL emitter (DSL→IR only), so
  `parse → emit → parse` can't be expressed. (Would require building a DSL serializer first.)

### 3. Open new fuzz surfaces — the small, strong-invariant parsers we *just wrote* — ✅ DONE (v0.81.87)
Each is self-contained, has a crisp invariant, and currently has only example tests. These are
the cheapest new surfaces and several are security-relevant. **All six now have Hypothesis
property tests** (`tests/unit/test_fuzz_small_parsers.py`); fuzzing them found and fixed a
`parse_grace_duration` `OverflowError` leak and three `parse_group_patch` crashes:
- `saml_metadata.parse_idp_metadata_xml` — arbitrary XML → dict or `SamlMetadataError`, **never
  a raw exception, never a hang** (XXE/oversize already delegated, but the property pins it).
- `saml_metadata.validate_metadata_url` — arbitrary URL → the SSRF invariant holds (no private
  IP ever passes); fuzz the URL space against the IP/scheme guard.
- `secret_rotation.parse_grace_duration` and the DSL duration lexer — arbitrary string →
  `timedelta`/int or `ValueError`, never crash.
- `scim_provisioning.parse_group_patch` — arbitrary dict → list or `ValueError`.
- `connection_crypto` — round-trip (`decrypt(encrypt(x)) == x`) over random bytes; tamper
  detection never false-negative.
- the **scope predicate algebra** — arbitrary predicate string → compiles or raises cleanly.

### 4. Pre-empt the *specific* bug class — *low cost, mechanical* — ✅ DONE (v0.81.86)
The catch was the **second** `ir.<Enum>(token.value)` site to leak `ValueError` (after
`DomainServiceKind`). An audit found **20 unguarded sites** (only 7 of 27 were guarded) —
each a latent fuzz-discoverable crash. Resolved structurally (the "altitude" fix):
a shared `BaseParser.enum_from_token(ir.<Enum>, token)` helper does the try/except →
`make_parse_error` once; all 20 unguarded sites migrated to it; and a gate
(`tests/unit/test_no_unguarded_enum_from_token.py`) fails on any new unguarded
`ir.<Enum>(token.value)` — allowlist-free (the migration drained it to zero).

### 5. Make the fuzz signal compound — ✅ DONE (v0.81.89)
- **Scheduled campaign + regression corpus.** `report.write_seed_files` persists every
  CRASH/HANG input (content-hash-deduped) and `dazzle sentinel fuzz --save-seeds <dir>`
  exposes it. A nightly workflow (`.github/workflows/fuzz-nightly.yml`, 05:00 UTC +
  `workflow_dispatch`) runs the mutate-layer campaign, goes RED on a catch, and uploads the
  report + seeds as an artifact (it deliberately does **not** write back to the repo). An
  operator promotes worthwhile seeds into `tests/unit/fuzz_seeds/`, replayed on every CI run
  by `test_fuzz_seed_regressions.py` (each must raise a *well-formed* located `ParseError`,
  never a raw crash) — so each catch becomes a permanent regression.
- **Mutation kill-rate.** Started as `scripts/mutation_poc.py`, now graduated to
  `dazzle sentinel mutate` (engine `src/dazzle/testing/mutation/`) with an enforced
  `--suite security` gate — see `docs/proposals/mutation-audit-findings.md`. A dependency-free,
  token-level mutation harness (mutmut 3.x's `mutants/`-dir pytest invocation is incompatible
  with this repo's config/conftest — `BadTestExecutionCommandsException`). It swaps operators/keywords
  at the *token* level (strings/docstrings/comments never mutated) and reports killed /
  survived / kill-rate. On `saml_metadata.py` it scored **86%** (12/14) — and the run *paid
  for itself*: a survivor flagged the untested size-cap boundary (`>` vs `>=`), which we
  pinned with a new test, lifting the rate from 79% → 86%. The 2 remaining survivors are a
  cosmetic error-message fallback and an untested explicit-port path. This is the strategy
  doc's headline metric, now measurable on demand.

## Suggested first slice

**1a + 1b + 4** together are small, mostly mechanical, and directly serve the stated goal:
they make distillation *name* fuzzable clusters and turn the 2,175-test redundancy backlog
into a ranked fuzz-target worklist, while #4 closes the exact bug class that prompted this. **3**
(new parser surfaces) is the highest-yield follow-on and a natural fit for the per-feature
ship rhythm — each new parser gets a property test the day it lands. **2** and **5** deepen the
parser surface we already trust.

A caution worth keeping (per `docs/architecture/model-driven-failure-modes.md`): a fuzz target
is only as honest as its oracle. "No crash" is a real but shallow guarantee; the durable wins
come from oracles that encode *correctness* (round-trip, idempotence, invariant preservation),
which is also what makes a collapsed property test stronger than the example cluster it
replaced — not just smaller.
