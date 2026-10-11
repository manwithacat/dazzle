# Fuzz-found Parser Crash — `foreign_model` Constraint Kind (Catch Report)

!!! info "📜 Historical snapshot — not current docs"
    Captured **2026-06-07**. It records a single fuzz-testing catch and the harness
    evaluation it prompted; **it may not describe current behaviour.** Start from the
    [documentation home](../index.md). The durable references are the parser-fuzz suite
    (`tests/unit/test_parser_fuzz.py`) and the counter-prior on exceptions-as-control-flow.

**Date:** 2026-06-07
**Shipped in:** v0.81.83 (fix committed separately from the SAML feature it surfaced under)
**Fixed file:** `src/dazzle/core/dsl_parser_impl/service.py`
**Found by:** `tests/unit/test_parser_fuzz.py::TestMutatedCorpusNeverCrashes::test_swap_adjacent_mutation`

## One-line summary

The Hypothesis-based parser fuzz suite caught a real, pre-existing parser-robustness bug —
an invalid `foreign_model` `constraint <kind>` raised a raw `ValueError` from an enum
constructor instead of a clean `ParseError` — while it was run as part of an *unrelated*
feature's pre-ship gate. The infrastructure did exactly what it exists to do.

## What the bug was

`parse_foreign_model` (`service.py`) read the constraint-kind token and passed its value
straight into the IR enum:

```python
constraint_kind_token = self.expect(TokenType.IDENTIFIER)
constraint_kind = ir.ForeignConstraintKind(constraint_kind_token.value)  # ← raises ValueError
```

For any value not in `ForeignConstraintKind`, `Enum.__call__` raises `ValueError`. The parser
contract is: **only `ParseError` may escape `parse_dsl`** (every other exception is a crash).
So a single malformed token in a `foreign_model` block crashed the parser instead of producing
a diagnostic. The sibling `kind:` path (`DomainServiceKind`) already had the correct
try/except → `make_parse_error` guard; the `constraint` path was simply missing it — a
copy-omission, not a design flaw.

This is a textbook instance of the **exceptions-as-control-flow** counter-prior: a library
enum's exception leaking through a boundary that promised a typed error.

## How the fuzzer found it

`test_parser_fuzz.py` is a property suite: *"a mutation of valid DSL produces `ParseError` at
worst, never a crash."* It loads a corpus of real example DSL files, then applies structural
mutators (`insert_keyword`, `delete_token`, `swap_adjacent_tokens`, `duplicate_line`,
`inject_near_miss`) parameterised by a Hypothesis-drawn integer seed:

```python
@given(st.integers(min_value=0, max_value=5000))
@settings(max_examples=50, ...)
def test_swap_adjacent_mutation(self, seed):
    source = corpus[seed % len(corpus)]
    mutated = swap_adjacent_tokens(source, seed=seed)
    _safe_parse(mutated)   # asserts: only ParseError, never another exception
```

The `swap_adjacent_tokens` mutator swapped two adjacent tokens in a real `foreign_model`
block from `examples/pra/dsl/services.dsl`, turning a line like
`constraint batch_import webhook_url="…"` into one where the constraint kind read as
`webhook_url`. `ForeignConstraintKind("webhook_url")` → `ValueError` → escaped `_safe_parse` →
test failure.

## The most interesting part: *where* it surfaced

This bug was **not** found by a dedicated fuzz run. It surfaced during the **pre-ship full
test suite** for an unrelated change (SAML SP-signed AuthnRequests, #1342 cluster 2/4). Two
facts made that possible, and both are worth keeping:

1. **The pre-ship gate runs `pytest tests/ -m "not e2e"` — the whole suite, not a narrow
   slice.** The fuzz suite rode along. A narrower "just the auth tests" gate would have
   shipped green and missed it.
2. **Hypothesis explores; it is not a fixed corpus.** The same suite had passed in CI for the
   immediately-preceding release (v0.81.82) — CI's 50 examples simply hadn't drawn the seed
   that hits this corpus file + mutation. The local run drew it, then pinned it in
   `.hypothesis/` (hence it reproduced deterministically on re-run). **CI green ≠ no bug** for
   a sampling fuzzer; a different run can find what a prior run missed.

The honest read: it was found by **luck of exploration**, made *capturable* by **broad gate
scope** and **deterministic replay**. The infrastructure converts luck into a durable
regression test — but only because the gate was wide enough to run it.

## The fix

Mirror the `DomainServiceKind` guard exactly:

```python
constraint_kind_token = self.expect(TokenType.IDENTIFIER)
try:
    constraint_kind = ir.ForeignConstraintKind(constraint_kind_token.value)
except ValueError as exc:
    valid = ", ".join(k.value for k in ir.ForeignConstraintKind)
    raise make_parse_error(
        f"Invalid foreign constraint kind '{constraint_kind_token.value}'. Valid kinds: {valid}.",
        self.file, constraint_kind_token.line, constraint_kind_token.column,
    ) from exc
```

Plus a focused regression test in `test_parser.py`
(`test_invalid_foreign_constraint_kind_raises_parse_error`) so the property is pinned by an
example, not only by the sampling fuzzer.

## Lessons

- **Keep the pre-ship gate wide.** The catch depended on the full-suite gate, not a
  feature-scoped one. The recurring temptation to narrow the pre-ship slice for speed would
  have let this through. (See the pre-ship-test-scope guidance.)
- **A green CI fuzz run is not proof of absence.** For sampling fuzzers, treat a pass as "no
  bug in *this* draw." The value compounds across runs precisely because each run draws new
  inputs.
- **Every enum-from-token in the parser is a suspect.** This was the second occurrence of the
  same shape (after `DomainServiceKind`). A lint/audit for `ir.<Enum>(token.value)` without a
  surrounding try/except would pre-empt the third.
- **The fuzzer is only as good as its corpus + mutators + oracle.** It found this because the
  corpus contained a `foreign_model` block with a `constraint … key=value` line *and* a
  mutator that swaps adjacent tokens *and* an oracle that asserts the `ParseError`-only
  contract. Widening any of those three widens what the fuzzer can find — which is the subject
  of the companion evaluation,
  [Giving Fuzz Testing More To Work With](../proposals/fuzz-harness-leverage-evaluation.md).
