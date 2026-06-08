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
| `back/runtime/rls_schema.py` | **7%** | **60% → 93%** | RLS DDL generation; residuals closed 2026-06-08 |
| `back/runtime/predicate_compiler.py` | **35%** | **45% → 77%** | scope→SQL compiler; residuals closed 2026-06-08 |
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
  (`predicate_compiler` L274 "Available FKs" `or`→`and`); and the two `L813`
  boolean-precedence flips on the dotted null-target guard — `value_sql is None` ⟺
  `target == "null"` there, so the combinations the mutants would diverge on are
  unreachable.

### Scope/RLS compiler residuals — CLOSED (2026-06-08)

The genuine residual gaps in the two SQL compilers are now pinned by direct unit tests
that exercise each branch (the PG suite executed them end-to-end but didn't constrain the
specific operator):

- **`rls_schema` 60% → 93%** (`tests/unit/test_rls_schema.py`): the orchestrators
  `build_all_rls_ddl` / `describe_rls_policies` were only run end-to-end. New stub-driven
  tests pin the tenancy gate (`tenancy is None` no-crash; `mode != SHARED_SCHEMA` → emit
  vs not), the scoped-vs-flat `has_scopes` split, and the no-scopes `ValueError` guard. The
  one survivor is an equivalent frozen-dataclass mutant.
- **`predicate_compiler` 45% → 77%** (`tests/unit/test_predicate_compiler.py`): new tests
  pin the scalar type-map (`kind == "scalar"`), the null-target `IS NULL` op, the
  `current_user`→`id` GUC-ref collection, the policy-mode non-dotted-binding guard, the
  2- and 3-segment dotted-junction expansion (depth + tail→head hop iteration), and the
  create-probe `payload_mode`. The 7 survivors are all equivalent/effectively-equivalent
  (frozen-dataclass ×4, error-string, correlated-guard ×2).

## Productionised (done)

The POC graduated to `dazzle sentinel mutate` (engine: `src/dazzle/testing/mutation/`).
The five modules above + their floors are registered in
`src/dazzle/testing/mutation/targets.py` and enforced by `dazzle sentinel mutate --suite
security`, run nightly by `.github/workflows/mutation-nightly.yml` (with a Postgres service
so the SQL-gen modules are measured with their enforcement suite). Floors are set a few
points below the measured baseline so a drop in test *strength* — not just coverage —
turns the job red. Per-module floors: crypto ≥80, matrix ≥65, csrf ≥80, rls_schema ≥90
(PG), predicate_compiler ≥72 (PG).
