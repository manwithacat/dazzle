# shapes_validation — tenant-scoped RBAC + conformance probe

An abstract "shapes" domain (6 entities × 8 personas) used by `tests/unit/test_conformance_plugin.py` and the CI security gate to verify the framework's multi-tenant RBAC patterns end-to-end. CLAUDE.md describes this as the fixture that *"exercises every RBAC pattern"*.

This is a **framework-validation fixture**, not a user-facing example. The domain is deliberately abstract (`Realm`, `Shape`, `Artifact`, `Inscription`) so that no real-world bias contaminates the patterns being tested.

## Why "shapes"

The domain has zero teaching value on purpose. `MedicalRecord` smuggles in healthcare intuitions; `Realm + Shape + Artifact` doesn't. The personas (`oracle`, `sovereign`, `architect`, `chromat`, `forgemaster`, `witness`, `guardian`, `outsider`) span the canonical tenancy roles without naming them after any real product.

## What this fixture probes

| Surface area | How |
|--------------|-----|
| Platform-admin vs tenant-admin distinction | `oracle` sees across `Realm`s; `sovereign` is scoped to one |
| Default-deny under cross-realm probing | `outsider` and `witness` exercise the negative space — every entity should refuse them by default |
| Realm-scoped `scope:` rules | `Shape.realm_id = current_user.realm` is the canonical column-equality form |
| Junction-table EXISTS / NOT EXISTS | `RealmGuardian` is a junction that drives `via` clauses |
| Inscription on Artifact (parent-scope inheritance) | Tests whether scope follows the FK chain when the child entity has no direct realm column |
| Conformance plugin invariants | `tests/unit/test_conformance_plugin.py` runs the framework's conformance suite against this fixture, treating it as the canonical "well-formed multi-tenant app" |

## Design rules for extension

1. **Keep the domain meaningless.** No new entity should evoke a real product. If you're tempted to name something `Order` or `Customer`, you're modelling a use case, not testing a pattern.
2. **Each persona must probe a *role behaviour*, not a job title.** New personas earn their place by covering a tenancy pattern (delegated cross-realm grant, time-bounded admin, conditional permission) not currently exercised.
3. **Each entity must probe a *scope shape*.** Direct realm column, FK-inherited scope, junction EXISTS, junction NOT-EXISTS, predicate negation, boolean combinations. The combinatorial coverage is the point.
4. **Pair every addition with a test assertion.** Untested coverage is decoration. The conformance test is the canonical consumer; widen it when you widen the fixture.

## What does NOT belong here

- UI/UX coverage — separate test surfaces own that.
- Performance probes — keep the fixture small. CI security gate runs on every push.
- Domain-realistic data — abstract values only.
- Workflow / state-machine modelling — those have dedicated fixtures.
- "Wouldn't it be cool if…" entities. The size of this fixture is a feature; it's small enough to reason about exhaustively.

## Running the tests

```bash
pytest tests/unit/test_conformance_plugin.py -v
```

Expected: 7 tests, ~0.25s. The fixture is also exercised by `dazzle rbac` matrix tooling and by the CI security gate in `.github/workflows/ci.yml`.

## See also

- `tests/unit/test_conformance_plugin.py` — the conformance check suite
- [`fixtures/rbac_validation`](../rbac_validation/) — sibling fixture, NIST 800-162 ABAC patterns on a single-tenant domain
- `docs/reference/rbac-verification.md` — public-facing RBAC verification framework
- `src/dazzle/rbac/` — matrix + audit + verifier implementation
- `.github/workflows/ci.yml` — `security-tests` job uses this fixture as its canonical RBAC corpus
