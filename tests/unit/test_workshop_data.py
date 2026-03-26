"""Tests for workshop data layer and widgets."""

import sqlite3


class TestDbRowToEntry:
    """Test _db_row_to_entry conversion."""

    def test_minimal_row(self):
        from dazzle.mcp.server.workshop import _db_row_to_entry

        row = {"event_type": "tool_start", "tool": "dsl", "ts": "2026-03-12T10:00:00"}
        entry = _db_row_to_entry(row)
        assert entry == {"type": "tool_start", "tool": "dsl", "ts": "2026-03-12T10:00:00"}

    def test_full_row(self):
        from dazzle.mcp.server.workshop import _db_row_to_entry

        row = {
            "event_type": "progress",
            "tool": "pipeline",
            "ts": "2026-03-12T10:00:00",
            "operation": "run",
            "success": 1,
            "duration_ms": 1234.5,
            "error": None,
            "warnings": 2,
            "progress_current": 3,
            "progress_total": 8,
            "message": "Running step 3",
            "level": "info",
            "source": "mcp",
            "context_json": '{"steps": 8}',
        }
        entry = _db_row_to_entry(row)
        assert entry["type"] == "progress"
        assert entry["current"] == 3
        assert entry["total"] == 8
        assert entry["warnings"] == 2
        assert entry["context_json"] == '{"steps": 8}'


class TestDetectDbPath:
    """Test _detect_db_path with real SQLite."""

    def test_returns_none_when_no_file(self, tmp_path):
        from dazzle.mcp.server.workshop import _detect_db_path

        # _detect_db_path uses project_kg_db() which resolves .dazzle/kg.db
        # We test via a path that doesn't exist
        assert _detect_db_path(tmp_path / "nonexistent") is None

    def test_returns_none_when_no_table(self, tmp_path):
        from dazzle.mcp.server.workshop import _detect_db_path

        # Create a .dazzle/knowledge_graph.db without the activity_events table
        dazzle_dir = tmp_path / ".dazzle"
        dazzle_dir.mkdir()
        db_path = dazzle_dir / "knowledge_graph.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE other_table (id INTEGER)")
        conn.close()
        assert _detect_db_path(tmp_path) is None
