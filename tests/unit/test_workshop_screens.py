"""Tests for workshop screen data and navigation logic."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dazzle.mcp.server.workshop import ToolCall, WorkshopData, _format_duration, _format_ts


class TestToolCall:
    def test_label_with_operation(self):
        call = ToolCall(
            call_id="dsl.validate.t1",
            tool="dsl",
            operation="validate",
            start_ts="2026-03-12T10:00:00",
            start_mono=0.0,
        )
        assert call.label == "dsl.validate"

    def test_label_without_operation(self):
        call = ToolCall(
            call_id="dsl.None.t1",
            tool="dsl",
            operation=None,
            start_ts="2026-03-12T10:00:00",
            start_mono=0.0,
        )
        assert call.label == "dsl"

    def test_purpose_from_first_log_event(self):
        call = ToolCall(
            call_id="test.t1",
            tool="test",
            operation="run",
            start_ts="t1",
            start_mono=0.0,
            events=[
                {"type": "log", "message": "Running quality pipeline"},
                {"type": "progress", "message": "Step 2"},
            ],
        )
        assert call.purpose == "Running quality pipeline"

    def test_purpose_fallback_to_label(self):
        call = ToolCall(
            call_id="test.t1",
            tool="test",
            operation="run",
            start_ts="t1",
            start_mono=0.0,
        )
        assert call.purpose == "test.run"

    def test_summary_from_context_json(self):
        call = ToolCall(
            call_id="test.t1",
            tool="test",
            operation="run",
            start_ts="t1",
            start_mono=0.0,
            context_json='{"summary": "8/8 steps passed"}',
        )
        assert call.summary == "8/8 steps passed"

    def test_summary_from_context_json_keys(self):
        call = ToolCall(
            call_id="test.t1",
            tool="test",
            operation="run",
            start_ts="t1",
            start_mono=0.0,
            context_json='{"passed": 5, "failed": 1}',
        )
        assert "passed=5" in call.summary
        assert "failed=1" in call.summary


class TestWorkshopData:
    def test_ingest_tool_start(self):
        data = WorkshopData()
        call = data.ingest(
            {"type": "tool_start", "tool": "dsl", "operation": "validate", "ts": "t1"}
        )
        assert call is not None
        assert len(data.active) == 1
        assert data.total_calls == 1

    def test_ingest_tool_end(self):
        data = WorkshopData()
        data.ingest({"type": "tool_start", "tool": "dsl", "operation": "validate", "ts": "t1"})
        call = data.ingest(
            {
                "type": "tool_end",
                "tool": "dsl",
                "operation": "validate",
                "ts": "t2",
                "success": True,
                "duration_ms": 500,
            }
        )
        assert call is not None
        assert call.finished
        assert len(data.active) == 0
        assert len(data.completed) == 1

    def test_ingest_progress_updates_call(self):
        data = WorkshopData()
        data.ingest(
            {
                "type": "tool_start",
                "tool": "pipeline",
                "operation": "run",
                "ts": "t1",
            }
        )
        call = data.ingest(
            {
                "type": "progress",
                "tool": "pipeline",
                "operation": "run",
                "current": 3,
                "total": 8,
                "message": "Step 3",
            }
        )
        assert call is not None
        assert call.progress_current == 3
        assert call.progress_total == 8

    def test_calls_grouped_by_tool(self):
        data = WorkshopData()
        data.ingest({"type": "tool_start", "tool": "dsl", "operation": "validate", "ts": "t1"})
        data.ingest(
            {
                "type": "tool_end",
                "tool": "dsl",
                "operation": "validate",
                "ts": "t2",
                "success": True,
            }
        )
        data.ingest(
            {
                "type": "tool_start",
                "tool": "story",
                "operation": "coverage",
                "ts": "t3",
            }
        )
        data.ingest(
            {
                "type": "tool_end",
                "tool": "story",
                "operation": "coverage",
                "ts": "t4",
                "success": True,
            }
        )
        data.ingest({"type": "tool_start", "tool": "dsl", "operation": "lint", "ts": "t5"})
        data.ingest(
            {
                "type": "tool_end",
                "tool": "dsl",
                "operation": "lint",
                "ts": "t6",
                "success": True,
            }
        )

        groups = data.calls_grouped_by_tool()
        assert len(groups["dsl"]) == 2
        assert len(groups["story"]) == 1

    def test_error_count_tracked(self):
        data = WorkshopData()
        data.ingest({"type": "tool_start", "tool": "dsl", "operation": "validate", "ts": "t1"})
        data.ingest(
            {
                "type": "tool_end",
                "tool": "dsl",
                "operation": "validate",
                "ts": "t2",
                "success": False,
                "error": "parse error",
            }
        )
        assert data.error_count == 1


class TestFormatHelpers:
    def test_format_ts_iso(self):
        assert _format_ts("2026-03-12T10:30:45.123") == "10:30:45"

    def test_format_ts_empty(self):
        assert _format_ts("") == "??:??:??"

    def test_format_duration_subsecond(self):
        assert _format_duration(0.05) == "<0.1s"

    def test_format_duration_seconds(self):
        assert _format_duration(12.3) == "12.3s"

    def test_format_duration_minutes(self):
        assert _format_duration(125.0) == "2m5s"


# ── Integration: SQLite → read_new_entries_db → WorkshopData.ingest ──────────


@pytest.fixture()
def activity_db(tmp_path: Path) -> Path:
    """Create a temporary SQLite DB with the activity_events schema and a
    tool_start → progress → tool_end sequence."""
    db_path = tmp_path / "activity.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE activity_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            event_type TEXT NOT NULL,
            tool TEXT NOT NULL,
            operation TEXT,
            ts TEXT,
            success INTEGER,
            duration_ms REAL,
            error TEXT,
            warnings INTEGER DEFAULT 0,
            progress_current INTEGER,
            progress_total INTEGER,
            message TEXT,
            level TEXT,
            source TEXT,
            context_json TEXT
        )
        """
    )
    conn.execute(
        """INSERT INTO activity_events
           (session_id, event_type, tool, operation, ts, source)
           VALUES ('s1', 'tool_start', 'pipeline', 'run',
                   '2026-03-12T10:00:00.000+00:00', 'mcp')"""
    )
    conn.execute(
        """INSERT INTO activity_events
           (session_id, event_type, tool, operation, ts, progress_current,
            progress_total, message, source)
           VALUES ('s1', 'progress', 'pipeline', 'run',
                   '2026-03-12T10:00:01.000+00:00', 3, 8, 'Step 3 of 8', 'mcp')"""
    )
    conn.execute(
        """INSERT INTO activity_events
           (session_id, event_type, tool, operation, ts, success, duration_ms,
            context_json, source)
           VALUES ('s1', 'tool_end', 'pipeline', 'run',
                   '2026-03-12T10:00:02.500+00:00', 1, 2500,
                   '{"summary": "8/8 steps passed"}', 'mcp')"""
    )
    conn.commit()
    conn.close()
    return db_path


class TestSqliteIntegration:
    """Integration: SQLite polling → WorkshopData.ingest → state verification."""

    def test_full_lifecycle(self, activity_db: Path) -> None:
        from dazzle.mcp.server.workshop import WorkshopData, read_new_entries_db

        data = WorkshopData()

        # Poll entries from the database
        entries = read_new_entries_db(activity_db, data)
        assert len(entries) == 3

        # Ingest each entry
        for entry in entries:
            data.ingest(entry)

        # Verify final state
        assert data.total_calls == 1  # one tool_start
        assert len(data.active) == 0  # finished
        assert len(data.completed) == 1
        assert data.error_count == 0

        call = data.completed[0]
        assert call.tool == "pipeline"
        assert call.operation == "run"
        assert call.finished
        assert call.success is True
        assert call.duration_ms == 2500
        assert call.summary == "8/8 steps passed"
        # Progress was recorded in events
        assert len(call.events) == 2  # progress + tool_end
        assert call.events[0]["message"] == "Step 3 of 8"

    def test_cursor_based_polling(self, activity_db: Path) -> None:
        from dazzle.mcp.server.workshop import WorkshopData, read_new_entries_db

        data = WorkshopData()

        entries = read_new_entries_db(activity_db, data)
        assert len(entries) == 3
        assert data._last_event_id > 0

        # Second poll returns nothing
        more = read_new_entries_db(activity_db, data)
        assert len(more) == 0

    def test_persistent_connection(self, activity_db: Path) -> None:
        """read_new_entries_db can reuse a persistent connection."""
        from dazzle.mcp.server.workshop import WorkshopData, read_new_entries_db

        data = WorkshopData()
        conn = sqlite3.connect(str(activity_db), check_same_thread=False)
        conn.row_factory = sqlite3.Row

        entries = read_new_entries_db(activity_db, data, conn=conn)
        assert len(entries) == 3

        # Connection still usable
        more = read_new_entries_db(activity_db, data, conn=conn)
        assert len(more) == 0

        conn.close()
