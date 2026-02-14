"""Tests that MCP tool dispatch writes activity events to SQLite.

Verifies that when `dispatch_consolidated_tool` is invoked, the SQLite
ActivityStore receives at least tool_start and tool_end events.  This is
the integration test for the workshop observability pipeline.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture()
def graph():
    """In-memory KnowledgeGraph for activity events."""
    from dazzle.mcp.knowledge_graph import KnowledgeGraph

    return KnowledgeGraph(":memory:")


@pytest.fixture()
def activity_store(graph):
    """ActivityStore backed by the in-memory KG."""
    from dazzle.mcp.server.activity_log import ActivityStore

    session_id = graph.start_activity_session(
        project_name="test_project",
        project_path="/tmp/test",
        version="0.1.0",
    )
    return ActivityStore(graph, session_id)


# ── dispatch_consolidated_tool writes to SQLite ─────────────────────────────


class TestDispatchWritesToSqlite:
    """End-to-end: dispatch -> handler -> SQLite events."""

    @pytest.mark.asyncio
    async def test_tool_start_and_end_in_sqlite(self, activity_store):
        """A successful tool call produces tool_start + tool_end in SQLite."""
        from dazzle.mcp.server.handlers_consolidated import dispatch_consolidated_tool

        with (
            patch("dazzle.mcp.server.state.get_activity_store", return_value=activity_store),
        ):
            result = await dispatch_consolidated_tool(
                "status",
                {"operation": "mcp"},
                session=None,
                progress_token=None,
            )

        assert result is not None

        events = activity_store.read_since(since_id=0)
        event_types = [e["event_type"] for e in events]

        assert "tool_start" in event_types, "tool_start event missing from SQLite"
        assert "tool_end" in event_types, "tool_end event missing from SQLite"

        # Verify tool_end has success and duration
        end_events = [e for e in events if e["event_type"] == "tool_end"]
        assert len(end_events) == 1
        assert end_events[0]["success"] == 1
        assert end_events[0]["duration_ms"] is not None
        assert end_events[0]["tool"] == "status"
        assert end_events[0]["operation"] == "mcp"

    @pytest.mark.asyncio
    async def test_progress_events_reach_sqlite(self, activity_store):
        """Handler progress.log_sync() calls produce log events in SQLite."""
        from dazzle.mcp.server.handlers_consolidated import dispatch_consolidated_tool

        with (
            patch("dazzle.mcp.server.state.get_activity_store", return_value=activity_store),
        ):
            # status.mcp handler calls progress.log_sync("Loading MCP status...")
            await dispatch_consolidated_tool(
                "status",
                {"operation": "mcp"},
            )

        events = activity_store.read_since(since_id=0)
        log_events = [e for e in events if e["event_type"] == "log"]

        assert len(log_events) >= 1, "Expected at least one progress log event in SQLite"

    @pytest.mark.asyncio
    async def test_failed_handler_records_error(self, activity_store):
        """A handler that raises should produce a tool_end with success=0."""
        from dazzle.mcp.server.handlers_consolidated import (
            CONSOLIDATED_TOOL_HANDLERS,
            dispatch_consolidated_tool,
        )

        # Inject a handler that always raises
        def _boom(arguments):
            raise RuntimeError("test explosion")

        CONSOLIDATED_TOOL_HANDLERS["_test_boom"] = _boom
        try:
            with (
                patch("dazzle.mcp.server.state.get_activity_store", return_value=activity_store),
            ):
                with pytest.raises(RuntimeError, match="test explosion"):
                    await dispatch_consolidated_tool("_test_boom", {})
        finally:
            del CONSOLIDATED_TOOL_HANDLERS["_test_boom"]

        events = activity_store.read_since(since_id=0)
        end_events = [e for e in events if e["event_type"] == "tool_end"]
        assert len(end_events) == 1
        assert end_events[0]["success"] == 0
        assert "test explosion" in (end_events[0].get("error") or "")


# ── Lazy init of activity store ─────────────────────────────────────────────


class TestLazyActivityStoreInit:
    """When activity_store is None at dispatch time, lazy init should recover."""

    @pytest.mark.asyncio
    async def test_lazy_init_creates_store(self, tmp_path):
        """If get_activity_store() returns None, dispatch lazily initializes it."""
        from dazzle.mcp.server.handlers_consolidated import dispatch_consolidated_tool

        project_root = tmp_path / "test_project"
        project_root.mkdir()

        with (
            patch("dazzle.mcp.server.state.get_activity_store", return_value=None),
            patch("dazzle.mcp.server.state.get_project_root", return_value=project_root),
            patch("dazzle.mcp.server.state.init_activity_store") as mock_init,
        ):
            await dispatch_consolidated_tool(
                "status",
                {"operation": "mcp"},
            )

        # init_activity_store should have been called as fallback
        assert mock_init.called, "Lazy init_activity_store was not called when store was None"
        mock_init.assert_called_once_with(project_root)


# ── ProgressContext writes to SQLite ────────────────────────────────────────


class TestProgressContextSqlite:
    """ProgressContext should write to the SQLite activity store."""

    def test_log_sync_writes_to_sqlite(self, activity_store):
        """log_sync() writes to SQLite."""
        from dazzle.mcp.server.progress import ProgressContext

        ctx = ProgressContext(
            session=None,
            activity_store=activity_store,
            tool_name="dsl_test",
            operation="run_all",
        )
        ctx.log_sync("Running all tests...")

        # Check SQLite
        sqlite_events = activity_store.read_since(since_id=0)
        assert len(sqlite_events) == 1
        assert sqlite_events[0]["message"] == "Running all tests..."
        assert sqlite_events[0]["tool"] == "dsl_test"
        assert sqlite_events[0]["operation"] == "run_all"

    def test_advance_sync_writes_to_sqlite(self, activity_store):
        """advance_sync() writes progress to SQLite."""
        from dazzle.mcp.server.progress import ProgressContext

        ctx = ProgressContext(
            session=None,
            activity_store=activity_store,
            tool_name="dsl_test",
            operation="run_all",
        )
        ctx.advance_sync(5, 20, "Test 5 of 20")

        # Check SQLite
        sqlite_events = activity_store.read_since(since_id=0)
        assert len(sqlite_events) == 1
        assert sqlite_events[0]["progress_current"] == 5
        assert sqlite_events[0]["progress_total"] == 20

    def test_noop_context_writes_nothing(self, activity_store):
        """noop() context should not write to any backend."""
        from dazzle.mcp.server.progress import noop

        ctx = noop()
        ctx.log_sync("This should go nowhere")

        # Backend should have no entries
        assert len(activity_store.read_since(since_id=0)) == 0


# ── Init ordering ───────────────────────────────────────────────────────────


class TestInitOrdering:
    """Verify that init_activity_log creates the SQLite store when KG is available."""

    def test_activity_store_initialized_when_kg_ready(self, graph, tmp_path):
        """init_activity_log should create ActivityStore when KG is already initialized."""
        from dazzle.mcp.server import state

        project_root = tmp_path / "test_project"
        dazzle_dir = project_root / ".dazzle"
        dazzle_dir.mkdir(parents=True)

        # Simulate: KG is already initialized
        old_kg = state._knowledge_graph
        old_log = state._activity_log
        old_store = state._activity_store
        try:
            state._knowledge_graph = graph
            state._activity_store = None  # Not yet initialized

            state.init_activity_log(project_root)

            # After init, both log and store should be set
            assert state._activity_log is not None
            assert state._activity_store is not None

            # Verify store actually works
            state._activity_store.log_event("test", "tool", "op", message="hello")
            events = state._activity_store.read_since(since_id=0)
            assert len(events) == 1
        finally:
            state._knowledge_graph = old_kg
            state._activity_log = old_log
            state._activity_store = old_store

    def test_activity_store_none_when_kg_not_ready(self, tmp_path):
        """init_activity_log should leave store as None when KG is not available."""
        from dazzle.mcp.server import state

        project_root = tmp_path / "test_project"
        dazzle_dir = project_root / ".dazzle"
        dazzle_dir.mkdir(parents=True)

        old_kg = state._knowledge_graph
        old_log = state._activity_log
        old_store = state._activity_store
        try:
            state._knowledge_graph = None  # KG not initialized
            state._activity_store = None

            state.init_activity_log(project_root)

            # Log should exist, but store should remain None
            assert state._activity_log is not None
            assert state._activity_store is None
        finally:
            state._knowledge_graph = old_kg
            state._activity_log = old_log
            state._activity_store = old_store
