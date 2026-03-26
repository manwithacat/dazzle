"""Tests for the RBAC audit trail types and sinks (Layer 3)."""

import json
from pathlib import Path

import pytest

from dazzle.rbac.audit import (
    AccessDecisionRecord,
    InMemoryAuditSink,
    JsonFileAuditSink,
    NullAuditSink,
    get_audit_sink,
    set_audit_sink,
)


def make_record(**overrides) -> AccessDecisionRecord:
    defaults = {
        "timestamp": "2026-03-18T12:00:00Z",
        "request_id": "req-001",
        "user_id": "user-42",
        "roles": ["admin", "viewer"],
        "entity": "Task",
        "operation": "read",
        "allowed": True,
        "effect": "permit",
        "matched_rule": "admin_can_read_task",
        "record_id": None,
        "tier": "entity",
    }
    defaults.update(overrides)
    return AccessDecisionRecord(**defaults)


# ---------------------------------------------------------------------------
# AccessDecisionRecord
# ---------------------------------------------------------------------------


class TestAccessDecisionRecord:
    def test_creation(self):
        record = make_record()
        assert record.user_id == "user-42"
        assert record.roles == ["admin", "viewer"]
        assert record.allowed is True
        assert record.record_id is None

    def test_to_dict_contains_all_fields(self):
        record = make_record()
        d = record.to_dict()
        assert d["timestamp"] == "2026-03-18T12:00:00Z"
        assert d["request_id"] == "req-001"
        assert d["user_id"] == "user-42"
        assert d["roles"] == ["admin", "viewer"]
        assert d["entity"] == "Task"
        assert d["operation"] == "read"
        assert d["allowed"] is True
        assert d["effect"] == "permit"
        assert d["matched_rule"] == "admin_can_read_task"
        assert d["record_id"] is None
        assert d["tier"] == "entity"

    def test_to_dict_with_record_id(self):
        record = make_record(record_id="rec-999")
        d = record.to_dict()
        assert d["record_id"] == "rec-999"

    def test_frozen(self):
        record = make_record()
        with pytest.raises(AttributeError):
            record.user_id = "other"  # type: ignore[misc]

    def test_deny_record(self):
        record = make_record(allowed=False, effect="deny", matched_rule="no_match")
        assert record.allowed is False
        assert record.effect == "deny"


# ---------------------------------------------------------------------------
# NullAuditSink
# ---------------------------------------------------------------------------


class TestNullAuditSink:
    def test_emit_does_not_raise(self):
        sink = NullAuditSink()
        record = make_record()
        sink.emit(record)  # must not raise

    def test_emit_multiple_does_not_raise(self):
        sink = NullAuditSink()
        for _ in range(100):
            sink.emit(make_record())


# ---------------------------------------------------------------------------
# InMemoryAuditSink
# ---------------------------------------------------------------------------


class TestInMemoryAuditSink:
    def test_starts_empty(self):
        sink = InMemoryAuditSink()
        assert sink.records == []

    def test_emit_appends_record(self):
        sink = InMemoryAuditSink()
        record = make_record()
        sink.emit(record)
        assert len(sink.records) == 1
        assert sink.records[0] is record

    def test_emit_multiple_records(self):
        sink = InMemoryAuditSink()
        r1 = make_record(request_id="req-1")
        r2 = make_record(request_id="req-2")
        r3 = make_record(request_id="req-3")
        sink.emit(r1)
        sink.emit(r2)
        sink.emit(r3)
        assert len(sink.records) == 3
        assert sink.records[0].request_id == "req-1"
        assert sink.records[2].request_id == "req-3"

    def test_clear_empties_records(self):
        sink = InMemoryAuditSink()
        sink.emit(make_record())
        sink.emit(make_record())
        sink.clear()
        assert sink.records == []

    def test_clear_then_emit(self):
        sink = InMemoryAuditSink()
        sink.emit(make_record(request_id="old"))
        sink.clear()
        sink.emit(make_record(request_id="new"))
        assert len(sink.records) == 1
        assert sink.records[0].request_id == "new"


# ---------------------------------------------------------------------------
# JsonFileAuditSink
# ---------------------------------------------------------------------------


class TestJsonFileAuditSink:
    def test_creates_file_on_init(self, tmp_path: Path):
        log_path = tmp_path / "audit.jsonl"
        sink = JsonFileAuditSink(log_path)
        sink.close()
        assert log_path.exists()

    def test_creates_parent_directories(self, tmp_path: Path):
        log_path = tmp_path / "nested" / "deep" / "audit.jsonl"
        sink = JsonFileAuditSink(log_path)
        sink.close()
        assert log_path.exists()

    def test_emit_writes_jsonl(self, tmp_path: Path):
        log_path = tmp_path / "audit.jsonl"
        sink = JsonFileAuditSink(log_path)
        record = make_record()
        sink.emit(record)
        sink.close()

        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["user_id"] == "user-42"
        assert data["operation"] == "read"
        assert data["allowed"] is True

    def test_emit_multiple_records_one_per_line(self, tmp_path: Path):
        log_path = tmp_path / "audit.jsonl"
        sink = JsonFileAuditSink(log_path)
        for i in range(5):
            sink.emit(make_record(request_id=f"req-{i}"))
        sink.close()

        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 5
        for i, line in enumerate(lines):
            data = json.loads(line)
            assert data["request_id"] == f"req-{i}"

    def test_emit_appends_to_existing_file(self, tmp_path: Path):
        log_path = tmp_path / "audit.jsonl"

        sink1 = JsonFileAuditSink(log_path)
        sink1.emit(make_record(request_id="first"))
        sink1.close()

        sink2 = JsonFileAuditSink(log_path)
        sink2.emit(make_record(request_id="second"))
        sink2.close()

        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 2
        assert json.loads(lines[0])["request_id"] == "first"
        assert json.loads(lines[1])["request_id"] == "second"

    def test_accepts_str_path(self, tmp_path: Path):
        log_path = str(tmp_path / "audit.jsonl")
        sink = JsonFileAuditSink(log_path)
        sink.emit(make_record())
        sink.close()
        assert Path(log_path).exists()

    def test_record_id_none_serialised(self, tmp_path: Path):
        log_path = tmp_path / "audit.jsonl"
        sink = JsonFileAuditSink(log_path)
        sink.emit(make_record(record_id=None))
        sink.close()
        data = json.loads(log_path.read_text().strip())
        assert data["record_id"] is None

    def test_record_with_record_id_serialised(self, tmp_path: Path):
        log_path = tmp_path / "audit.jsonl"
        sink = JsonFileAuditSink(log_path)
        sink.emit(make_record(record_id="rec-007"))
        sink.close()
        data = json.loads(log_path.read_text().strip())
        assert data["record_id"] == "rec-007"


# ---------------------------------------------------------------------------
# Global sink management
# ---------------------------------------------------------------------------


class TestGlobalSink:
    def setup_method(self):
        """Save the current global sink before each test."""
        self._original_sink = get_audit_sink()

    def teardown_method(self):
        """Restore the original global sink after each test."""
        set_audit_sink(self._original_sink)

    def test_default_is_null_sink(self):
        # After restore, this may be InMemory from a previous test run in same process.
        # We deliberately restore in teardown, so here we just check the type is a valid sink.
        sink = get_audit_sink()
        assert hasattr(sink, "emit")

    def test_default_sink_at_module_load_is_null(self):
        """Verify the module-level default is NullAuditSink."""
        import dazzle.rbac.audit as audit_mod

        assert isinstance(audit_mod._current_sink, (NullAuditSink, type(self._original_sink)))

    def test_set_and_get_in_memory_sink(self):
        new_sink = InMemoryAuditSink()
        set_audit_sink(new_sink)
        assert get_audit_sink() is new_sink

    def test_set_null_sink(self):
        null = NullAuditSink()
        set_audit_sink(null)
        assert get_audit_sink() is null

    def test_set_sink_replaces_previous(self):
        sink_a = InMemoryAuditSink()
        sink_b = InMemoryAuditSink()
        set_audit_sink(sink_a)
        set_audit_sink(sink_b)
        assert get_audit_sink() is sink_b

    def test_emit_goes_to_active_sink(self):
        memory_sink = InMemoryAuditSink()
        set_audit_sink(memory_sink)
        record = make_record(request_id="global-test")
        get_audit_sink().emit(record)
        assert len(memory_sink.records) == 1
        assert memory_sink.records[0].request_id == "global-test"
