# tests/unit/test_grant_store.py
"""Tests for runtime grant store (PostgreSQL)."""

import json
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg.rows import dict_row

from dazzle_back.runtime.grant_store import GrantStatus, GrantStore


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


class TestPgConnectivity:
    def test_connection_works(self, pg_conn):
        row = pg_conn.execute("SELECT 1 AS ok").fetchone()
        assert row["ok"] == 1


class TestGrantStoreInit:
    def test_tables_created(self, pg_conn):
        GrantStore(pg_conn)
        row = pg_conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename LIKE '_grant%'"
        ).fetchall()
        tables = {r["tablename"] for r in row}
        assert "_grants" in tables
        assert "_grant_events" in tables

    def test_check_constraint_on_status(self, pg_conn):
        GrantStore(pg_conn)
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
        GrantStore(pg_conn)
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


class TestApproveGrant:
    def test_approve_pending_grant(self, pg_conn):
        store = GrantStore(pg_conn)
        grant = store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=uuid4(),
            scope_entity="E",
            scope_id=uuid4(),
            granted_by_id=uuid4(),
            approval_mode="required",
        )
        updated = store.approve_grant(grant["id"], uuid4())
        assert updated["status"] == GrantStatus.ACTIVE
        assert updated["approved_by_id"] is not None
        assert updated["approved_at"] is not None

    def test_approve_non_pending_raises(self, pg_conn):
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
            schema_name="x",
            relation="r",
            principal_id=uuid4(),
            scope_entity="E",
            scope_id=uuid4(),
            granted_by_id=uuid4(),
            approval_mode="required",
        )
        updated = store.reject_grant(grant["id"], uuid4(), reason="Not needed")
        assert updated["status"] == GrantStatus.REJECTED

    def test_reject_active_raises(self, pg_conn):
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
        with pytest.raises(ValueError, match="Cannot reject"):
            store.reject_grant(grant["id"], uuid4())

    def test_reject_records_reason_metadata(self, pg_conn):
        store = GrantStore(pg_conn)
        grant = store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=uuid4(),
            scope_entity="E",
            scope_id=uuid4(),
            granted_by_id=uuid4(),
            approval_mode="required",
        )
        store.reject_grant(grant["id"], uuid4(), reason="Not needed")
        events = pg_conn.execute(
            "SELECT * FROM _grant_events WHERE grant_id = %s AND event_type = 'rejected'",
            (grant["id"],),
        ).fetchall()
        assert len(events) == 1
        meta = events[0]["metadata"]
        if isinstance(meta, str):
            meta = json.loads(meta)
        assert meta["reason"] == "Not needed"


class TestCancelGrant:
    def test_cancel_pending_grant(self, pg_conn):
        store = GrantStore(pg_conn)
        granter = uuid4()
        grant = store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=uuid4(),
            scope_entity="E",
            scope_id=uuid4(),
            granted_by_id=granter,
            approval_mode="required",
        )
        updated = store.cancel_grant(grant["id"], granter)
        assert updated["status"] == GrantStatus.CANCELLED

    def test_cancel_active_raises(self, pg_conn):
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
        with pytest.raises(ValueError, match="Cannot cancel"):
            store.cancel_grant(grant["id"], uuid4())


class TestRevokeGrant:
    def test_revoke_active_grant(self, pg_conn):
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
        updated = store.revoke_grant(grant["id"], uuid4())
        assert updated["status"] == GrantStatus.REVOKED
        assert updated["revoked_at"] is not None
        assert updated["revoked_by_id"] is not None

    def test_revoke_pending_raises(self, pg_conn):
        store = GrantStore(pg_conn)
        grant = store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=uuid4(),
            scope_entity="E",
            scope_id=uuid4(),
            granted_by_id=uuid4(),
            approval_mode="required",
        )
        with pytest.raises(ValueError, match="Cannot revoke"):
            store.revoke_grant(grant["id"], uuid4())


class TestHasActiveGrant:
    def test_has_active_grant_true(self, pg_conn):
        store = GrantStore(pg_conn)
        pid, sid = uuid4(), uuid4()
        store.create_grant(
            schema_name="x",
            relation="acting_hod",
            principal_id=pid,
            scope_entity="Department",
            scope_id=sid,
            granted_by_id=uuid4(),
            approval_mode="none",
        )
        assert store.has_active_grant(pid, "acting_hod", sid) is True

    def test_has_active_grant_false_pending(self, pg_conn):
        store = GrantStore(pg_conn)
        pid, sid = uuid4(), uuid4()
        store.create_grant(
            schema_name="x",
            relation="acting_hod",
            principal_id=pid,
            scope_entity="Department",
            scope_id=sid,
            granted_by_id=uuid4(),
            approval_mode="required",
        )
        assert store.has_active_grant(pid, "acting_hod", sid) is False

    def test_has_active_grant_false_expired(self, pg_conn):
        store = GrantStore(pg_conn)
        pid, sid = uuid4(), uuid4()
        store.create_grant(
            schema_name="x",
            relation="acting_hod",
            principal_id=pid,
            scope_entity="Department",
            scope_id=sid,
            granted_by_id=uuid4(),
            approval_mode="none",
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        assert store.has_active_grant(pid, "acting_hod", sid) is False

    def test_has_active_grant_false_revoked(self, pg_conn):
        store = GrantStore(pg_conn)
        pid, sid = uuid4(), uuid4()
        grant = store.create_grant(
            schema_name="x",
            relation="acting_hod",
            principal_id=pid,
            scope_entity="Department",
            scope_id=sid,
            granted_by_id=uuid4(),
            approval_mode="none",
        )
        store.revoke_grant(grant["id"], uuid4())
        assert store.has_active_grant(pid, "acting_hod", sid) is False


class TestListGrants:
    def test_list_by_scope(self, pg_conn):
        store = GrantStore(pg_conn)
        sid = uuid4()
        store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=uuid4(),
            scope_entity="Department",
            scope_id=sid,
            granted_by_id=uuid4(),
            approval_mode="none",
        )
        grants = store.list_grants(scope_entity="Department", scope_id=sid)
        assert len(grants) == 1

    def test_list_by_principal(self, pg_conn):
        store = GrantStore(pg_conn)
        pid = uuid4()
        store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=pid,
            scope_entity="E",
            scope_id=uuid4(),
            granted_by_id=uuid4(),
            approval_mode="none",
        )
        grants = store.list_grants(principal_id=pid)
        assert len(grants) == 1

    def test_list_by_status(self, pg_conn):
        store = GrantStore(pg_conn)
        store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=uuid4(),
            scope_entity="E",
            scope_id=uuid4(),
            granted_by_id=uuid4(),
            approval_mode="required",
        )
        assert len(store.list_grants(status=GrantStatus.PENDING_APPROVAL)) == 1
        assert len(store.list_grants(status=GrantStatus.ACTIVE)) == 0

    def test_list_no_filters(self, pg_conn):
        store = GrantStore(pg_conn)
        store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=uuid4(),
            scope_entity="E",
            scope_id=uuid4(),
            granted_by_id=uuid4(),
            approval_mode="none",
        )
        store.create_grant(
            schema_name="y",
            relation="s",
            principal_id=uuid4(),
            scope_entity="F",
            scope_id=uuid4(),
            granted_by_id=uuid4(),
            approval_mode="required",
        )
        assert len(store.list_grants()) == 2


class TestExpireStaleGrants:
    def test_expire_stale(self, pg_conn):
        store = GrantStore(pg_conn)
        pid = uuid4()
        store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=pid,
            scope_entity="E",
            scope_id=uuid4(),
            granted_by_id=uuid4(),
            approval_mode="none",
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        count = store.expire_stale_grants()
        assert count == 1
        assert len(store.list_grants(principal_id=pid, status=GrantStatus.EXPIRED)) == 1

    def test_expire_does_not_touch_future(self, pg_conn):
        store = GrantStore(pg_conn)
        store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=uuid4(),
            scope_entity="E",
            scope_id=uuid4(),
            granted_by_id=uuid4(),
            approval_mode="none",
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        assert store.expire_stale_grants() == 0

    def test_expire_records_events(self, pg_conn):
        store = GrantStore(pg_conn)
        grant = store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=uuid4(),
            scope_entity="E",
            scope_id=uuid4(),
            granted_by_id=uuid4(),
            approval_mode="none",
            expires_at=datetime.now(UTC) - timedelta(hours=1),
        )
        store.expire_stale_grants()
        events = pg_conn.execute(
            "SELECT * FROM _grant_events WHERE grant_id = %s AND event_type = 'expired'",
            (grant["id"],),
        ).fetchall()
        assert len(events) == 1


class TestConcurrency:
    def test_concurrent_approve_one_wins(self, pg_grant_conn_factory):
        """Two connections approve the same grant — exactly one succeeds."""
        conn1 = pg_grant_conn_factory()
        conn1.execute("DROP TABLE IF EXISTS _grant_events, _grants")
        conn1.commit()
        store1 = GrantStore(conn1)

        grant = store1.create_grant(
            schema_name="x",
            relation="r",
            principal_id=uuid4(),
            scope_entity="E",
            scope_id=uuid4(),
            granted_by_id=uuid4(),
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
            schema_name="x",
            relation="r",
            principal_id=uuid4(),
            scope_entity="E",
            scope_id=uuid4(),
            granted_by_id=uuid4(),
            approval_mode="required",
        )
        grant_id = grant["id"]

        conn2 = pg_grant_conn_factory()
        store2 = GrantStore.__new__(GrantStore)
        store2._conn = conn2

        # store1 approves first
        store1.approve_grant(grant_id, uuid4())

        # store2 tries to reject — should fail
        with pytest.raises(ValueError, match="Cannot reject"):
            store2.reject_grant(grant_id, uuid4())

        conn1.close()
        conn2.close()
