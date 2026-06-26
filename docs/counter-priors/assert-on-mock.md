---
id: assert_on_mock
name: Assert-on-mock (a test that cannot fail)
layer: inference
status: active
summary: >-
  A test whose assertions verify the mock rather than the behaviour — asserting
  the value the mock was told to return, asserting only that a call happened when
  a value was the contract, or mocking the very unit under test. It goes green by
  construction and stays green when the real behaviour breaks: a non-test wearing
  a checkmark. The flaw is not mocking (isolating a real boundary is correct and
  necessary); it is asserting on the mock instead of on behaviour the real code
  produced.
triggers_text:
  - "write a test"
  - "unit test"
  - "mock the"
  - "patch the"
  - "add test coverage"
  - "assert it was called"
  - "test that it calls"
triggers_code:
  - 'assert_called(_once|_with|_once_with)?'
  - '\.return_value\s*='
  - 'assert\s+\w+\.return_value'
refs:
  adrs: []
  memories: []
  pr_review_agents: []
  tests: []
detectors: []
---

# Assert-on-mock (a test that cannot fail)

## The corpus prior

This is an **agent-production** prior, and it is measured. Coding agents add mocks
at a higher rate than non-agents (~36% vs 26% of test commits in a 2025–2026
study) and write tests characterised as *observational* — value-revealing, like a
`print` — rather than behaviour-asserting. The mechanism is **local-success
optimisation**: a heavily-mocked test goes green fast and *looks* like coverage,
so the writer optimises the visible signal (the test passes) over the latent goal
(the behaviour is actually verified). The mock-loop tautology is the limit point
of "make it green" pressure.

## Wrong shape

A test with **no failure mode reachable by a real behavioural defect**:

```python
svc.compute = Mock(return_value=42)
assert svc.compute() == 42            # passes by construction — verifies the Mock library
```

and its subtler, more common form — mock a collaborator, then assert *only* that
it was called, with no assertion on any value the unit produced:

```python
loader.fetch = Mock()
process(loader)
loader.fetch.assert_called_once()     # restates the call graph as the spec
```

If the real collaborator's contract breaks, or the unit mishandles the return,
the test stays green. It cannot fail for the reason it exists. Also convictable:
mocking the *unit under test* itself, and implementation-derived snapshots passed
off as correctness assertions (a golden captured *from* the code, never blessed,
used as a feature test).

## Right shape

Mock only genuine boundaries; assert on behaviour the real code produced:

1. Mock at the **seam** — I/O, the clock, randomness, an external service — not
   inside the logic under test.
2. Land every assertion on a value/state the **real code computed** — a return
   value, a state transition, a transformed payload, a raised error.
3. Interaction assertions (`assert_called_*`) are legitimate **only when the
   interaction is itself the specified behaviour** — "on cache miss, hit the store
   exactly once", "retry exactly 3 times", "idempotent: do not re-charge". When a
   *value* is the contract, assert the value.
4. Snapshot/characterisation tests are legitimate when named as such and guarding
   a refactor or output contract against a *blessed* baseline (Dazzle's
   `docs/api-surface/` baselines and schema-snapshot gates are the honest form).

The discriminating question, asked at write time:

> *If I break the real behaviour this test claims to cover — leaving every mock
> exactly as written — does this test go red?* If no, it is the wrong shape.

## Why this matters here

Dazzle stakes its credibility on tests that *prove* behaviour — the conformance
engine, the agent-E2E tiers, the fidelity gates, the RBAC runtime verifier all
exist so that "green" means "the running app does what the DSL says." An
assert-on-mock test imports the one thing those gates are built to exclude: a
green checkmark that proves nothing. It is most dangerous in agent-authored
suites precisely because the agent optimises the visible signal — so the test
that looks like new coverage is the one most likely to be hollow. The legitimate
forms (boundary mocking, parameterised matrices with independently-derived
expecteds, blessed snapshots) are not just allowed but encouraged; the line is
whether a real defect can turn the test red.

**First-party corroboration.** This repo's own (agent-generated) test suite shows
the construct at scale: of ~1,470 test files, ~21% use mocks / `@patch`, with
hundreds of `assert_called*` interaction assertions. Prevalence alone is not
conviction — most are the legitimate forms above — but it confirms the surface
this prior acts on is large here, which is why the discriminating question
("would a real defect turn this red?") is the cheaper guard than auditing after.
