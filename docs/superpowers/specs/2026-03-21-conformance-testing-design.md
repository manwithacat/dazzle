# DSL Conformance Testing

**Date:** 2026-03-21
**Status:** Approved
**Author:** Claude + James

## Problem

Dazzle is a DSL-first toolkit that compiles high-level specifications into running applications. The DSL declares access rules (permit/forbid), row-level scoping (scope predicates), and persona-based authorization — but the runtime implementation has repeatedly failed to enforce these declarations faithfully. Recent bugs include:

- Compound logical conditions in permit blocks silently bypassed on CREATE (#594)
- Scope predicates not applied on API list endpoints (#595)
- Null FK values poisoning scope resolution (#591, #580)
- CSRF protection disabled by default (#597)
- Missing enforcement points in UI layer (#581-585)

These are all the same class of bug: **the runtime doesn't faithfully implement what the DSL declares**. The gap between specification and execution is the root cause.

## Solution

A conformance testing framework that mechanically derives behavioral test cases from the DSL specification and verifies the runtime enforces them. Fully deterministic — every test case is derived from the DSL, fixtures use known UUIDs, assertions are exact.

### Key Insight

The DSL contains enough information to generate its own test suite. Given `permit: role(admin)` and `scope: owner = current_user for: viewer`, the expected behavior for every `(persona, entity, operation)` triple is mechanically derivable. No human needs to write access control tests — the framework generates them from the specification.

## Architecture

```
AppSpec (parsed, linked, predicates compiled)
    |
    v
Derivation Engine (pure function)
    |-- extracts personas from permit/scope for: clauses
    |-- derives expected behavior per (entity, persona, operation)
    |-- produces list of ConformanceCase
    v
Fixture Engine (pure function)
    |-- generates deterministic seed data from entity schemas
    |-- computes expected row counts from scope rules + seeded data
    |-- produces ConformanceFixtures
    v
Two delivery mechanisms:
    |
    |-- pytest plugin (dynamic, always in sync)
    |       boots FastAPI app in-process via app_factory
    |       uses isolated PostgreSQL test schema (or pytest-postgresql)
    |       seeds DB with fixtures via direct SQL
    |       creates auth tokens via enable_test_mode endpoints
    |       runs HTTP assertions via httpx AsyncClient (ASGI transport)
    |
    |-- static generator (dazzle conformance generate)
            writes TOML files for inspection/debugging
            documents expected behavior per entity
            scaffold for stage-by-stage invariant checks
```

## Conformance Coverage Metric

Coverage = `cases_passed / cases_total` where `cases_total` is the complete set of `(entity, persona, operation)` triples derived from the AppSpec.

**Goal: 1.0 (100%) before deployment.** Every declared access rule must have a passing conformance case. If a triple can't be tested, that's a bug in the framework, not an inherent limitation — the DSL's formal structure IS the test specification.

The metric is reported by `dazzle conformance summary` (MCP) and the static generator includes it in the TOML output.

## Test Derivation Engine

Pure function: `derive_conformance_cases(appspec: AppSpec) -> list[ConformanceCase]`

### ConformanceCase

```python
@dataclass
class ConformanceCase:
    entity: str           # "Task"
    persona: str          # "viewer"
    operation: str        # "list", "create", "read", "update", "delete"
    expected_status: int  # 200, 201, 401, 403, 404
    expected_rows: int | None  # exact count for list ops, None for non-list
    row_target: str | None    # "own" or "other" for read/update/delete, None for list/create
    description: str      # "viewer listing Task sees only own rows"
    scope_type: str       # see ScopeOutcome enum below
```

**ScopeOutcome values:**
- `"all"` — scope: all, sees every row
- `"filtered"` — scope with predicate, sees matching rows only
- `"scope_excluded"` — permit granted but no matching scope rule → 0 rows (default-deny, #595)
- `"access_denied"` — no permit rule matches → 403
- `"forbidden"` — explicit `forbid` rule matches → 403 (Cedar FORBID > PERMIT)
- `"unauthenticated"` — no auth token → 401
- `"unprotected"` — entity has no access spec → all rows visible

### Derivation Rules

The derivation engine takes one additional input: `auth_enabled: bool` (from `dazzle.toml` or app config), which affects unauthenticated access behavior.

**Step 1: Extract personas** — scan all `permit`, `forbid`, and `scope` `for:` clauses across all entities. Add synthetic `"unauthenticated"` (no auth) and `"unmatched_role"` (authenticated, no matching persona) personas.

**Step 2: For each (entity, persona, operation)** — apply Cedar three-rule evaluation order: FORBID > PERMIT > default-deny.

1. **Unauthenticated persona:**
   - If `auth_enabled` → `expected_status=401`, `scope_type="unauthenticated"`
   - If not `auth_enabled` and entity has no access spec → `expected_status=200`, `scope_type="unprotected"`, `expected_rows=total_seed_count`

2. **`unmatched_role` persona** (authenticated, no matching permit/scope persona):
   - Entity has access spec → `expected_status=403`, `scope_type="access_denied"` (Cedar default-deny)
   - Entity has no access spec → `expected_status=200`, `scope_type="unprotected"`

   **No access spec on entity** → `expected_status=200`, `expected_rows=total_seed_count`, `scope_type="unprotected"` (unprotected entity — all rows visible to authenticated users)

3. **Check `forbid` rules first** (Cedar: FORBID > PERMIT):
   - If any `forbid` rule matches this `(persona, operation)` → `expected_status=403`, `scope_type="forbidden"`

4. **Check `permit` rules:**
   - No permit matches → `expected_status=403`, `scope_type="access_denied"`

5. **Permit matches — check scope rules** (LIST operation only):
   - Scope with `for: *` wildcard → applies to this persona regardless of name
   - `scope: all` → `expected_rows=total_seed_count`, `scope_type="all"`
   - `scope: field = current_user` → `expected_rows=owned_count`, `scope_type="filtered"`
   - `scope: field = current_user.<attr>` → `expected_rows=attr_matching_count`, `scope_type="filtered"`
   - `scope: field = "literal"` (ColumnCheck) → `expected_rows=literal_matching_count`, `scope_type="filtered"`
   - `scope: via JunctionEntity(...)` → `expected_rows=junction_matching_count`, `scope_type="filtered"`
   - Scope predicate simplifies to `Contradiction` → `expected_rows=0`, `scope_type="scope_excluded"`
   - No scope rule matches persona → `expected_rows=0`, `scope_type="scope_excluded"` (default-deny per #595)

6. **Permit matches — non-LIST operations** (each produces TWO cases per persona: own-row and other-row):
   - **CREATE:** single case, `expected_status=201` (no scope predicate — permit gate is the only check)
   - **READ own row:** `expected_status=200`, `row_target="own"`
   - **READ other's row:** `expected_status=404`, `row_target="other"` (Cedar evaluates permit per-record; denied records return 404 to avoid leaking existence)
   - **UPDATE own row:** `expected_status=200`, `row_target="own"`
   - **UPDATE other's row:** `expected_status=404`, `row_target="other"`
   - **DELETE own row:** `expected_status=200`, `row_target="own"`
   - **DELETE other's row:** `expected_status=404`, `row_target="other"`

   For entities with `scope: all` for a persona, both own-row and other-row cases expect `200`.

**Step 3: Compound scopes** — AND/OR/NOT in scope conditions produce `scope_type="filtered"`. The fixture engine assigns explicit field values per row, and the derivation engine evaluates the predicate tree against each fixture row to compute the exact `expected_rows` count. This is a deterministic evaluation of the predicate algebra against known data.

**Step 4: Cross-entity FK paths** — `scope: manuscript.student = current_user` produces `scope_type="filtered"` with expected counts computed by walking the FK chain through fixture data.

This is a pure transformation — no side effects, no database, no HTTP. Testable in isolation.

## Fixture Engine

Pure function: `generate_fixtures(appspec: AppSpec) -> ConformanceFixtures`

### ConformanceFixtures

```python
@dataclass
class ConformanceFixtures:
    users: dict[str, dict]                    # persona_name -> user record dict
    entity_rows: dict[str, list[dict]]        # entity_name -> list of row dicts
    junction_rows: dict[str, list[dict]]      # junction_entity -> list of linking rows
    expected_counts: dict[tuple[str, str], int]  # (persona, entity) -> visible row count
```

### Fixture Strategy

For each entity with access rules:

- **2 user entities per persona** — User A (persona-under-test) and User B (different user, same persona). Deterministic UUIDs via `uuid5(NAMESPACE, f"{entity}.{persona}.{purpose}")`.
- **4 entity rows per scoped entity:**
  - Row 1: owned by User A, User A's realm, matching literal values (satisfies all scope branches)
  - Row 2: owned by User B, User B's realm (filtered out for ownership scopes)
  - Row 3: owned by User A, different realm (tests `current_user.<attr>` — matches ownership but not realm)
  - Row 4: owned by User B, User A's realm (tests OR scopes — doesn't match ownership but matches realm)
- **FK resolution:** reads entity field specs to populate ref fields correctly
- **Via-junction fixtures:** creates junction table rows linking User A to Rows 1 and 3
- **`current_user.<attr>` fixtures:** User A's record includes the referenced attributes (realm, school, etc.)
- **ColumnCheck literal fixtures:** when scope rules reference literal values (e.g. `material = "shadow"`), rows are seeded with both matching and non-matching literal values

**OR predicate expected counts:** For a scope like `realm = current_user.realm or creator = current_user`, the derivation engine evaluates the predicate tree against each fixture row:
- Row 1: owner=A, realm=A's → both branches true → visible (1)
- Row 2: owner=B, realm=B's → both branches false → hidden (0)
- Row 3: owner=A, realm=other → right branch true → visible (1)
- Row 4: owner=B, realm=A's → left branch true → visible (1)
- Result: `expected_rows=3`

This evaluation is deterministic because both the fixture values and the predicate tree are known at derivation time.

### Determinism

All UUIDs are `uuid5(CONFORMANCE_NS, f"{entity}.{purpose}")` where `CONFORMANCE_NS = UUID("d4zzl3c0-nf0r-m4nc-3t3s-t1ngfr4m3w0")` — a fixed Dazzle-specific namespace. Same input always produces the same UUID. No randomness. Fixtures are reproducible across runs.

`expected_counts` is computed mechanically from scope rules and seeded data — not from running the app. The test asserts `actual_count == expected_counts[(persona, entity)]`.

## pytest Plugin

### Registration

Standard pytest plugin. Activated when `dazzle.toml` is found in the project root, or explicitly via `pytest -m conformance`. Marker: `@pytest.mark.conformance`.

### Collection Phase (no side effects)

1. Parse DSL → AppSpec (reuse `parse_dsl` + linker)
2. Run derivation engine → list of `ConformanceCase`
3. Generate pytest parametrized items: `test_conformance[viewer-list-Task-filtered]`

### Setup Phase (session-scoped fixture)

1. Boot FastAPI app from AppSpec via `app_factory.create_app()` with `enable_test_mode=True`
2. Use isolated PostgreSQL test schema (the app's existing `PostgresBackend` requires PostgreSQL — no SQLite path exists). Test database URL from `CONFORMANCE_DATABASE_URL` env var or fallback to `dazzle.toml` `[database]` with a `_conformance` suffix on the schema name.
3. Create tables via the ORM layer (`db_manager.create_tables()`)
4. Seed fixtures via direct SQL inserts (bypasses RBAC — avoids interference during seeding)
5. Create auth tokens for each test persona via the `enable_test_mode` endpoints (`/__test__/create-user`, `/__test__/login`) which are already available when `enable_test_mode=True`
6. Wrap app in `httpx.AsyncClient(transport=ASGITransport(app))`
7. Teardown: drop all tables in the conformance schema (if using schema suffix) or drop the schema itself. When `CONFORMANCE_DATABASE_URL` points to a dedicated database, truncate all tables instead.

### Execution Phase (per test case)

```python
async def test_conformance(client, case: ConformanceCase, auth_tokens):
    headers = auth_tokens.get(case.persona, {})  # empty = unauthenticated

    if case.operation == "list":
        response = await client.get(f"/{entity_plural}", headers=headers)
        assert response.status_code == case.expected_status
        if case.expected_status == 200:
            data = response.json()
            assert data["total"] == case.expected_rows

    elif case.operation == "create":
        response = await client.post(
            f"/{entity_plural}", json=minimal_payload, headers=headers
        )
        assert response.status_code == case.expected_status

    # read, update, delete similarly
```

### Output

Standard pytest output. Failures show the exact case:
```
FAILED test_conformance[viewer-list-Task-filtered]
  assert 3 == 1  (API returned 3 rows, expected 1 for scoped viewer)
```

## Static Generator

**CLI:** `dazzle conformance generate`

**Output:** One TOML file per entity in `.dazzle/conformance/`:

```toml
# .dazzle/conformance/Task.toml
# AUTO-GENERATED — do not edit. Regenerate with: dazzle conformance generate

[entity]
name = "Task"
fields = ["id", "title", "owner", "status"]
scope_rules = 2
permit_rules = 3

[coverage]
total_cases = 15
scope_types = { filtered = 5, all = 4, denied = 4, unauthenticated = 2 }

[[cases]]
persona = "viewer"
operation = "list"
expected_status = 200
expected_rows = 1
scope_type = "filtered"
description = "viewer listing Task sees only own rows (scope: owner = current_user)"

[[cases]]
persona = "admin"
operation = "list"
expected_status = 200
expected_rows = 3
scope_type = "all"
description = "admin listing Task sees all rows (scope: all)"

[[cases]]
persona = "viewer"
operation = "create"
expected_status = 403
scope_type = "denied"
description = "viewer cannot create Task (no permit for create)"
```

### Stage Invariant Annotations

Each case can include intermediate expectations (documented but not asserted in v1):

```toml
[cases.invariants]
predicate_type = "UserAttrCheck"
expected_sql_contains = "WHERE owner = %s"
resolved_param = "user-a-uuid"
```

These document what each compilation stage should produce. Future versions assert them.

## MCP Integration

`conformance` MCP tool with operations:

| Operation | Purpose |
|-----------|---------|
| `summary` | Coverage metric, case counts per entity, pass/fail from last run |
| `cases` | List cases for a specific entity |
| `gaps` | Entities with permits but no conformance coverage |

## Testing the Framework Itself

- **Derivation engine tests** — feed `shapes_validation` AppSpec (exercises every RBAC pattern), assert correct `ConformanceCase` list. Pure function, no runtime.
- **Fixture engine tests** — verify fixture generation produces correct UUIDs, FK relationships, and expected counts for each scope type.
- **Plugin integration test** — boot `shapes_validation` app via the plugin, run conformance cases, assert all pass. The conformance framework conforming to itself.
- **Regression anchors** — run conformance against `simple_task` and `pra` examples. These should pass; failures indicate real bugs.

## What v1 Covers

- Permit gate enforcement (all operations, all persona combinations)
- Scope predicate enforcement (LIST row filtering)
- Default-deny (permit without scope, #595)
- Unauthenticated access (401)
- CRUD mutation enforcement (CREATE/UPDATE/DELETE status codes)
- `via` junction-table scope rules
- `current_user.<attr>` dotted attribute resolution
- Cross-entity FK path scope rules (depth > 1)
- Conformance coverage metric (target: 1.0)

## Out of Scope

- Runtime contract monitoring (approach C — future CI/CD tool, designed for but not implemented)
- Stage-by-stage assertion execution (invariant annotations documented in TOML but not asserted)
- UI-layer conformance (template rendering, sidebar visibility, column hiding)
- Performance/load testing
