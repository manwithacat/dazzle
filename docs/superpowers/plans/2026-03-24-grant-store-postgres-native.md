# GrantStore PostgreSQL-Native Rewrite — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite GrantStore from dual SQLite/PostgreSQL to PostgreSQL-only with native types, atomic state transitions, and real PostgreSQL tests.

**Architecture:** Direct PostgreSQL-native SQL with `%s` placeholders, proper types (UUID, TIMESTAMPTZ, JSONB), optimistic concurrency via `UPDATE WHERE status + rowcount`, CHECK constraints on status/event_type columns. No abstraction layer — SQL is the logic.

**Tech Stack:** psycopg 3, PostgreSQL 14+, pytest with `TEST_DATABASE_URL`

**Spec:** `docs/superpowers/specs/2026-03-24-grant-store-postgres-native-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/dazzle_back/runtime/grant_store.py` | Rewrite | PostgreSQL-native grant store with proper types and atomic transitions |
| `src/dazzle_back/runtime/grant_routes.py` | Modify | Drop placeholder, UUID validation at HTTP boundary, cancel endpoint |
| `tests/unit/test_grant_store.py` | Rewrite | PostgreSQL-backed tests: state machine, concurrency, types |
| `tests/unit/test_grant_integration.py` | Modify | Swap SQLite for PostgreSQL in integration pipeline test |

---

### Task 1: PostgreSQL Test Fixtures

**Files:**
- Modify: `tests/unit/test_grant_store.py`

All subsequent tasks depend on having working PostgreSQL fixtures. Build these first and verify connectivity before touching the store.

- [ ] **Step 1: Write the PostgreSQL fixture module**

Add a `pg_grant_conn` fixture to `tests/unit/test_grant_store.py` that connects to `TEST_DATABASE_URL`, drops grant tables before each test, and closes after. Keep it self-contained in the test file since only grant tests need it.

```python
import os
import psycopg
from psycopg.rows import dict_row
import pytest

@pytest.fixture(scope="session")
def pg_grant_conn_factory():
    """Session-scoped factory for PostgreSQL connections. Skips if no TEST_DATABASE_URL."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set — skipping PostgreSQL grant tests")
    def factory():
        return psycopg.connect(url, row_factory=dict_row)
    return factory

@pytest.fixture
def pg_conn(pg_grant_conn_factory):
    """Per-test connection that drops grant tables for clean state."""
    conn = pg_grant_conn_factory()
    conn.execute("DROP TABLE IF EXISTS _grant_events, _grants")
    conn.commit()
    yield conn
    conn.close()
```

- [ ] **Step 2: Write a smoke test that verifies PostgreSQL connectivity**

```python
class TestPgConnectivity:
    def test_connection_works(self, pg_conn):
        row = pg_conn.execute("SELECT 1 AS ok").fetchone()
        assert row["ok"] == 1
```

- [ ] **Step 3: Run smoke test**

Run: `TEST_DATABASE_URL=postgresql://localhost/dazzle_test pytest tests/unit/test_grant_store.py::TestPgConnectivity -v`
Expected: PASS (or SKIP if no TEST_DATABASE_URL)

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_grant_store.py
git commit -m "test(grants): add PostgreSQL fixtures for grant store tests"
```

---

### Task 2: Rewrite GrantStore — DDL and Constructor

**Files:**
- Modify: `src/dazzle_back/runtime/grant_store.py`
- Test: `tests/unit/test_grant_store.py`

Replace the entire `__init__` and `_ensure_tables` with PostgreSQL-native DDL. Remove `_sql()` helper, `placeholder` parameter, and `import sqlite3`.

- [ ] **Step 1: Write the failing test for table creation**

```python
from dazzle_back.runtime.grant_store import GrantStore

class TestGrantStoreInit:
    def test_tables_created(self, pg_conn):
        store = GrantStore(pg_conn)
        row = pg_conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE '_grant%'"
        ).fetchall()
        tables = {r["tablename"] for r in row}
        assert "_grants" in tables
        assert "_grant_events" in tables

    def test_check_constraint_on_status(self, pg_conn):
        store = GrantStore(pg_conn)
        from psycopg import errors
        with pytest.raises(errors.CheckViolation):
            pg_conn.execute(
                """INSERT INTO _grants (id, schema_name, relation, principal_id, scope_entity,
                   scope_id, status, granted_by_id, granted_at)
                   VALUES (gen_random_uuid(), 'x', 'r', gen_random_uuid(), 'E',
                   gen_random_uuid(), 'INVALID_STATUS', gen_random_uuid(), now())"""
            )
        pg_conn.rollback()

    def test_check_constraint_on_event_type(self, pg_conn):
        store = GrantStore(pg_conn)
        from uuid import uuid4
        grant_id = uuid4()
        pg_conn.execute(
            """INSERT INTO _grants (id, schema_name, relation, principal_id, scope_entity,
               scope_id, status, granted_by_id, granted_at)
               VALUES (%s, 'x', 'r', %s, 'E', %s, 'active', %s, now())""",
            (grant_id, uuid4(), uuid4(), uuid4()),
        )
        from psycopg import errors
        with pytest.raises(errors.CheckViolation):
            pg_conn.execute(
                """INSERT INTO _grant_events (id, grant_id, event_type, actor_id, timestamp)
                   VALUES (gen_random_uuid(), %s, 'INVALID_EVENT', gen_random_uuid(), now())""",
                (grant_id,),
            )
        pg_conn.rollback()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `TEST_DATABASE_URL=postgresql://localhost/dazzle_test pytest tests/unit/test_grant_store.py::TestGrantStoreInit -v`
Expected: FAIL (GrantStore still uses old code)

- [ ] **Step 3: Rewrite GrantStore constructor and DDL**

**Replace the entire contents of `grant_store.py`** with the following (delete all existing code first):

```python
"""
Runtime grant store for dynamic RBAC grants.

Manages the _grants and _grant_events tables on PostgreSQL, providing CRUD
operations with atomic status transitions and audit event logging.

Requires: psycopg >= 3.2
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class GrantStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    ACTIVE = "active"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REVOKED = "revoked"


class GrantStore:
    """Grant store backed by PostgreSQL.

    All SQL uses native PostgreSQL types (UUID, TIMESTAMPTZ, JSONB) and %s
    placeholders. Connections must have autocommit=False (psycopg default).
    """

    def __init__(self, conn: Any) -> None:
        self._conn = conn
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        cursor = self._conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS _grants (
                id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                schema_name     TEXT NOT NULL,
                relation        TEXT NOT NULL,
                principal_id    UUID NOT NULL,
                scope_entity    TEXT NOT NULL,
                scope_id        UUID NOT NULL,
                status          TEXT NOT NULL CHECK (status IN (
                    'pending_approval', 'active', 'rejected',
                    'cancelled', 'expired', 'revoked'
                )),
                granted_by_id   UUID NOT NULL,
                approved_by_id  UUID,
                granted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
                approved_at     TIMESTAMPTZ,
                expires_at      TIMESTAMPTZ,
                revoked_at      TIMESTAMPTZ,
                revoked_by_id   UUID
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_grants_lookup
            ON _grants (principal_id, relation, scope_id, status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_grants_expiry
            ON _grants (status, expires_at)
            WHERE status = 'active' AND expires_at IS NOT NULL
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS _grant_events (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                grant_id    UUID NOT NULL REFERENCES _grants(id),
                event_type  TEXT NOT NULL CHECK (event_type IN (
                    'created', 'approved', 'rejected',
                    'cancelled', 'revoked', 'expired'
                )),
                actor_id    UUID NOT NULL,
                timestamp   TIMESTAMPTZ NOT NULL DEFAULT now(),
                metadata    JSONB
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_grant_events_grant_id
            ON _grant_events (grant_id)
        """)
        self._conn.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `TEST_DATABASE_URL=postgresql://localhost/dazzle_test pytest tests/unit/test_grant_store.py::TestGrantStoreInit -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_back/runtime/grant_store.py tests/unit/test_grant_store.py
git commit -m "feat(grants): rewrite GrantStore DDL for PostgreSQL-native types

UUID, TIMESTAMPTZ, JSONB columns. CHECK constraints on status and
event_type. Partial index on expiry. FK index on grant_events."
```

---

### Task 3: Core Methods — `_record_event`, `_get_grant`, `create_grant`

**Files:**
- Modify: `src/dazzle_back/runtime/grant_store.py`
- Test: `tests/unit/test_grant_store.py`

Implement the foundational methods that all transitions depend on.

- [ ] **Step 1: Write the failing tests for create_grant**

```python
from uuid import uuid4
from datetime import UTC, datetime, timedelta

class TestCreateGrant:
    def test_create_grant_pending(self, pg_conn):
        store = GrantStore(pg_conn)
        grant = store.create_grant(
            schema_name="dept_delegation",
            relation="acting_hod",
            principal_id=uuid4(),
            scope_entity="Department",
            scope_id=uuid4(),
            granted_by_id=uuid4(),
            approval_mode="required",
        )
        assert grant["status"] == GrantStatus.PENDING_APPROVAL
        assert isinstance(grant["id"], UUID)

    def test_create_grant_immediate(self, pg_conn):
        store = GrantStore(pg_conn)
        grant = store.create_grant(
            schema_name="dept_delegation",
            relation="acting_hod",
            principal_id=uuid4(),
            scope_entity="Department",
            scope_id=uuid4(),
            granted_by_id=uuid4(),
            approval_mode="immediate",
        )
        assert grant["status"] == GrantStatus.ACTIVE

    def test_create_grant_with_expiry(self, pg_conn):
        store = GrantStore(pg_conn)
        expires = datetime.now(UTC) + timedelta(days=90)
        grant = store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=uuid4(),
            scope_entity="E",
            scope_id=uuid4(),
            granted_by_id=uuid4(),
            approval_mode="none",
            expires_at=expires,
        )
        assert grant["expires_at"] is not None

    def test_create_grant_records_event(self, pg_conn):
        store = GrantStore(pg_conn)
        grant = store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=uuid4(),
            scope_entity="E",
            scope_id=uuid4(),
            granted_by_id=uuid4(),
            approval_mode="none",
        )
        events = pg_conn.execute(
            "SELECT * FROM _grant_events WHERE grant_id = %s", (grant["id"],)
        ).fetchall()
        assert len(events) == 1
        assert events[0]["event_type"] == "created"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `TEST_DATABASE_URL=postgresql://localhost/dazzle_test pytest tests/unit/test_grant_store.py::TestCreateGrant -v`
Expected: FAIL

- [ ] **Step 3: Implement `_record_event`, `_get_grant`, `create_grant`**

```python
    def _record_event(
        self,
        grant_id: UUID,
        event_type: str,
        actor_id: UUID,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._conn.execute(
            """INSERT INTO _grant_events (id, grant_id, event_type, actor_id, timestamp, metadata)
               VALUES (%s, %s, %s, %s, %s, %s)""",
            (
                uuid4(),
                grant_id,
                event_type,
                actor_id,
                datetime.now(UTC),
                json.dumps(metadata) if metadata else None,
            ),
        )

    def _get_grant(self, grant_id: UUID) -> dict[str, Any]:
        row = self._conn.execute(
            "SELECT * FROM _grants WHERE id = %s", (grant_id,)
        ).fetchone()
        if row is None:
            raise ValueError(f"Grant {grant_id} not found")
        return dict(row)

    def create_grant(
        self,
        schema_name: str,
        relation: str,
        principal_id: UUID,
        scope_entity: str,
        scope_id: UUID,
        granted_by_id: UUID,
        approval_mode: str = "required",
        expires_at: datetime | None = None,
    ) -> dict[str, Any]:
        grant_id = uuid4()
        now = datetime.now(UTC)

        if approval_mode == "required":
            status = GrantStatus.PENDING_APPROVAL
        else:
            status = GrantStatus.ACTIVE

        self._conn.execute(
            """INSERT INTO _grants
               (id, schema_name, relation, principal_id, scope_entity, scope_id,
                status, granted_by_id, granted_at, expires_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                grant_id,
                schema_name,
                relation,
                principal_id,
                scope_entity,
                scope_id,
                status,
                granted_by_id,
                now,
                expires_at,
            ),
        )
        self._record_event(grant_id, "created", granted_by_id)
        self._conn.commit()
        return self._get_grant(grant_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `TEST_DATABASE_URL=postgresql://localhost/dazzle_test pytest tests/unit/test_grant_store.py::TestCreateGrant -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_back/runtime/grant_store.py tests/unit/test_grant_store.py
git commit -m "feat(grants): implement create_grant with UUID/TIMESTAMPTZ types"
```

---

### Task 4: State Transitions — approve, reject, cancel, revoke

**Files:**
- Modify: `src/dazzle_back/runtime/grant_store.py`
- Test: `tests/unit/test_grant_store.py`

Implement all four transitions using the atomic `UPDATE WHERE status + rowcount` pattern.

- [ ] **Step 1: Write the failing tests**

```python
class TestApproveGrant:
    def test_approve_pending_grant(self, pg_conn):
        store = GrantStore(pg_conn)
        grant = store.create_grant(
            schema_name="x", relation="r", principal_id=uuid4(),
            scope_entity="E", scope_id=uuid4(), granted_by_id=uuid4(),
            approval_mode="required",
        )
        updated = store.approve_grant(grant["id"], uuid4())
        assert updated["status"] == GrantStatus.ACTIVE
        assert updated["approved_by_id"] is not None
        assert updated["approved_at"] is not None

    def test_approve_non_pending_raises(self, pg_conn):
        store = GrantStore(pg_conn)
        grant = store.create_grant(
            schema_name="x", relation="r", principal_id=uuid4(),
            scope_entity="E", scope_id=uuid4(), granted_by_id=uuid4(),
            approval_mode="none",
        )
        with pytest.raises(ValueError, match="Cannot approve"):
            store.approve_grant(grant["id"], uuid4())

    def test_approve_nonexistent_raises(self, pg_conn):
        store = GrantStore(pg_conn)
        with pytest.raises(ValueError, match="not found"):
            store.approve_grant(uuid4(), uuid4())


class TestRejectGrant:
    def test_reject_pending_grant(self, pg_conn):
        store = GrantStore(pg_conn)
        grant = store.create_grant(
            schema_name="x", relation="r", principal_id=uuid4(),
            scope_entity="E", scope_id=uuid4(), granted_by_id=uuid4(),
            approval_mode="required",
        )
        updated = store.reject_grant(grant["id"], uuid4(), reason="Not needed")
        assert updated["status"] == GrantStatus.REJECTED

    def test_reject_active_raises(self, pg_conn):
        store = GrantStore(pg_conn)
        grant = store.create_grant(
            schema_name="x", relation="r", principal_id=uuid4(),
            scope_entity="E", scope_id=uuid4(), granted_by_id=uuid4(),
            approval_mode="none",
        )
        with pytest.raises(ValueError, match="Cannot reject"):
            store.reject_grant(grant["id"], uuid4())

    def test_reject_records_reason_metadata(self, pg_conn):
        store = GrantStore(pg_conn)
        grant = store.create_grant(
            schema_name="x", relation="r", principal_id=uuid4(),
            scope_entity="E", scope_id=uuid4(), granted_by_id=uuid4(),
            approval_mode="required",
        )
        store.reject_grant(grant["id"], uuid4(), reason="Not needed")
        events = pg_conn.execute(
            "SELECT * FROM _grant_events WHERE grant_id = %s AND event_type = 'rejected'",
            (grant["id"],),
        ).fetchall()
        assert len(events) == 1
        import json
        meta = json.loads(events[0]["metadata"]) if isinstance(events[0]["metadata"], str) else events[0]["metadata"]
        assert meta["reason"] == "Not needed"


class TestCancelGrant:
    def test_cancel_pending_grant(self, pg_conn):
        store = GrantStore(pg_conn)
        granter = uuid4()
        grant = store.create_grant(
            schema_name="x", relation="r", principal_id=uuid4(),
            scope_entity="E", scope_id=uuid4(), granted_by_id=granter,
            approval_mode="required",
        )
        updated = store.cancel_grant(grant["id"], granter)
        assert updated["status"] == GrantStatus.CANCELLED

    def test_cancel_active_raises(self, pg_conn):
        store = GrantStore(pg_conn)
        grant = store.create_grant(
            schema_name="x", relation="r", principal_id=uuid4(),
            scope_entity="E", scope_id=uuid4(), granted_by_id=uuid4(),
            approval_mode="none",
        )
        with pytest.raises(ValueError, match="Cannot cancel"):
            store.cancel_grant(grant["id"], uuid4())


class TestRevokeGrant:
    def test_revoke_active_grant(self, pg_conn):
        store = GrantStore(pg_conn)
        grant = store.create_grant(
            schema_name="x", relation="r", principal_id=uuid4(),
            scope_entity="E", scope_id=uuid4(), granted_by_id=uuid4(),
            approval_mode="none",
        )
        updated = store.revoke_grant(grant["id"], uuid4())
        assert updated["status"] == GrantStatus.REVOKED
        assert updated["revoked_at"] is not None
        assert updated["revoked_by_id"] is not None

    def test_revoke_pending_raises(self, pg_conn):
        store = GrantStore(pg_conn)
        grant = store.create_grant(
            schema_name="x", relation="r", principal_id=uuid4(),
            scope_entity="E", scope_id=uuid4(), granted_by_id=uuid4(),
            approval_mode="required",
        )
        with pytest.raises(ValueError, match="Cannot revoke"):
            store.revoke_grant(grant["id"], uuid4())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `TEST_DATABASE_URL=postgresql://localhost/dazzle_test pytest tests/unit/test_grant_store.py::TestApproveGrant tests/unit/test_grant_store.py::TestRejectGrant tests/unit/test_grant_store.py::TestCancelGrant tests/unit/test_grant_store.py::TestRevokeGrant -v`
Expected: FAIL

- [ ] **Step 3: Implement all four transition methods**

Add these methods to the `GrantStore` class. The `_transition` helper centralises the atomic `UPDATE WHERE status + rowcount` pattern. It accepts optional `metadata` for event recording (used by `reject_grant`).

```python
    def _transition(
        self,
        grant_id: UUID,
        from_status: GrantStatus,
        to_status: GrantStatus,
        event_type: str,
        actor_id: UUID,
        extra_sets: str = "",
        extra_params: tuple[Any, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        sets = f"status = %s{', ' + extra_sets if extra_sets else ''}"
        params = (to_status, *extra_params, grant_id, from_status)
        cursor = self._conn.execute(
            f"UPDATE _grants SET {sets} WHERE id = %s AND status = %s",
            params,
        )
        if cursor.rowcount == 0:
            row = self._conn.execute(
                "SELECT status FROM _grants WHERE id = %s", (grant_id,)
            ).fetchone()
            if row is None:
                raise ValueError(f"Grant {grant_id} not found")
            raise ValueError(
                f"Cannot {event_type} grant in status '{row['status']}'"
            )
        self._record_event(grant_id, event_type, actor_id, metadata)
        self._conn.commit()
        return self._get_grant(grant_id)

    def approve_grant(self, grant_id: UUID, approved_by_id: UUID) -> dict[str, Any]:
        now = datetime.now(UTC)
        return self._transition(
            grant_id,
            from_status=GrantStatus.PENDING_APPROVAL,
            to_status=GrantStatus.ACTIVE,
            event_type="approved",
            actor_id=approved_by_id,
            extra_sets="approved_by_id = %s, approved_at = %s",
            extra_params=(approved_by_id, now),
        )

    def reject_grant(
        self, grant_id: UUID, rejected_by_id: UUID, reason: str | None = None
    ) -> dict[str, Any]:
        metadata = {"reason": reason} if reason else None
        return self._transition(
            grant_id,
            from_status=GrantStatus.PENDING_APPROVAL,
            to_status=GrantStatus.REJECTED,
            event_type="rejected",
            actor_id=rejected_by_id,
            metadata=metadata,
        )

    def cancel_grant(self, grant_id: UUID, cancelled_by_id: UUID) -> dict[str, Any]:
        return self._transition(
            grant_id,
            from_status=GrantStatus.PENDING_APPROVAL,
            to_status=GrantStatus.CANCELLED,
            event_type="cancelled",
            actor_id=cancelled_by_id,
        )

    def revoke_grant(self, grant_id: UUID, revoked_by_id: UUID) -> dict[str, Any]:
        now = datetime.now(UTC)
        return self._transition(
            grant_id,
            from_status=GrantStatus.ACTIVE,
            to_status=GrantStatus.REVOKED,
            event_type="revoked",
            actor_id=revoked_by_id,
            extra_sets="revoked_at = %s, revoked_by_id = %s",
            extra_params=(now, revoked_by_id),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `TEST_DATABASE_URL=postgresql://localhost/dazzle_test pytest tests/unit/test_grant_store.py::TestApproveGrant tests/unit/test_grant_store.py::TestRejectGrant tests/unit/test_grant_store.py::TestCancelGrant tests/unit/test_grant_store.py::TestRevokeGrant -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_back/runtime/grant_store.py tests/unit/test_grant_store.py
git commit -m "feat(grants): atomic state transitions with optimistic concurrency

approve, reject, cancel, revoke use UPDATE WHERE status + rowcount.
Shared _transition() helper eliminates TOCTOU race conditions."
```

---

### Task 5: Query Methods — `has_active_grant`, `list_grants`, `expire_stale_grants`

**Files:**
- Modify: `src/dazzle_back/runtime/grant_store.py`
- Test: `tests/unit/test_grant_store.py`

- [ ] **Step 1: Write the failing tests**

```python
class TestHasActiveGrant:
    def test_has_active_grant_true(self, pg_conn):
        store = GrantStore(pg_conn)
        pid, sid = uuid4(), uuid4()
        store.create_grant(
            schema_name="x", relation="acting_hod", principal_id=pid,
            scope_entity="Department", scope_id=sid, granted_by_id=uuid4(),
            approval_mode="none",
        )
        assert store.has_active_grant(pid, "acting_hod", sid) is True

    def test_has_active_grant_false_pending(self, pg_conn):
        store = GrantStore(pg_conn)
        pid, sid = uuid4(), uuid4()
        store.create_grant(
            schema_name="x", relation="acting_hod", principal_id=pid,
            scope_entity="Department", scope_id=sid, granted_by_id=uuid4(),
            approval_mode="required",
        )
        assert store.has_active_grant(pid, "acting_hod", sid) is False

    def test_has_active_grant_false_expired(self, pg_conn):
        store = GrantStore(pg_conn)
        pid, sid = uuid4(), uuid4()
        store.create_grant(
            schema_name="x", relation="acting_hod", principal_id=pid,
            scope_entity="Department", scope_id=sid, granted_by_id=uuid4(),
            approval_mode="none",
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert store.has_active_grant(pid, "acting_hod", sid) is False

    def test_has_active_grant_false_revoked(self, pg_conn):
        store = GrantStore(pg_conn)
        pid, sid = uuid4(), uuid4()
        grant = store.create_grant(
            schema_name="x", relation="acting_hod", principal_id=pid,
            scope_entity="Department", scope_id=sid, granted_by_id=uuid4(),
            approval_mode="none",
        )
        store.revoke_grant(grant["id"], uuid4())
        assert store.has_active_grant(pid, "acting_hod", sid) is False


class TestListGrants:
    def test_list_by_scope(self, pg_conn):
        store = GrantStore(pg_conn)
        sid = uuid4()
        store.create_grant(
            schema_name="x", relation="r", principal_id=uuid4(),
            scope_entity="Department", scope_id=sid, granted_by_id=uuid4(),
            approval_mode="none",
        )
        grants = store.list_grants(scope_entity="Department", scope_id=sid)
        assert len(grants) == 1

    def test_list_by_principal(self, pg_conn):
        store = GrantStore(pg_conn)
        pid = uuid4()
        store.create_grant(
            schema_name="x", relation="r", principal_id=pid,
            scope_entity="E", scope_id=uuid4(), granted_by_id=uuid4(),
            approval_mode="none",
        )
        grants = store.list_grants(principal_id=pid)
        assert len(grants) == 1

    def test_list_by_status(self, pg_conn):
        store = GrantStore(pg_conn)
        store.create_grant(
            schema_name="x", relation="r", principal_id=uuid4(),
            scope_entity="E", scope_id=uuid4(), granted_by_id=uuid4(),
            approval_mode="required",
        )
        assert len(store.list_grants(status=GrantStatus.PENDING_APPROVAL)) == 1
        assert len(store.list_grants(status=GrantStatus.ACTIVE)) == 0

    def test_list_no_filters(self, pg_conn):
        store = GrantStore(pg_conn)
        store.create_grant(
            schema_name="x", relation="r", principal_id=uuid4(),
            scope_entity="E", scope_id=uuid4(), granted_by_id=uuid4(),
            approval_mode="none",
        )
        store.create_grant(
            schema_name="y", relation="s", principal_id=uuid4(),
            scope_entity="F", scope_id=uuid4(), granted_by_id=uuid4(),
            approval_mode="required",
        )
        assert len(store.list_grants()) == 2


class TestExpireStaleGrants:
    def test_expire_stale(self, pg_conn):
        store = GrantStore(pg_conn)
        pid = uuid4()
        store.create_grant(
            schema_name="x", relation="r", principal_id=pid,
            scope_entity="E", scope_id=uuid4(), granted_by_id=uuid4(),
            approval_mode="none",
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        count = store.expire_stale_grants()
        assert count == 1
        assert len(store.list_grants(principal_id=pid, status=GrantStatus.EXPIRED)) == 1

    def test_expire_does_not_touch_future(self, pg_conn):
        store = GrantStore(pg_conn)
        store.create_grant(
            schema_name="x", relation="r", principal_id=uuid4(),
            scope_entity="E", scope_id=uuid4(), granted_by_id=uuid4(),
            approval_mode="none",
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        assert store.expire_stale_grants() == 0

    def test_expire_records_events(self, pg_conn):
        store = GrantStore(pg_conn)
        grant = store.create_grant(
            schema_name="x", relation="r", principal_id=uuid4(),
            scope_entity="E", scope_id=uuid4(), granted_by_id=uuid4(),
            approval_mode="none",
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        store.expire_stale_grants()
        events = pg_conn.execute(
            "SELECT * FROM _grant_events WHERE grant_id = %s AND event_type = 'expired'",
            (grant["id"],),
        ).fetchall()
        assert len(events) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `TEST_DATABASE_URL=postgresql://localhost/dazzle_test pytest tests/unit/test_grant_store.py::TestHasActiveGrant tests/unit/test_grant_store.py::TestListGrants tests/unit/test_grant_store.py::TestExpireStaleGrants -v`
Expected: FAIL

- [ ] **Step 3: Implement the three query methods**

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

    def list_grants(
        self,
        scope_entity: str | None = None,
        scope_id: UUID | None = None,
        principal_id: UUID | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if scope_entity is not None:
            clauses.append("scope_entity = %s")
            params.append(scope_entity)
        if scope_id is not None:
            clauses.append("scope_id = %s")
            params.append(scope_id)
        if principal_id is not None:
            clauses.append("principal_id = %s")
            params.append(principal_id)
        if status is not None:
            clauses.append("status = %s")
            params.append(status)
        where = " AND ".join(clauses) if clauses else "TRUE"
        rows = self._conn.execute(
            f"SELECT * FROM _grants WHERE {where} ORDER BY granted_at DESC",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def expire_stale_grants(self) -> int:
        now = datetime.now(UTC)
        cursor = self._conn.execute(
            """UPDATE _grants SET status = %s
               WHERE status = %s AND expires_at IS NOT NULL AND expires_at <= %s
               RETURNING id""",
            (GrantStatus.EXPIRED, GrantStatus.ACTIVE, now),
        )
        expired = cursor.fetchall()
        system_actor = UUID(int=0)
        for row in expired:
            self._record_event(row["id"], "expired", system_actor)
        if expired:
            self._conn.commit()
        return len(expired)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `TEST_DATABASE_URL=postgresql://localhost/dazzle_test pytest tests/unit/test_grant_store.py::TestHasActiveGrant tests/unit/test_grant_store.py::TestListGrants tests/unit/test_grant_store.py::TestExpireStaleGrants -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/dazzle_back/runtime/grant_store.py tests/unit/test_grant_store.py
git commit -m "feat(grants): has_active_grant, list_grants, expire_stale_grants

Dynamic WHERE for list_grants (replaces IS NULL OR anti-pattern).
RETURNING id for expire_stale_grants. Native TIMESTAMPTZ comparisons."
```

---

### Task 6: Concurrency Tests

**Files:**
- Test: `tests/unit/test_grant_store.py`

Verify the key correctness property: two concurrent transitions on the same grant yield exactly one success.

- [ ] **Step 1: Write the concurrency tests**

```python
class TestConcurrency:
    def test_concurrent_approve_one_wins(self, pg_grant_conn_factory):
        """Two connections approve the same grant — exactly one succeeds."""
        conn1 = pg_grant_conn_factory()
        conn1.execute("DROP TABLE IF EXISTS _grant_events, _grants")
        conn1.commit()
        store1 = GrantStore(conn1)

        grant = store1.create_grant(
            schema_name="x", relation="r", principal_id=uuid4(),
            scope_entity="E", scope_id=uuid4(), granted_by_id=uuid4(),
            approval_mode="required",
        )
        grant_id = grant["id"]

        conn2 = pg_grant_conn_factory()
        store2 = GrantStore.__new__(GrantStore)
        store2._conn = conn2

        results = []
        for s in [store1, store2]:
            try:
                s.approve_grant(grant_id, uuid4())
                results.append("ok")
            except ValueError:
                results.append("conflict")

        assert results.count("ok") == 1
        assert results.count("conflict") == 1

        conn1.close()
        conn2.close()

    def test_concurrent_approve_and_reject(self, pg_grant_conn_factory):
        """One approve + one reject — exactly one succeeds."""
        conn1 = pg_grant_conn_factory()
        conn1.execute("DROP TABLE IF EXISTS _grant_events, _grants")
        conn1.commit()
        store1 = GrantStore(conn1)

        grant = store1.create_grant(
            schema_name="x", relation="r", principal_id=uuid4(),
            scope_entity="E", scope_id=uuid4(), granted_by_id=uuid4(),
            approval_mode="required",
        )
        grant_id = grant["id"]

        conn2 = pg_grant_conn_factory()
        store2 = GrantStore.__new__(GrantStore)
        store2._conn = conn2

        # store1 approves
        store1.approve_grant(grant_id, uuid4())

        # store2 tries to reject — should fail
        with pytest.raises(ValueError, match="Cannot reject"):
            store2.reject_grant(grant_id, uuid4())

        conn1.close()
        conn2.close()
```

- [ ] **Step 2: Run tests**

Run: `TEST_DATABASE_URL=postgresql://localhost/dazzle_test pytest tests/unit/test_grant_store.py::TestConcurrency -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_grant_store.py
git commit -m "test(grants): concurrency tests verify one-winner property

Two connections racing on the same grant — exactly one succeeds."
```

---

### Task 7: Update `grant_routes.py`

**Files:**
- Modify: `src/dazzle_back/runtime/grant_routes.py`

Drop placeholder parameter, add UUID validation at HTTP boundary, add cancel endpoint.

- [ ] **Step 1: Update `_get_store` — remove `placeholder`**

In `grant_routes.py`, change:

```python
# Old
return GrantStore(conn_factory(), placeholder="%s")

# New
return GrantStore(conn_factory())
```

- [ ] **Step 2: Fix docstring**

Change `conn_factory` docstring from:
```
conn_factory: Callable returning a sqlite3 Connection for GrantStore.
```
To:
```
conn_factory: Callable returning a psycopg Connection for GrantStore.
```

- [ ] **Step 3: Add `_parse_uuid` helper**

```python
from uuid import UUID

def _parse_uuid(value: str, field_name: str) -> UUID:
    try:
        return UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail=f"Invalid UUID for {field_name}")
```

- [ ] **Step 4: Add cancel endpoint**

After the reject endpoint, add:

```python
@router.post("/{grant_id}/cancel", summary="Cancel a pending grant")
async def cancel_grant(
    grant_id: str,
    auth_context: AuthContext = Depends(auth_dep),
) -> dict[str, Any]:
    user_id = _get_user_id(auth_context)
    parsed_id = _parse_uuid(grant_id, "grant_id")
    store = _get_store()
    try:
        grant = store._get_grant(parsed_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Grant not found")

    user_roles = _get_user_roles(auth_context)
    _check_granted_by(grant["schema_name"], user_roles)

    try:
        result = store.cancel_grant(parsed_id, UUID(user_id))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"grant": result}
```

- [ ] **Step 5: Run lint and type checks**

Run: `ruff check src/dazzle_back/runtime/grant_routes.py src/dazzle_back/runtime/grant_store.py --fix && mypy src/dazzle_back/runtime/grant_store.py src/dazzle_back/runtime/grant_routes.py`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add src/dazzle_back/runtime/grant_routes.py
git commit -m "feat(grants): update grant_routes for PostgreSQL-only store

Drop placeholder param, add UUID validation, add cancel endpoint,
fix docstring to reference psycopg."
```

---

### Task 8: Update Integration Test

**Files:**
- Modify: `tests/unit/test_grant_integration.py`

Swap SQLite for PostgreSQL in the end-to-end pipeline test: DSL parse → GrantStore → condition evaluation.

- [ ] **Step 1: Rewrite the integration test**

Replace the SQLite setup with PostgreSQL:

```python
import os
from pathlib import Path
from uuid import uuid4

import pytest
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle_back.runtime.condition_evaluator import evaluate_condition
from dazzle_back.runtime.grant_store import GrantStore


@pytest.fixture
def pg_integration_conn():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    import psycopg
    from psycopg.rows import dict_row
    conn = psycopg.connect(url, row_factory=dict_row)
    conn.execute("DROP TABLE IF EXISTS _grant_events, _grants")
    conn.commit()
    yield conn
    conn.close()


class TestGrantPipelineIntegration:
    def test_parse_to_evaluation_pipeline(self, pg_integration_conn):
        """Parse grant_schema DSL, create grant in store, evaluate condition."""
        dsl = """module test_mod

entity Department "Department":
  id: uuid pk
  name: str(200)

entity AssessmentEvent "Assessment Event":
  id: uuid pk
  department: ref Department
  access:
    read: role(hod) or has_grant("acting_hod", department)
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))

        entity = [e for e in fragment.entities if e.name == "AssessmentEvent"][0]
        read_rules = [r for r in entity.access.permissions if r.operation.value == "read"]
        assert read_rules
        cond = read_rules[0].condition
        assert cond.is_compound
        assert cond.right.grant_check is not None

        store = GrantStore(pg_integration_conn)
        user_id = uuid4()
        dept_id = uuid4()

        store.create_grant(
            schema_name="dept_delegation",
            relation="acting_hod",
            principal_id=user_id,
            scope_entity="Department",
            scope_id=dept_id,
            granted_by_id=uuid4(),
            approval_mode="none",
        )

        active_grants = store.list_grants(principal_id=user_id, status="active")
        condition_dict = cond.model_dump()
        record = {"department": str(dept_id)}
        context = {"user_roles": [], "active_grants": active_grants}

        result = evaluate_condition(condition_dict, record, context)
        assert result is True

    def test_parse_to_evaluation_no_grant(self, pg_integration_conn):
        """User without grant fails has_grant() check."""
        dsl = """module test_mod

entity Department "Department":
  id: uuid pk
  name: str(200)

entity AssessmentEvent "Assessment Event":
  id: uuid pk
  department: ref Department
  access:
    read: has_grant("acting_hod", department)
"""
        _, _, _, _, _, fragment = parse_dsl(dsl, Path("test.dsl"))
        entity = [e for e in fragment.entities if e.name == "AssessmentEvent"][0]
        read_rules = [r for r in entity.access.permissions if r.operation.value == "read"]
        cond = read_rules[0].condition
        condition_dict = cond.model_dump()

        # Need a store instance just to ensure tables exist (for list_grants)
        GrantStore(pg_integration_conn)

        record = {"department": str(uuid4())}
        context = {"active_grants": []}

        result = evaluate_condition(condition_dict, record, context)
        assert result is False
```

- [ ] **Step 2: Run the integration tests**

Run: `TEST_DATABASE_URL=postgresql://localhost/dazzle_test pytest tests/unit/test_grant_integration.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_grant_integration.py
git commit -m "test(grants): integration test uses PostgreSQL instead of SQLite

DSL parse → GrantStore → condition evaluation pipeline now runs
against real PostgreSQL."
```

---

### Task 9: Final Verification and Cleanup

**Files:**
- All modified files

Run full lint, type check, and test suite to ensure nothing is broken.

- [ ] **Step 1: Run ruff**

Run: `ruff check src/dazzle_back/runtime/grant_store.py src/dazzle_back/runtime/grant_routes.py tests/unit/test_grant_store.py tests/unit/test_grant_integration.py --fix && ruff format src/dazzle_back/runtime/grant_store.py src/dazzle_back/runtime/grant_routes.py tests/unit/test_grant_store.py tests/unit/test_grant_integration.py`
Expected: No errors

- [ ] **Step 2: Run mypy**

Run: `mypy src/dazzle_back/runtime/grant_store.py src/dazzle_back/runtime/grant_routes.py`
Expected: No errors (or only pre-existing unrelated warnings)

- [ ] **Step 3: Run all grant tests**

Run: `TEST_DATABASE_URL=postgresql://localhost/dazzle_test pytest tests/unit/test_grant_store.py tests/unit/test_grant_integration.py tests/unit/test_workspace_rendering_grants.py -v`
Expected: All PASS

- [ ] **Step 4: Run full unit test suite**

Run: `pytest tests/ -m "not e2e" --timeout=60 -x -q`
Expected: All pass. Grant tests that need PostgreSQL skip cleanly when `TEST_DATABASE_URL` is absent.

- [ ] **Step 5: Verify no sqlite3 imports remain in grant code**

Run: `grep -rn "sqlite" src/dazzle_back/runtime/grant_store.py src/dazzle_back/runtime/grant_routes.py`
Expected: No output

- [ ] **Step 6: Commit any final fixups**

```bash
git add -u
git commit -m "chore(grants): final lint and type check fixes"
```
