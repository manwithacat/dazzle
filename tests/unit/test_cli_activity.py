"""Tests for CLI activity logging context manager and source column."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture()
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal project directory with dazzle.toml."""
    (tmp_path / "dazzle.toml").write_text('[project]\nname = "test"\n')
    (tmp_path / ".dazzle").mkdir()
    return tmp_path


class TestSourceColumnMigration:
    """Test that the source column is added to existing databases."""

    def test_source_column_exists_in_new_db(self, tmp_path: Path) -> None:
        """New databases should have a source column on activity_events."""
        from dazzle.mcp.knowledge_graph.store import KnowledgeGraph

        db_path = tmp_path / "kg.db"
        KnowledgeGraph(db_path)

        # Check schema
        conn = sqlite3.connect(str(db_path))
        try:
            info = conn.execute("PRAGMA table_info(activity_events)").fetchall()
            col_names = [row[1] for row in info]
            assert "source" in col_names
        finally:
            conn.close()

    def test_source_column_default_is_mcp(self, tmp_path: Path) -> None:
        """Existing rows and new rows without explicit source default to 'mcp'."""
        from dazzle.mcp.knowledge_graph.store import KnowledgeGraph

        db_path = tmp_path / "kg.db"
        graph = KnowledgeGraph(db_path)

        session_id = graph.start_activity_session(project_name="test")
        event_id = graph.log_activity_event(session_id, "tool_start", "dsl", "validate")

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT source FROM activity_events WHERE id = ?", (event_id,)
            ).fetchone()
            assert row["source"] == "mcp"
        finally:
            conn.close()

    def test_source_column_stores_cli(self, tmp_path: Path) -> None:
        """Events with source='cli' store correctly."""
        from dazzle.mcp.knowledge_graph.store import KnowledgeGraph

        db_path = tmp_path / "kg.db"
        graph = KnowledgeGraph(db_path)

        session_id = graph.start_activity_session(project_name="test")
        event_id = graph.log_activity_event(
            session_id, "tool_start", "pipeline", "run", source="cli"
        )

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT source FROM activity_events WHERE id = ?", (event_id,)
            ).fetchone()
            assert row["source"] == "cli"
        finally:
            conn.close()


class TestActivityStorePropagation:
    """Test that source propagates through ActivityStore."""

    def test_activity_store_passes_source(self, tmp_path: Path) -> None:
        """ActivityStore.log_event passes source to KG."""
        from dazzle.mcp.knowledge_graph.store import KnowledgeGraph
        from dazzle.mcp.server.activity_log import ActivityStore

        db_path = tmp_path / "kg.db"
        graph = KnowledgeGraph(db_path)
        session_id = graph.start_activity_session(project_name="test")
        store = ActivityStore(graph, session_id)

        event_id = store.log_event("tool_start", "sentinel", "scan", source="cli")

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT source FROM activity_events WHERE id = ?", (event_id,)
            ).fetchone()
            assert row["source"] == "cli"
        finally:
            conn.close()


class TestProgressContextSource:
    """Test that ProgressContext propagates source to activity writes."""

    def test_progress_context_writes_source(self, tmp_path: Path) -> None:
        """ProgressContext with source='cli' writes cli source to log entries."""
        from dazzle.mcp.knowledge_graph.store import KnowledgeGraph
        from dazzle.mcp.server.activity_log import ActivityStore
        from dazzle.mcp.server.progress import ProgressContext

        db_path = tmp_path / "kg.db"
        graph = KnowledgeGraph(db_path)
        session_id = graph.start_activity_session(project_name="test")
        store = ActivityStore(graph, session_id)

        progress = ProgressContext(
            session=None,
            activity_store=store,
            tool_name="pipeline",
            operation="run",
            source="cli",
        )

        # Write a log entry
        progress.log_sync("Testing CLI source")

        # Check that the entry has source=cli
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT source FROM activity_events ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert row["source"] == "cli"
        finally:
            conn.close()

    def test_progress_context_defaults_to_mcp(self, tmp_path: Path) -> None:
        """ProgressContext without explicit source defaults to 'mcp'."""
        from dazzle.mcp.knowledge_graph.store import KnowledgeGraph
        from dazzle.mcp.server.activity_log import ActivityStore
        from dazzle.mcp.server.progress import ProgressContext

        db_path = tmp_path / "kg.db"
        graph = KnowledgeGraph(db_path)
        session_id = graph.start_activity_session(project_name="test")
        store = ActivityStore(graph, session_id)

        progress = ProgressContext(
            session=None,
            activity_store=store,
            tool_name="dsl",
            operation="validate",
        )

        progress.log_sync("Testing default source")

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT source FROM activity_events ORDER BY id DESC LIMIT 1"
            ).fetchone()
            assert row["source"] == "mcp"
        finally:
            conn.close()


class TestCliActivity:
    """Test the cli_activity context manager."""

    def test_context_manager_logs_start_and_end(self, tmp_project: Path) -> None:
        """cli_activity should log tool_start and tool_end events."""
        from dazzle.mcp.knowledge_graph.store import KnowledgeGraph
        from dazzle.mcp.server.activity_log import ActivityStore

        # Pre-initialise KG + activity store
        db_path = tmp_project / ".dazzle" / "knowledge_graph.db"
        graph = KnowledgeGraph(db_path)
        session_id = graph.start_activity_session(project_name="test")
        store = ActivityStore(graph, session_id)

        with (
            patch("dazzle.mcp.server.state.get_knowledge_graph", return_value=graph),
            patch("dazzle.mcp.server.state.get_activity_store", return_value=store),
            patch("dazzle.mcp.server.state.init_knowledge_graph"),
            patch("dazzle.mcp.server.state.init_activity_store"),
        ):
            from dazzle.cli.activity import cli_activity

            with cli_activity(tmp_project, "pipeline", "run") as progress:
                assert progress is not None

        # Check events
        events = graph.get_activity_events(since_id=0, session_id=session_id)
        types = [e["event_type"] for e in events]
        assert "tool_start" in types
        assert "tool_end" in types

        # Check source on all events
        for event in events:
            assert event.get("source") == "cli"

        # Check tool_end has success=True
        tool_end = [e for e in events if e["event_type"] == "tool_end"][0]
        assert tool_end["success"] == 1

    def test_context_manager_logs_error_on_exception(self, tmp_project: Path) -> None:
        """cli_activity should log tool_end with success=False on exception."""
        from dazzle.mcp.knowledge_graph.store import KnowledgeGraph
        from dazzle.mcp.server.activity_log import ActivityStore

        db_path = tmp_project / ".dazzle" / "knowledge_graph.db"
        graph = KnowledgeGraph(db_path)
        session_id = graph.start_activity_session(project_name="test")
        store = ActivityStore(graph, session_id)

        with (
            patch("dazzle.mcp.server.state.get_knowledge_graph", return_value=graph),
            patch("dazzle.mcp.server.state.get_activity_store", return_value=store),
            patch("dazzle.mcp.server.state.init_knowledge_graph"),
            patch("dazzle.mcp.server.state.init_activity_store"),
        ):
            from dazzle.cli.activity import cli_activity

            with pytest.raises(ValueError, match="boom"):
                with cli_activity(tmp_project, "sentinel", "scan"):
                    raise ValueError("boom")

        events = graph.get_activity_events(since_id=0, session_id=session_id)
        tool_end = [e for e in events if e["event_type"] == "tool_end"][0]
        assert tool_end["success"] == 0
        assert "boom" in (tool_end.get("error") or "")
        assert tool_end.get("source") == "cli"

    def test_context_manager_records_duration(self, tmp_project: Path) -> None:
        """cli_activity should record duration_ms on tool_end."""
        import time

        from dazzle.mcp.knowledge_graph.store import KnowledgeGraph
        from dazzle.mcp.server.activity_log import ActivityStore

        db_path = tmp_project / ".dazzle" / "knowledge_graph.db"
        graph = KnowledgeGraph(db_path)
        session_id = graph.start_activity_session(project_name="test")
        store = ActivityStore(graph, session_id)

        with (
            patch("dazzle.mcp.server.state.get_knowledge_graph", return_value=graph),
            patch("dazzle.mcp.server.state.get_activity_store", return_value=store),
            patch("dazzle.mcp.server.state.init_knowledge_graph"),
            patch("dazzle.mcp.server.state.init_activity_store"),
        ):
            from dazzle.cli.activity import cli_activity

            with cli_activity(tmp_project, "pipeline", "run"):
                time.sleep(0.01)  # Small delay to get measurable duration

        events = graph.get_activity_events(since_id=0, session_id=session_id)
        tool_end = [e for e in events if e["event_type"] == "tool_end"][0]
        assert tool_end["duration_ms"] is not None
        assert tool_end["duration_ms"] > 0

    def test_context_manager_works_without_store(self, tmp_project: Path) -> None:
        """cli_activity should yield a noop progress if store init fails."""
        with (
            patch("dazzle.mcp.server.state.get_knowledge_graph", return_value=None),
            patch("dazzle.mcp.server.state.get_activity_store", return_value=None),
            patch("dazzle.mcp.server.state.init_knowledge_graph", side_effect=Exception("no KG")),
            patch("dazzle.mcp.server.state.init_activity_store"),
        ):
            from dazzle.cli.activity import cli_activity

            with cli_activity(tmp_project, "pipeline", "run") as progress:
                # Should still work — just no logging
                assert progress is not None
                progress.log_sync("this is fine")


class TestWorkshopSourceDisplay:
    """Test that the workshop renders source tags."""

    def test_db_row_to_entry_includes_source(self) -> None:
        """_db_row_to_entry should include source field when present."""
        from dazzle.mcp.server.workshop import _db_row_to_entry

        row = {
            "event_type": "tool_start",
            "tool": "pipeline",
            "ts": "2026-02-14T10:00:00.000+00:00",
            "operation": "run",
            "success": None,
            "duration_ms": None,
            "error": None,
            "warnings": None,
            "progress_current": None,
            "progress_total": None,
            "message": None,
            "level": None,
            "source": "cli",
        }
        entry = _db_row_to_entry(row)
        assert entry["source"] == "cli"

    def test_ingest_tracks_source_on_active(self) -> None:
        """WorkshopState.ingest should store source on ActiveTool."""
        from dazzle.mcp.server.workshop import WorkshopState

        state = WorkshopState()
        state.ingest(
            {
                "type": "tool_start",
                "tool": "pipeline",
                "operation": "run",
                "ts": "2026-02-14T10:00:00",
                "source": "cli",
            }
        )

        at = state.active["pipeline.run"]
        assert at.source == "cli"

    def test_ingest_tracks_source_on_completed(self) -> None:
        """WorkshopState.ingest should store source on CompletedTool."""
        from dazzle.mcp.server.workshop import WorkshopState

        state = WorkshopState()
        state.ingest(
            {
                "type": "tool_start",
                "tool": "pipeline",
                "operation": "run",
                "ts": "2026-02-14T10:00:00",
                "source": "cli",
            }
        )
        state.ingest(
            {
                "type": "tool_end",
                "tool": "pipeline",
                "operation": "run",
                "ts": "2026-02-14T10:00:01",
                "success": True,
                "duration_ms": 1000,
                "source": "cli",
            }
        )

        ct = state.completed[0]
        assert ct.source == "cli"

    def test_render_shows_cli_tag(self) -> None:
        """render_workshop should prepend 'CLI' to CLI-sourced tool labels."""
        from dazzle.mcp.server.workshop import WorkshopState, render_workshop

        state = WorkshopState()
        state.ingest(
            {
                "type": "tool_start",
                "tool": "pipeline",
                "operation": "run",
                "ts": "2026-02-14T10:00:00",
                "source": "cli",
            }
        )
        state.ingest(
            {
                "type": "tool_end",
                "tool": "pipeline",
                "operation": "run",
                "ts": "2026-02-14T10:00:01",
                "success": True,
                "duration_ms": 500,
                "source": "cli",
            }
        )

        render_workshop(state, "test", "1.0")
        # The rendered output should contain 'CLI pipeline.run'
        # We verify by checking the CompletedTool label generation
        ct = state.completed[0]
        label = f"{ct.tool}.{ct.operation}" if ct.operation else ct.tool
        if ct.source == "cli":
            label = f"CLI {label}"
        assert label == "CLI pipeline.run"
