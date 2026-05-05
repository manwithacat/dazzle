# Suite Distillation Strategy

> Agent instruction file for auditing and distilling the Dazzle test suite.
> The goal is **not** to grade tests but to recover the minimal suite that preserves the same protective properties — and to produce documentation as a side-effect.

-----

## 0. Framing

The current suite has accreted organically under agent-driven development. Test count is high (~14k) and the suite is, in practice, preventing drift. That is the strongest signal we have. However, raw count is uninformative on its own: a suite of 14k can be doing the work of 3k or of 30k, depending on how the tests are shaped.

This document defines the epistemology we use to reason about the suite, the taxonomy we sort tests into, and the four-pass process the agent runs to produce actionable outputs.

The verb is **distil**, not **audit**. We are reducing to essence, not grading.

-----

## 1. The dimensions that matter

Coverage answers “did this line execute?” — necessary but vacuous. The dimensions that actually matter:

1. **Specificity** — does the test pin down the contract, or just exercise the code? Asserting non-null is too loose; asserting on entire serialised output is too tight. The target is asserting on the properties callers actually rely on.
1. **Independence from implementation** — could you swap the implementation for an equivalent one and have the test still pass? If yes, the test is behavioural. If no, it is implementation-shaped, and it is the principal source of refactor friction.
1. **Fault localisation** — when the test fails, does the message point at a single suspect? Tests that exercise many components and assert on a final output fail uninformatively.
1. **Redundancy class** — for a given behaviour, how many tests fail when it breaks? Zero is bad. One is ideal. Twenty is bloat — the failures stop adding information after the first one, and every legitimate change becomes twenty units of busywork.
1. **Mutation sensitivity** — if you flipped a `>` to `>=`, deleted a branch, or returned a default instead of the computed value, would *some* test catch it? This is the gold-standard measure of whether the suite is doing real work.
1. **Cost** — wall-clock time, flake rate, attention-cost-per-failure. A 4-second test that flakes 1% of the time taxes every PR regardless of assertion quality.

The headline metric we care about is **mutation kill rate per CPU-second**. Adding a redundant test moves the denominator without moving the numerator; that is what disciplines suite sprawl.

-----

## 2. Test archetypes

Every test in the suite sorts into one of these. The agent’s first job is to label each test with its archetype.

| Archetype                   | Description                                                  | Verdict                                                      |
| --------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------ |
| **Contract test**           | Asserts on documented or stable behavioural properties       | Keep                                                         |
| **Regression pin**          | Exists because of a specific bug; narrow assertion on the broken behaviour | Keep, tag with originating issue                             |
| **Smoke test**              | Asserts only that something doesn’t throw                    | Keep as canary; never the *only* test for a behaviour        |
| **Implementation mirror**   | Re-encodes the implementation in assertion form              | Rewrite as contract test, or delete                          |
| **Snapshot / golden**       | Structural equality against stored output                    | One bit of signal each; audit for inflation                  |
| **Tautology**               | Asserts things true by construction (e.g. asserts on the value just passed in) | Delete                                                       |
| **Parametric cluster**      | N tests of the same shape with different inputs              | Collapse to property test or `it.each`                       |
| **Belt-and-braces cluster** | Same behaviour asserted at multiple layers (unit + integration + e2e) | Audit; keep only where the layers test genuinely different concerns |

Every test in the inventory must carry an archetype tag, a confidence score, and a rationale.

-----

## 3. The four-pass process

Each pass is independently valuable. Run them in order; do not block later passes on earlier ones being perfect.

### Pass 1 — Static classification

**Goal:** label every test with its archetype.

**Method:** read each test file. Classify based on:

- Assertion shape (count, type, what is being asserted on)
- Fixture complexity
- Test name semantics
- Whether the test imports the implementation directly vs only its public interface

**Output:** `tests/audit/classification.json` — a list of `{test_id, file, archetype, confidence, rationale}`. No execution required.

**Success criterion:** the proportion of tests in each archetype is now known. Tautologies and obvious implementation mirrors are flagged for deletion in a follow-up PR.

### Pass 2 — Redundancy clustering

**Goal:** identify tests asserting the same thing.

**Method:** group tests by:

- The function or module under test
- The shape of the assertion (semantic, not syntactic — use embeddings on the assertion body plus the call path)
- The input class (empty, boundary, typical, exceptional)

Two tests that both end up asserting “empty input produces empty output” against the same function are in the same redundancy class.

**Output:** `tests/audit/redundancy.json` — clusters with size > 1, ranked by cluster size. Each cluster carries a recommendation: `merge`, `parametrise`, `keep_all` (with reason).

**Success criterion:** clusters of 5+ are individually reviewed. Most should collapse to single parametric tests.

### Pass 3 — Mutation sampling

**Goal:** find real coverage holes, not coverage-percentage holes.

**Method:** do **not** run mutation testing on the whole codebase. It is quadratic and slow. Instead:

1. Identify the 50 most architecturally load-bearing modules (by fan-in, by churn, by criticality — agent picks based on call graph and git history).
1. Run mutation testing only on those (e.g. `mutmut`, or hand-rolled mutation operators for the framework-specific code).
1. For each surviving mutant, the agent either:
- Writes a test that would catch it, or
- Documents why the mutant is acceptable (equivalent mutant, or behaviour genuinely unspecified).

**Output:** `tests/audit/mutation_report.md` — surviving mutants per module, with proposed tests or written justifications.

**Success criterion:** mutation kill rate on the audited modules is known and tracked. Real gaps have proposed fixes.

### Pass 4 — Contract extraction

**Goal:** produce module-level contracts as documentation, then cross-reference against tests.

**Method:** for each module, the agent:

1. Reads the implementation and existing tests.
1. Produces a written contract in plain language: the properties the module guarantees (preconditions, postconditions, invariants, error behaviour).
1. Cross-references the contract against the tests:
- Which contract clauses are tested?
- Which clauses are not tested? (gap)
- Which tests do not correspond to any clause? (either undocumented behaviour, or bloat)

**Output:** `docs/contracts/{module}.md` per module, plus `tests/audit/contract_coverage.json` mapping clauses to tests.

**Success criterion:** every load-bearing module has a contract document. The repo now contains structured documentation that did not exist before.

-----

## 4. Outputs

The audit produces five artefacts. Treat them as the canonical deliverables.

1. **Taxonomy report** — what kinds of tests we have, in what proportion. Single-page summary.
1. **Redundancy report** — what could be merged or deleted without loss of protection.
1. **Gap report** — surviving mutants imply real coverage holes; this is the list.
1. **Contract documents** — one per load-bearing module. Permanent documentation.
1. **Delta proposal** — concrete PR-sized changes. Each PR must either reduce test count without reducing mutation kill rate, or increase mutation kill rate without proportional CI-cost increase. Ideally both.

-----

## 5. Metrics to track

Replace `count(tests)` and `coverage_pct` with:

- **Mutation kill rate per CPU-second** — protection per unit of CI cost. The headline metric.
- **Mean cluster size** — average redundancy class size. Lower is better; bounded below by 1.
- **Implementation-mirror ratio** — fraction of tests classified as implementation mirrors. Should trend toward zero.
- **Contract coverage** — fraction of contract clauses with at least one corresponding test. Should trend toward 1.
- **Flake rate per 1k runs** — independently tracked; high flake rate poisons the signal of every other metric.

`count(tests)` is fine to track as a sanity check, but it is not the goal variable. A successful distillation may *reduce* the count while increasing protection.

-----

## 6. Feedback into future agent runs

The outputs of this process must themselves be checked into the repo and consumed by future agent runs. The pattern mirrors `CSS_MIGRATION.md`:

- `docs/contracts/{module}.md` — read by any agent writing tests for that module. New tests must correspond to contract clauses.
- `tests/audit/classification.json` — read by any agent generating new tests, to avoid producing more of the archetypes already flagged for deletion.
- `tests/audit/redundancy.json` — read before adding a test; if the proposed test falls into an existing redundancy class, prefer extending the parametric set.

This closes the loop: the next 14k tests do not accrete in the same shape, because the agent writing them has the taxonomy in context.

-----

## 7. Sequencing

For a first run on the Dazzle suite:

1. Pass 1 on the whole suite. Cheap. Produces the taxonomy report and a flagged-for-deletion list.
1. Delete obvious tautologies and implementation mirrors in a single PR. Re-run the suite to confirm no behavioural regression.
1. Pass 2 on the whole suite. Produces the redundancy report. Collapse the largest clusters first.
1. Pass 4 on the top 20 load-bearing modules. Produces contract documents and reveals the highest-value gaps.
1. Pass 3 on the same 20 modules. Confirms or refutes the gaps surfaced by Pass 4.
1. Establish the metric dashboard. Re-run Passes 1–3 quarterly.

Pass 4 before Pass 3 is deliberate: contract extraction often surfaces obvious gaps without needing mutation testing, and the contracts make the mutation-testing output more interpretable when you do run it.

-----

## 8. What this is not

- **Not a coverage push.** Coverage is a lagging proxy and we are not optimising for it.
- **Not a deletion exercise.** Some passes will *add* tests where mutation testing reveals genuine gaps.
- **Not a one-off.** The metrics dashboard is permanent; the passes are re-runnable.
- **Not a substitute for human review.** The agent classifies and proposes; humans approve PRs that delete or merge tests. Deletions are higher-stakes than additions and warrant the friction.
