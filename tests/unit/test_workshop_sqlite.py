"""Tests for workshop SQLite integration."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


@pytest.fixture()
def db_path(tmp_path: Path) -> Path:
    """Create a KG database with activity tables populated."""
    from dazzle.mcp.knowledge_graph import KnowledgeGraph

    db = tmp_path / ".dazzle" / "knowledge_graph.db"
    db.parent.mkdir(parents=True)
    graph = KnowledgeGraph(db)

    session_id = graph.start_activity_session(project_name="test")
    graph.log_activity_event(session_id, "tool_start", "dsl", "validate")
    graph.log_activity_event(
        session_id,
        "tool_end",
        "dsl",
        "validate",
        success=True,
        duration_ms=42.0,
    )
    graph.log_activity_event(session_id, "tool_start", "story", "propose")
    graph.log_activity_event(
        session_id,
        "tool_end",
        "story",
        "propose",
        success=False,
        error="Not found",
        duration_ms=10.0,
    )
    return db


# ── read_new_entries_db ──────────────────────────────────────────────────────


class TestReadNewEntriesDb:
    def test_reads_all_events(self, db_path):
        from dazzle.mcp.server.workshop import WorkshopState, read_new_entries_db

        state = WorkshopState()
        entries = read_new_entries_db(db_path, state)
        assert len(entries) == 4
        assert entries[0]["type"] == "tool_start"
        assert entries[0]["tool"] == "dsl"
        assert entries[1]["type"] == "tool_end"
        assert entries[1]["success"] is True
        assert entries[1]["duration_ms"] == 42.0

    def test_cursor_advances(self, db_path):
        from dazzle.mcp.server.workshop import WorkshopState, read_new_entries_db

        state = WorkshopState()
        entries = read_new_entries_db(db_path, state)
        assert len(entries) == 4
        assert state._last_event_id > 0

        # Second read returns nothing (no new events)
        more = read_new_entries_db(db_path, state)
        assert len(more) == 0

    def test_handles_missing_db(self, tmp_path):
        from dazzle.mcp.server.workshop import WorkshopState, read_new_entries_db

        state = WorkshopState()
        entries = read_new_entries_db(tmp_path / "missing.db", state)
        assert entries == []


# ── _db_row_to_entry ─────────────────────────────────────────────────────────


class TestDbRowToEntry:
    def test_converts_tool_start(self):
        from dazzle.mcp.server.workshop import _db_row_to_entry

        row = {
            "event_type": "tool_start",
            "tool": "dsl",
            "operation": "validate",
            "ts": "2026-02-13T10:00:00.000+00:00",
            "success": None,
            "duration_ms": None,
            "error": None,
            "warnings": 0,
            "progress_current": None,
            "progress_total": None,
            "message": None,
            "level": "info",
        }
        entry = _db_row_to_entry(row)
        assert entry["type"] == "tool_start"
        assert entry["tool"] == "dsl"
        assert entry["operation"] == "validate"
        assert "success" not in entry

    def test_converts_tool_end(self):
        from dazzle.mcp.server.workshop import _db_row_to_entry

        row = {
            "event_type": "tool_end",
            "tool": "dsl",
            "operation": "validate",
            "ts": "2026-02-13T10:00:00.050+00:00",
            "success": 1,
            "duration_ms": 50.0,
            "error": None,
            "warnings": 0,
            "progress_current": None,
            "progress_total": None,
            "message": None,
            "level": "info",
        }
        entry = _db_row_to_entry(row)
        assert entry["type"] == "tool_end"
        assert entry["success"] is True
        assert entry["duration_ms"] == 50.0

    def test_converts_progress(self):
        from dazzle.mcp.server.workshop import _db_row_to_entry

        row = {
            "event_type": "progress",
            "tool": "pipeline",
            "operation": "run",
            "ts": "2026-02-13T10:00:01.000+00:00",
            "success": None,
            "duration_ms": None,
            "error": None,
            "warnings": 0,
            "progress_current": 3,
            "progress_total": 10,
            "message": "Step 3",
            "level": "info",
        }
        entry = _db_row_to_entry(row)
        assert entry["type"] == "progress"
        assert entry["current"] == 3
        assert entry["total"] == 10
        assert entry["message"] == "Step 3"


# ── _detect_db_path ──────────────────────────────────────────────────────────


class TestDetectDbPath:
    def test_detects_valid_db(self, db_path, tmp_path):
        from dazzle.mcp.server.workshop import _detect_db_path

        result = _detect_db_path(tmp_path)
        assert result == db_path

    def test_returns_none_for_missing(self, tmp_path):
        from dazzle.mcp.server.workshop import _detect_db_path

        result = _detect_db_path(tmp_path)
        assert result is None

    def test_returns_none_for_db_without_table(self, tmp_path):
        from dazzle.mcp.server.workshop import _detect_db_path

        db = tmp_path / ".dazzle" / "knowledge_graph.db"
        db.parent.mkdir(parents=True)
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE entities (id TEXT)")
        conn.close()

        result = _detect_db_path(tmp_path)
        assert result is None


# ── Ingest integration ───────────────────────────────────────────────────────


class TestIngestFromSqlite:
    def test_ingest_sqlite_events(self, db_path):
        from dazzle.mcp.server.workshop import WorkshopState, read_new_entries_db

        state = WorkshopState()
        entries = read_new_entries_db(db_path, state)
        for entry in entries:
            state.ingest(entry)

        assert state.total_calls == 2  # Two tool_start events
        assert state.error_count == 1  # One failed tool_end
        assert len(state.completed) == 2  # Two tool_end events
