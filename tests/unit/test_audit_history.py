"""Tests for #956 cycle 6 — audit history reader.

Cycle 4 wires the writer; cycle 6 builds the read-side primitives the
detail-surface ``history`` region (cycle 7) will consume.

These tests verify:

  * `decode_audit_row` round-trips the JSON-encoded before/after
    values written by cycle 3
  * Decode is tolerant of missing keys (future schema rows)
  * Decode falls back to raw string for unparseable JSON
  * `group_by_change` collapses N field-rows from one mutation into
    a single HistoryChange with N entries in `fields`
  * Different (at, user, operation) tuples produce separate changes
"""

from __future__ import annotations

import json
from datetime import datetime

from dazzle_back.runtime.audit_history import (
    HistoryChange,
    HistoryEntry,
    decode_audit_row,
    group_by_change,
)

# ---------------------------------------------------------------------------
# decode_audit_row
# ---------------------------------------------------------------------------


class TestDecodeAuditRow:
    def test_roundtrip_via_safe_decode(self):
        row = {
            "at": datetime(2026, 5, 3, 12, 0, 0),
            "entity_type": "Manuscript",
            "entity_id": "abc",
            "field_name": "status",
            "operation": "update",
            "before_value": json.dumps("draft"),
            "after_value": json.dumps("submitted"),
            "by_user_id": "user-1",
        }
        entry = decode_audit_row(row)
        assert entry.entity_type == "Manuscript"
        assert entry.field_name == "status"
        assert entry.decoded_before == "draft"
        assert entry.decoded_after == "submitted"
        assert entry.by_user_id == "user-1"

    def test_create_has_none_before(self):
        row = {
            "at": "2026-05-03T12:00:00",
            "entity_type": "M",
            "entity_id": "x",
            "field_name": "status",
            "operation": "create",
            "before_value": None,
            "after_value": json.dumps("draft"),
            "by_user_id": None,
        }
        entry = decode_audit_row(row)
        assert entry.before is None
        assert entry.decoded_before is None
        assert entry.decoded_after == "draft"
        assert entry.by_user_id is None

    def test_delete_has_none_after(self):
        row = {
            "at": "2026-05-03T12:00:00",
            "entity_type": "M",
            "entity_id": "x",
            "field_name": "status",
            "operation": "delete",
            "before_value": json.dumps("submitted"),
            "after_value": None,
            "by_user_id": "user-1",
        }
        entry = decode_audit_row(row)
        assert entry.decoded_before == "submitted"
        assert entry.decoded_after is None

    def test_unparseable_json_falls_back_to_raw(self):
        # Hand-written / future-format row with non-JSON value.
        row = {
            "at": "2026-05-03T12:00:00",
            "entity_type": "M",
            "entity_id": "x",
            "field_name": "status",
            "operation": "update",
            "before_value": "not-json",
            "after_value": json.dumps("ok"),
            "by_user_id": None,
        }
        entry = decode_audit_row(row)
        # Decode falls back to the raw string rather than crashing.
        assert entry.decoded_before == "not-json"
        assert entry.decoded_after == "ok"

    def test_missing_keys_default_safely(self):
        # Future schema rows may omit fields — decoder must not crash.
        entry = decode_audit_row({"at": "now"})
        assert entry.entity_type == ""
        assert entry.entity_id == ""
        assert entry.field_name == ""
        assert entry.operation == "update"  # default for tolerant render
        assert entry.before is None
        assert entry.after is None

    def test_decoded_value_handles_complex_types(self):
        # JSON round-trips dicts/lists.
        row = {
            "at": "2026-05-03T12:00:00",
            "entity_type": "M",
            "entity_id": "x",
            "field_name": "tags",
            "operation": "update",
            "before_value": json.dumps([]),
            "after_value": json.dumps(["draft", "review"]),
            "by_user_id": "u",
        }
        entry = decode_audit_row(row)
        assert entry.decoded_before == []
        assert entry.decoded_after == ["draft", "review"]


# ---------------------------------------------------------------------------
# group_by_change
# ---------------------------------------------------------------------------


def _entry(*, at, field_name, by="user-1", op="update", entity_id="x", entity_type="M"):
    return HistoryEntry(
        at=at,
        entity_type=entity_type,
        entity_id=entity_id,
        field_name=field_name,
        operation=op,
        before=None,
        after=None,
        decoded_before=None,
        decoded_after=None,
        by_user_id=by,
    )


class TestGroupByChange:
    def test_empty_input(self):
        assert group_by_change([]) == []

    def test_single_entry(self):
        entries = [_entry(at="2026-05-03T12:00:00", field_name="status")]
        changes = group_by_change(entries)
        assert len(changes) == 1
        assert isinstance(changes[0], HistoryChange)
        assert len(changes[0].fields) == 1
        assert changes[0].fields[0].field_name == "status"

    def test_multiple_fields_same_change_grouped(self):
        # One mutation touching two tracked fields → cycle-3 emits two
        # rows → cycle-6 groups into one HistoryChange with 2 fields.
        same_at = "2026-05-03T12:00:00"
        entries = [
            _entry(at=same_at, field_name="status"),
            _entry(at=same_at, field_name="title"),
        ]
        changes = group_by_change(entries)
        assert len(changes) == 1
        names = [e.field_name for e in changes[0].fields]
        assert names == ["status", "title"]

    def test_different_timestamps_split(self):
        entries = [
            _entry(at="2026-05-03T12:00:00", field_name="status"),
            _entry(at="2026-05-03T12:00:01", field_name="title"),
        ]
        changes = group_by_change(entries)
        assert len(changes) == 2

    def test_different_users_split(self):
        same_at = "2026-05-03T12:00:00"
        entries = [
            _entry(at=same_at, field_name="status", by="user-1"),
            _entry(at=same_at, field_name="title", by="user-2"),
        ]
        changes = group_by_change(entries)
        assert len(changes) == 2

    def test_different_operations_split(self):
        same_at = "2026-05-03T12:00:00"
        entries = [
            _entry(at=same_at, field_name="status", op="update"),
            _entry(at=same_at, field_name="title", op="create"),
        ]
        changes = group_by_change(entries)
        assert len(changes) == 2

    def test_different_entity_ids_split(self):
        # Two changes to different rows of the same entity type at
        # the same instant — must NOT collapse.
        same_at = "2026-05-03T12:00:00"
        entries = [
            _entry(at=same_at, field_name="status", entity_id="row-1"),
            _entry(at=same_at, field_name="status", entity_id="row-2"),
        ]
        changes = group_by_change(entries)
        assert len(changes) == 2

    def test_change_facets_propagate(self):
        # The grouped HistoryChange carries the shared facets so the
        # template can render "Daisy changed Manuscript at 12:00" once
        # rather than reading them off the first field row.
        same_at = "2026-05-03T12:00:00"
        entries = [
            _entry(at=same_at, field_name="status", by="user-1"),
            _entry(at=same_at, field_name="title", by="user-1"),
        ]
        change = group_by_change(entries)[0]
        assert change.at == same_at
        assert change.by_user_id == "user-1"
        assert change.operation == "update"
        assert change.entity_type == "M"
        assert change.entity_id == "x"
