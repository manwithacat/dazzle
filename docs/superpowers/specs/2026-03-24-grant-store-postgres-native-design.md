# GrantStore PostgreSQL-Native Rewrite

**Date**: 2026-03-24
**Status**: Approved
**Issue**: #640 (original fix), follow-on hardening
**Scope**: `grant_store.py`, `grant_routes.py`, and their tests

## Problem

The GrantStore was written with SQLite as the default backend and PostgreSQL
bolted on via a `_sql()` helper that does blind `?` → `%s` string replacement.
This is fragile, untested against PostgreSQL, and uses lowest-common-denominator
types (`TEXT` everywhere). The state machine transitions have TOCTOU race
conditions. PostgreSQL is the sole runtime backend for Dazzle — SQLite should
not appear in grant code at all.

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Target database | PostgreSQL only | SQLite is not a supported target. Hard requirement. |
| Concurrency control | Optimistic (WHERE clause + rowcount) | Single-row transitions; advisory locks are overkill. Documented as upgrade path if multi-step serialization is needed later. |
| DDL types | Native PG types (UUID, TIMESTAMPTZ, JSONB) | Type safety, index efficiency, no string conversion bugs. |
| Abstraction layer | None — SQL is the logic | One backend, simple state machine. Premature abstraction obscures correctness. |
| Test backend | Real PostgreSQL via `TEST_DATABASE_URL` | Tests must exercise the actual backend. Developers need PostgreSQL to use Dazzle. |

## Design

### 1. Connection Contract

GrantStore accepts a psycopg connection directly. No placeholder parameter,
no `_sql()` helper. All SQL uses `%s` placeholders natively.

```python
class GrantStore:
    def __init__(self, conn: Any) -> None:
        self._conn = conn
        self._ensure_tables()
```

### 2. DDL

```sql
CREATE TABLE IF NOT EXISTS _grants (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    schema_name     TEXT NOT NULL,
    relation        TEXT NOT NULL,
    principal_id    UUID NOT NULL,
    scope_entity    TEXT NOT NULL,
    scope_id        UUID NOT NULL,
    status          TEXT NOT NULL CHECK (status IN (
        'pending_approval', 'active', 'rejected', 'cancelled', 'expired', 'revoked'
    )),
    granted_by_id   UUID NOT NULL,
    approved_by_id  UUID,
    granted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    approved_at     TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ,
    revoked_at      TIMESTAMPTZ,
    revoked_by_id   UUID
);

CREATE INDEX IF NOT EXISTS idx_grants_lookup
    ON _grants (principal_id, relation, scope_id, status);

CREATE INDEX IF NOT EXISTS idx_grants_expiry
    ON _grants (status, expires_at)
    WHERE status = 'active' AND expires_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS _grant_events (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    grant_id    UUID NOT NULL REFERENCES _grants(id),
    event_type  TEXT NOT NULL CHECK (event_type IN (
        'created', 'approved', 'rejected', 'cancelled', 'revoked', 'expired'
    )),
    actor_id    UUID NOT NULL,
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata    JSONB
);

CREATE INDEX IF NOT EXISTS idx_grant_events_grant_id
    ON _grant_events (grant_id);
```

Notable:
- **UUID** for all ID columns (16 bytes vs ~36 for TEXT, type-safe)
- **TIMESTAMPTZ** for all timestamps (timezone-aware, native comparison)
- **JSONB** for event metadata (queryable, validated)
- **CHECK constraints** on `status` and `event_type` — database-level guard against invalid states
- **Partial index on expiry** — only indexes active grants with expiry dates
- **FK index on `_grant_events.grant_id`** — PostgreSQL does not auto-index FK columns
- **Server-side defaults** for id, granted_at, timestamp

### 3. State Machine — Atomic Transitions

Valid transitions:

```
pending_approval → active     (approve)
pending_approval → rejected   (reject)
pending_approval → cancelled  (cancel — by the granter)
active           → revoked    (revoke)
active           → expired    (expire_stale_grants)
```

Terminal states (no outbound transitions): `rejected`, `cancelled`, `expired`, `revoked`.

Every transition uses a single `UPDATE ... WHERE status = %s` and checks
`cursor.rowcount`. No separate read-then-write. Example:

```python
def approve_grant(self, grant_id: UUID, approved_by_id: UUID) -> dict[str, Any]:
    now = datetime.now(UTC)
    cursor = self._conn.execute(
        """UPDATE _grants
           SET status = %s, approved_by_id = %s, approved_at = %s
           WHERE id = %s AND status = %s""",
        (GrantStatus.ACTIVE, approved_by_id, now, grant_id, GrantStatus.PENDING_APPROVAL),
    )
    if cursor.rowcount == 0:
        row = self._conn.execute(
            "SELECT status FROM _grants WHERE id = %s", (grant_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Grant {grant_id} not found")
        raise ValueError(f"Cannot approve grant in status '{row['status']}'")
    self._record_event(grant_id, "approved", approved_by_id)
    self._conn.commit()
    return self._get_grant(grant_id)
```

**Transaction boundary**: psycopg 3 defaults to `autocommit=False`. The
UPDATE and the subsequent `_record_event` INSERT are in the same transaction
until `commit()`. If the process crashes between them, both are rolled back.
This is the correct behaviour — a transition without its audit event must
never be persisted. Implementers must not enable autocommit on connections
passed to GrantStore.

`expire_stale_grants` uses `RETURNING id` to get expired IDs in one statement:

```python
def expire_stale_grants(self) -> int:
    now = datetime.now(UTC)
    cursor = self._conn.execute(
        """UPDATE _grants SET status = %s
           WHERE status = %s AND expires_at IS NOT NULL AND expires_at <= %s
           RETURNING id""",
        (GrantStatus.EXPIRED, GrantStatus.ACTIVE, now),
    )
    expired = cursor.fetchall()
    for row in expired:
        self._record_event(row["id"], "expired", UUID(int=0))  # system actor
    if expired:
        self._conn.commit()
    return len(expired)
```

### 4. `has_active_grant` — Expiry-Aware Lookup

The primary runtime interface used by the condition evaluator. Unchanged
in logic but benefits from TIMESTAMPTZ: the `expires_at > now()` comparison
is now a native timestamp comparison instead of lexicographic string
comparison on ISO-8601 text. This eliminates a subtle correctness risk
where malformed or timezone-naive strings could produce wrong results.

```python
def has_active_grant(self, principal_id: UUID, relation: str, scope_id: UUID) -> bool:
    now = datetime.now(UTC)
    row = self._conn.execute(
        """SELECT 1 FROM _grants
           WHERE principal_id = %s AND relation = %s AND scope_id = %s
           AND status = %s
           AND (expires_at IS NULL OR expires_at > %s)
           LIMIT 1""",
        (principal_id, relation, scope_id, GrantStatus.ACTIVE, now),
    ).fetchone()
    return row is not None
```

The partial index `idx_grants_expiry` serves this query.

### 5. `list_grants` — Dynamic WHERE

Replace the `? IS NULL OR col = ?` anti-pattern with dynamic WHERE clause
construction. Column names are string literals in code (not user input),
so no injection risk:

```python
def list_grants(self, scope_entity=None, scope_id=None, principal_id=None, status=None):
    clauses, params = [], []
    if scope_entity is not None:
        clauses.append("scope_entity = %s"); params.append(scope_entity)
    if scope_id is not None:
        clauses.append("scope_id = %s"); params.append(scope_id)
    # ... etc
    where = " AND ".join(clauses) if clauses else "TRUE"
    rows = self._conn.execute(
        f"SELECT * FROM _grants WHERE {where} ORDER BY granted_at DESC", params
    ).fetchall()
    return [dict(r) for r in rows]
```

### 6. Python Type Changes

Methods accept `UUID` and `datetime` objects. psycopg 3 handles conversion
natively. The HTTP boundary (`grant_routes.py`) converts strings to UUIDs
and returns 422 on malformed input.

### 7. `grant_routes.py` Changes

- Remove `placeholder="%s"` from `_get_store()`
- Fix docstring (psycopg connection, not sqlite3)
- Add `_parse_uuid()` helper for HTTP boundary validation
- Route-level `_get_grant()` call remains for authorization checks
  (`_check_granted_by` needs `schema_name`); the store-level pre-read
  before transitions is eliminated by the optimistic WHERE clause

### 8. Testing Strategy

**Fixtures**: Session-scoped connection factory from `TEST_DATABASE_URL`.
Per-test fixture drops and recreates tables via `_ensure_tables()`.
Tests are skipped with `pytest.skip("TEST_DATABASE_URL not set")` when
the env var is absent, so `pytest tests/ -m "not e2e"` remains green
on machines without PostgreSQL.

**Test categories**:
- Existing state machine tests (structurally preserved, new fixtures)
- `cancel_grant` tests (new transition)
- Concurrency tests (two connections, same grant, one wins)
- Type validation tests (malformed UUID → psycopg DataError)
- Table introspection via `pg_catalog` instead of `sqlite_master`

**Integration test**: DSL parse → GrantStore → condition evaluation,
backed by PostgreSQL.

## Files Changed

| File | Change |
|------|--------|
| `src/dazzle_back/runtime/grant_store.py` | Full rewrite — PG-native, proper types, atomic transitions, cancel_grant |
| `src/dazzle_back/runtime/grant_routes.py` | Drop placeholder, add UUID validation, fix docstring, add cancel endpoint |
| `tests/unit/test_grant_store.py` | PG fixtures, concurrency tests, type tests, cancel tests |
| `tests/unit/test_grant_integration.py` | Swap SQLite for PostgreSQL |

## Files NOT Changed (Separate Efforts)

- `repository.py` / `SQLiteRepository` alias — #642
- `audit_log.py` SQLite fallback — #643
- `events/outbox.py` aiosqlite code — #644
- `_comparison.py` SQLite bool coercion — #645

## Future Consideration

If the grant system later requires multi-step serialization (e.g.,
check grant + check quota + create resource atomically), PostgreSQL
advisory locks (`pg_advisory_xact_lock`) are the documented upgrade path.
Not needed for single-row state transitions.
