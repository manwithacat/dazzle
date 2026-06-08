# Mutation-audit findings — security-critical modules (2026-06-08)

Follow-on to the fuzz-harness leverage track. Where fuzzing asks *"does any input crash
this?"*, mutation testing asks *"do our tests actually pin this behaviour, or merely
execute it?"* — it injects a small bug (mutant) and checks whether a test fails. A
**surviving** mutant is behaviour no test constrains; a low **kill-rate** means coverage
without strength. Tool: `dazzle sentinel mutate` (engine in `src/dazzle/testing/mutation/`;
token-level, dependency-free — mutmut 3.x is incompatible with this repo's pytest config).
Run a single module with `dazzle sentinel mutate <module> -t <pytest target>`; run the
enforced security gate with `dazzle sentinel mutate --suite security`.

## Headline

The biggest finding is methodological: **mutation kill-rate measured against unit tests
alone badly understates code whose real safety net is the Postgres enforcement suite.**

| Module | Unit-only | With PG suite | Notes |
|--------|-----------|---------------|-------|
| `back/runtime/rls_schema.py` | **7%** | **60%** | RLS DDL generation — the PG suite does the pinning |
| `back/runtime/predicate_compiler.py` | **35%** | **45%** | scope→SQL compiler |
| `rbac/matrix.py` | 65% | n/a (pure) | static RBAC matrix |
| `back/runtime/csrf.py` | 84% | n/a (pure) | CSRF middleware |
| `back/runtime/auth/connection_crypto.py` | 50% → **83%** | n/a (pure) | secret-at-rest (fixed this round) |

Lesson for any future kill-rate gate: **the test command must include the PG enforcement
tests for the SQL-generation modules**, or the number is meaningless.

## Fixed this round (clear, high-value, security-relevant)

- **`connection_crypto`** (50% → 83%): no test asserted the key/token decoders reject
  non-base64 characters (`base64.b64decode(validate=True)` survivors). A regression
  dropping `validate=True` would silently accept mangled keys. Added two tests feeding a
  stray non-alphabet char. *Residual L57 is an equivalent mutant* — `_decode_key` uses
  `validate=False` by design (lenient rotation key); `test_malformed_old_key_is_skipped`
  shows both variants behave identically.
- **`rbac/matrix`** (65% → 69%): pinned two security inversions —
  `_rule_matches_role`'s `deny_all` guard (flipping it turns an explicit `permit: x: false`
  denial into a permit) and `_condition_matches_role`'s recursive `or` (flipping to `and`
  silently denies a `role(a) or role(b)` gate to everyone).

## Triaged but NOT chased (deliberate — diminishing returns)

Chasing every survivor in already-well-pinned modules is the same trap as crash-fuzzing
the Unicode tail. The remaining survivors are either:

- **Equivalent mutants** (no observable behaviour change): all `@dataclass(frozen=True)
  → frozen=False` (testing Python's immutability, not our logic); error-string formatting
  (`predicate_compiler` L274 "Available FKs" `or`→`and`); assert-message boundary
  (`L668 >=`→`>`).
- **Genuine but lower-value residual gaps** worth a dedicated follow-up, concentrated in
  the scope/RLS compilers even *with* the PG suite:
  - `predicate_compiler` L813 (null-target guard), L833 (`op == "="`), L1105
    (`target == "current_user"`), L690/692 (FK-hop iteration direction/index).
  - `rls_schema` L116/L251 (shared-schema tenancy guard `or`/`!=`), L142/L262/L476
    (`has_scopes` / `access.scopes` boolean logic).
  These flip real SQL semantics; that they survive the PG suite means the enforcement
  tests don't exercise the specific branch (e.g. a non-shared-schema tenancy, or a
  dotted-FK path of depth ≥ 3). Candidates for targeted PG tests if/when we harden these.

## Productionised (done)

The POC graduated to `dazzle sentinel mutate` (engine: `src/dazzle/testing/mutation/`).
The five modules above + their floors are registered in
`src/dazzle/testing/mutation/targets.py` and enforced by `dazzle sentinel mutate --suite
security`, run nightly by `.github/workflows/mutation-nightly.yml` (with a Postgres service
so the SQL-gen modules are measured with their enforcement suite). Floors are set a few
points below the measured baseline so a drop in test *strength* — not just coverage —
turns the job red. Per-module floors: crypto ≥80, matrix ≥65, csrf ≥80, rls_schema ≥55
(PG), predicate_compiler ≥40 (PG).

Remaining work (optional): close the genuine residual survivors in the scope/RLS compilers
(listed above) with targeted PG tests, raising those floors over time.
