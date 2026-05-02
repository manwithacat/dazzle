"""Tests for #956 cycle 3 — audit-trail diff computation + emitter.

Cycle 2 added the AuditEntry destination table. Cycle 3 builds the
pure diff computation (`compute_diff`) and the
service-callback-shaped emitter (`build_audit_callbacks`) that cycle
4 will register against `BaseService.on_*`.

These tests verify:

  * Only tracked fields produce rows
  * `track=[]` captures every field
  * Unchanged tracked fields are skipped on update
  * CREATE emits one row per tracked field with `before_value=null`
  * DELETE emits one row per tracked field with `after_value=null`
  * before/after_value are JSON-encoded (UUIDs / datetimes round-trip)
  * Writer failures don't break the callback (best-effort)
  * user_id_provider failures don't break the callback
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from uuid import uuid4

import pytest

from dazzle_back.runtime.audit_emitter import build_audit_callbacks, compute_diff

# ---------------------------------------------------------------------------
# compute_diff
# ---------------------------------------------------------------------------


class TestComputeDiff:
    def test_unchanged_field_skipped_on_update(self):
        rows = compute_diff(
            entity_type="Manuscript",
            entity_id="abc",
            old_data={"status": "draft"},
            new_data={"status": "draft"},
            track=["status"],
            operation="update",
        )
        assert rows == []

    def test_changed_field_emitted(self):
        rows = compute_diff(
            entity_type="Manuscript",
            entity_id="abc",
            old_data={"status": "draft"},
            new_data={"status": "submitted"},
            track=["status"],
            operation="update",
            by_user_id="user-1",
        )
        assert len(rows) == 1
        row = rows[0]
        assert row["entity_type"] == "Manuscript"
        assert row["entity_id"] == "abc"
        assert row["field_name"] == "status"
        assert row["operation"] == "update"
        assert row["before_value"] == json.dumps("draft")
        assert row["after_value"] == json.dumps("submitted")
        assert row["by_user_id"] == "user-1"

    def test_only_tracked_fields_emitted(self):
        # `title` changed but isn't in the track list — no row.
        rows = compute_diff(
            entity_type="Manuscript",
            entity_id="abc",
            old_data={"status": "draft", "title": "Old"},
            new_data={"status": "draft", "title": "New"},
            track=["status"],
            operation="update",
        )
        assert rows == []

    def test_empty_track_means_all_fields(self):
        rows = compute_diff(
            entity_type="Manuscript",
            entity_id="abc",
            old_data={"status": "draft", "title": "Old"},
            new_data={"status": "submitted", "title": "New"},
            track=[],
            operation="update",
        )
        names = {r["field_name"] for r in rows}
        assert names == {"status", "title"}

    def test_create_emits_per_tracked_field(self):
        rows = compute_diff(
            entity_type="Manuscript",
            entity_id="abc",
            old_data=None,
            new_data={"status": "draft", "title": "New"},
            track=["status", "title"],
            operation="create",
        )
        assert len(rows) == 2
        for row in rows:
            assert row["operation"] == "create"
            assert row["before_value"] is None
            assert row["after_value"] is not None

    def test_delete_emits_per_tracked_field(self):
        rows = compute_diff(
            entity_type="Manuscript",
            entity_id="abc",
            old_data={"status": "draft", "title": "Old"},
            new_data=None,
            track=["status", "title"],
            operation="delete",
        )
        assert len(rows) == 2
        for row in rows:
            assert row["operation"] == "delete"
            assert row["after_value"] is None
            assert row["before_value"] is not None

    def test_uuid_round_trip_via_safe_json(self):
        uid = uuid4()
        rows = compute_diff(
            entity_type="Manuscript",
            entity_id="abc",
            old_data={"owner_id": None},
            new_data={"owner_id": uid},
            track=["owner_id"],
            operation="update",
        )
        assert json.loads(rows[0]["after_value"]) == str(uid)

    def test_datetime_round_trip(self):
        when = datetime(2026, 5, 1, 12, 30, 0)
        rows = compute_diff(
            entity_type="Manuscript",
            entity_id="abc",
            old_data={"submitted_at": None},
            new_data={"submitted_at": when},
            track=["submitted_at"],
            operation="update",
        )
        # `default=str` produces "YYYY-MM-DD HH:MM:SS" (datetime.__str__),
        # not isoformat — round-trip is the contract, exact format is
        # an implementation detail.
        assert json.loads(rows[0]["after_value"]) == str(when)

    def test_both_sides_none_emits_nothing(self):
        rows = compute_diff(
            entity_type="Manuscript",
            entity_id="abc",
            old_data=None,
            new_data=None,
            track=["status"],
            operation="update",
        )
        assert rows == []

    def test_missing_field_treated_as_none(self):
        # Tracked field absent from old_data — the diff must still
        # detect "added" rather than crash on KeyError.
        rows = compute_diff(
            entity_type="Manuscript",
            entity_id="abc",
            old_data={},
            new_data={"status": "draft"},
            track=["status"],
            operation="update",
        )
        assert len(rows) == 1
        assert rows[0]["before_value"] is None
        assert json.loads(rows[0]["after_value"]) == "draft"


# ---------------------------------------------------------------------------
# build_audit_callbacks
# ---------------------------------------------------------------------------


class TestBuildAuditCallbacks:
    @pytest.fixture()
    def captured(self):
        return {"rows": []}

    @pytest.fixture()
    def writer(self, captured):
        async def _write(rows):
            captured["rows"].extend(rows)

        return _write

    def test_returns_three_callbacks(self, writer):
        cbs = build_audit_callbacks(entity_type="X", track=["a"], writer=writer)
        assert set(cbs) == {"on_created", "on_updated", "on_deleted"}

    def test_on_updated_writes_diff(self, writer, captured):
        cbs = build_audit_callbacks(
            entity_type="Manuscript",
            track=["status"],
            writer=writer,
            user_id_provider=lambda: "user-1",
        )
        asyncio.run(
            cbs["on_updated"]("abc", {"status": "submitted"}, {"status": "draft"}, "updated")
        )
        assert len(captured["rows"]) == 1
        assert captured["rows"][0]["by_user_id"] == "user-1"
        assert captured["rows"][0]["operation"] == "update"

    def test_on_created_writes_per_field(self, writer, captured):
        cbs = build_audit_callbacks(
            entity_type="Manuscript",
            track=["status", "title"],
            writer=writer,
        )
        asyncio.run(cbs["on_created"]("abc", {"status": "draft", "title": "T"}, None, "created"))
        assert len(captured["rows"]) == 2
        assert all(r["operation"] == "create" for r in captured["rows"])

    def test_on_deleted_writes_per_field(self, writer, captured):
        cbs = build_audit_callbacks(
            entity_type="Manuscript",
            track=["status"],
            writer=writer,
        )
        asyncio.run(cbs["on_deleted"]("abc", {"status": "draft"}, None, "deleted"))
        assert len(captured["rows"]) == 1
        assert captured["rows"][0]["operation"] == "delete"

    def test_writer_exception_swallowed(self, captured):
        async def broken_writer(rows):
            raise RuntimeError("DB down")

        cbs = build_audit_callbacks(
            entity_type="Manuscript", track=["status"], writer=broken_writer
        )
        # Must NOT raise — audit failures are best-effort and must
        # never break the user's mutation.
        asyncio.run(
            cbs["on_updated"]("abc", {"status": "submitted"}, {"status": "draft"}, "updated")
        )

    def test_no_writes_when_nothing_changed(self, writer, captured):
        cbs = build_audit_callbacks(entity_type="Manuscript", track=["status"], writer=writer)
        asyncio.run(cbs["on_updated"]("abc", {"status": "draft"}, {"status": "draft"}, "updated"))
        assert captured["rows"] == []

    def test_user_id_provider_failure_swallowed(self, writer, captured):
        def broken_provider():
            raise RuntimeError("ContextVar empty")

        cbs = build_audit_callbacks(
            entity_type="Manuscript",
            track=["status"],
            writer=writer,
            user_id_provider=broken_provider,
        )
        asyncio.run(
            cbs["on_updated"]("abc", {"status": "submitted"}, {"status": "draft"}, "updated")
        )
        # Row written with by_user_id=None — provider failure shouldn't
        # block the audit row.
        assert len(captured["rows"]) == 1
        assert captured["rows"][0]["by_user_id"] is None
