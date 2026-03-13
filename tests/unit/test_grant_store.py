# tests/unit/test_grant_store.py
"""Tests for runtime grant store."""

import sqlite3
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from dazzle_back.runtime.grant_store import GrantStatus, GrantStore


@pytest.fixture
def db():
    """In-memory SQLite for testing."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()


@pytest.fixture
def store(db):
    """Grant store backed by in-memory DB."""
    return GrantStore(db)


class TestGrantStoreInit:
    def test_tables_created(self, store, db):
        cursor = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '_grant%'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        assert "_grants" in tables
        assert "_grant_events" in tables


class TestCreateGrant:
    def test_create_grant_pending(self, store):
        grant = store.create_grant(
            schema_name="dept_delegation",
            relation="acting_hod",
            principal_id=str(uuid4()),
            scope_entity="Department",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="required",
        )
        assert grant["status"] == GrantStatus.PENDING_APPROVAL

    def test_create_grant_immediate(self, store):
        grant = store.create_grant(
            schema_name="dept_delegation",
            relation="acting_hod",
            principal_id=str(uuid4()),
            scope_entity="Department",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="immediate",
        )
        assert grant["status"] == GrantStatus.ACTIVE

    def test_create_grant_no_approval(self, store):
        grant = store.create_grant(
            schema_name="dept_delegation",
            relation="observer",
            principal_id=str(uuid4()),
            scope_entity="Department",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="none",
        )
        assert grant["status"] == GrantStatus.ACTIVE

    def test_create_grant_with_expiry(self, store):
        expires = datetime.now(UTC) + timedelta(days=90)
        grant = store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=str(uuid4()),
            scope_entity="E",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="none",
            expires_at=expires.isoformat(),
        )
        assert grant["expires_at"] is not None

    def test_create_grant_records_event(self, store, db):
        grant = store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=str(uuid4()),
            scope_entity="E",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="none",
        )
        events = db.execute(
            "SELECT * FROM _grant_events WHERE grant_id = ?", (grant["id"],)
        ).fetchall()
        assert len(events) == 1
        assert events[0]["event_type"] == "created"


class TestApproveGrant:
    def test_approve_pending_grant(self, store):
        grant = store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=str(uuid4()),
            scope_entity="E",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="required",
        )
        updated = store.approve_grant(grant["id"], str(uuid4()))
        assert updated["status"] == GrantStatus.ACTIVE
        assert updated["approved_by_id"] is not None

    def test_approve_non_pending_raises(self, store):
        grant = store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=str(uuid4()),
            scope_entity="E",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="none",
        )
        with pytest.raises(ValueError, match="Cannot approve"):
            store.approve_grant(grant["id"], str(uuid4()))


class TestRejectGrant:
    def test_reject_pending_grant(self, store):
        grant = store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=str(uuid4()),
            scope_entity="E",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="required",
        )
        updated = store.reject_grant(grant["id"], str(uuid4()), reason="Not needed")
        assert updated["status"] == GrantStatus.REJECTED

    def test_reject_active_raises(self, store):
        grant = store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=str(uuid4()),
            scope_entity="E",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="none",
        )
        with pytest.raises(ValueError, match="Cannot reject"):
            store.reject_grant(grant["id"], str(uuid4()))


class TestRevokeGrant:
    def test_revoke_active_grant(self, store):
        grant = store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=str(uuid4()),
            scope_entity="E",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="none",
        )
        updated = store.revoke_grant(grant["id"], str(uuid4()))
        assert updated["status"] == GrantStatus.REVOKED
        assert updated["revoked_at"] is not None

    def test_revoke_expired_raises(self, store):
        grant = store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=str(uuid4()),
            scope_entity="E",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="none",
            expires_at=(datetime.now(UTC) - timedelta(days=1)).isoformat(),
        )
        store.expire_stale_grants()
        with pytest.raises(ValueError, match="Cannot revoke"):
            store.revoke_grant(grant["id"], str(uuid4()))


class TestHasActiveGrant:
    def test_has_active_grant_true(self, store):
        pid = str(uuid4())
        sid = str(uuid4())
        store.create_grant(
            schema_name="x",
            relation="acting_hod",
            principal_id=pid,
            scope_entity="Department",
            scope_id=sid,
            granted_by_id=str(uuid4()),
            approval_mode="none",
        )
        assert store.has_active_grant(pid, "acting_hod", sid) is True

    def test_has_active_grant_false_pending(self, store):
        pid = str(uuid4())
        sid = str(uuid4())
        store.create_grant(
            schema_name="x",
            relation="acting_hod",
            principal_id=pid,
            scope_entity="Department",
            scope_id=sid,
            granted_by_id=str(uuid4()),
            approval_mode="required",
        )
        assert store.has_active_grant(pid, "acting_hod", sid) is False

    def test_has_active_grant_false_expired(self, store):
        pid = str(uuid4())
        sid = str(uuid4())
        store.create_grant(
            schema_name="x",
            relation="acting_hod",
            principal_id=pid,
            scope_entity="Department",
            scope_id=sid,
            granted_by_id=str(uuid4()),
            approval_mode="none",
            expires_at=(datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        )
        assert store.has_active_grant(pid, "acting_hod", sid) is False

    def test_has_active_grant_false_revoked(self, store):
        pid = str(uuid4())
        sid = str(uuid4())
        grant = store.create_grant(
            schema_name="x",
            relation="acting_hod",
            principal_id=pid,
            scope_entity="Department",
            scope_id=sid,
            granted_by_id=str(uuid4()),
            approval_mode="none",
        )
        store.revoke_grant(grant["id"], str(uuid4()))
        assert store.has_active_grant(pid, "acting_hod", sid) is False


class TestListGrants:
    def test_list_by_scope(self, store):
        sid = str(uuid4())
        store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=str(uuid4()),
            scope_entity="Department",
            scope_id=sid,
            granted_by_id=str(uuid4()),
            approval_mode="none",
        )
        grants = store.list_grants(scope_entity="Department", scope_id=sid)
        assert len(grants) == 1

    def test_list_by_principal(self, store):
        pid = str(uuid4())
        store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=pid,
            scope_entity="E",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="none",
        )
        grants = store.list_grants(principal_id=pid)
        assert len(grants) == 1

    def test_list_by_status(self, store):
        store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=str(uuid4()),
            scope_entity="E",
            scope_id=str(uuid4()),
            granted_by_id=str(uuid4()),
            approval_mode="required",
        )
        grants = store.list_grants(status=GrantStatus.PENDING_APPROVAL)
        assert len(grants) == 1
        grants = store.list_grants(status=GrantStatus.ACTIVE)
        assert len(grants) == 0


class TestExpireStaleGrants:
    def test_expire_stale(self, store):
        pid = str(uuid4())
        sid = str(uuid4())
        store.create_grant(
            schema_name="x",
            relation="r",
            principal_id=pid,
            scope_entity="E",
            scope_id=sid,
            granted_by_id=str(uuid4()),
            approval_mode="none",
            expires_at=(datetime.now(UTC) - timedelta(hours=1)).isoformat(),
        )
        count = store.expire_stale_grants()
        assert count == 1
        grants = store.list_grants(principal_id=pid, status=GrantStatus.EXPIRED)
        assert len(grants) == 1
