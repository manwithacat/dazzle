"""Tests for the SQLite-backed ActivityStore and KG activity methods."""

from __future__ import annotations

import threading

import pytest


@pytest.fixture()
def graph():
    from dazzle.mcp.knowledge_graph import KnowledgeGraph

    return KnowledgeGraph(":memory:")


@pytest.fixture()
def activity_store(graph):
    from dazzle.mcp.server.activity_log import ActivityStore

    session_id = graph.start_activity_session(
        project_name="test_project",
        project_path="/tmp/test",
        version="0.1.0",
    )
    return ActivityStore(graph, session_id)


# ── Session lifecycle ────────────────────────────────────────────────────────


class TestSessionLifecycle:
    def test_start_session(self, graph):
        sid = graph.start_activity_session(project_name="myapp", project_path="/tmp/myapp")
        assert sid  # Non-empty UUID string
        sessions = graph.get_activity_sessions()
        assert len(sessions) == 1
        assert sessions[0]["project_name"] == "myapp"
        assert sessions[0]["ended_at"] is None

    def test_end_session(self, graph):
        sid = graph.start_activity_session(project_name="myapp")
        graph.end_activity_session(sid)
        sessions = graph.get_activity_sessions()
        assert sessions[0]["ended_at"] is not None

    def test_multiple_sessions(self, graph):
        graph.start_activity_session(project_name="first")
        graph.start_activity_session(project_name="second")
        sessions = graph.get_activity_sessions()
        assert len(sessions) == 2
        # Newest first
        assert sessions[0]["project_name"] == "second"


# ── Event logging and retrieval ──────────────────────────────────────────────


class TestEventLogging:
    def test_log_event_returns_id(self, activity_store):
        eid = activity_store.log_event("tool_start", "dsl", "validate")
        assert isinstance(eid, int)
        assert eid > 0

    def test_log_and_read_events(self, activity_store):
        activity_store.log_event("tool_start", "dsl", "validate")
        activity_store.log_event("tool_end", "dsl", "validate", success=True, duration_ms=42.5)

        events = activity_store.read_since(since_id=0)
        assert len(events) == 2
        assert events[0]["event_type"] == "tool_start"
        assert events[0]["tool"] == "dsl"
        assert events[0]["operation"] == "validate"
        assert events[1]["event_type"] == "tool_end"
        assert events[1]["success"] == 1
        assert events[1]["duration_ms"] == 42.5

    def test_cursor_based_polling(self, activity_store):
        activity_store.log_event("tool_start", "dsl", "validate")
        activity_store.log_event("tool_end", "dsl", "validate", success=True)
        activity_store.log_event("tool_start", "story", "propose")

        # Read first two
        events = activity_store.read_since(since_id=0, limit=2)
        assert len(events) == 2
        cursor = events[-1]["id"]

        # Read from cursor
        more = activity_store.read_since(since_id=cursor)
        assert len(more) == 1
        assert more[0]["event_type"] == "tool_start"
        assert more[0]["tool"] == "story"

    def test_log_event_with_progress(self, activity_store):
        activity_store.log_event(
            "progress",
            "pipeline",
            "run",
            progress_current=3,
            progress_total=10,
            message="Running step 3",
        )
        events = activity_store.read_since()
        assert len(events) == 1
        assert events[0]["progress_current"] == 3
        assert events[0]["progress_total"] == 10
        assert events[0]["message"] == "Running step 3"

    def test_log_event_with_error(self, activity_store):
        activity_store.log_event(
            "tool_end",
            "dsl",
            "validate",
            success=False,
            error="Parse error at line 5",
            duration_ms=10.0,
        )
        events = activity_store.read_since()
        assert events[0]["success"] == 0
        assert events[0]["error"] == "Parse error at line 5"

    def test_events_ordered_by_id(self, activity_store):
        for i in range(5):
            activity_store.log_event("log", "test", message=f"msg-{i}")
        events = activity_store.read_since()
        ids = [e["id"] for e in events]
        assert ids == sorted(ids)

    def test_session_isolation(self, graph):
        """Events from different sessions should not overlap."""
        from dazzle.mcp.server.activity_log import ActivityStore

        sid1 = graph.start_activity_session(project_name="proj1")
        sid2 = graph.start_activity_session(project_name="proj2")
        store1 = ActivityStore(graph, sid1)
        store2 = ActivityStore(graph, sid2)

        store1.log_event("tool_start", "dsl", "validate")
        store2.log_event("tool_start", "story", "propose")

        events1 = store1.read_since()
        events2 = store2.read_since()
        assert len(events1) == 1
        assert events1[0]["tool"] == "dsl"
        assert len(events2) == 1
        assert events2[0]["tool"] == "story"


# ── Activity stats ───────────────────────────────────────────────────────────


class TestActivityStats:
    def test_stats_empty(self, graph):
        stats = graph.get_activity_stats()
        assert stats["total_events"] == 0
        assert stats["tool_calls_ok"] == 0
        assert stats["tool_calls_error"] == 0
        assert stats["by_tool"] == []

    def test_stats_aggregation(self, activity_store, graph):
        activity_store.log_event("tool_start", "dsl", "validate")
        activity_store.log_event("tool_end", "dsl", "validate", success=True, duration_ms=50.0)
        activity_store.log_event("tool_start", "dsl", "lint")
        activity_store.log_event("tool_end", "dsl", "lint", success=True, duration_ms=30.0)
        activity_store.log_event("tool_start", "story", "propose")
        activity_store.log_event("tool_end", "story", "propose", success=False, error="boom")

        stats = graph.get_activity_stats()
        assert stats["total_events"] == 6
        assert stats["tool_calls_ok"] == 2
        assert stats["tool_calls_error"] == 1
        assert stats["success_rate"] == pytest.approx(66.7, abs=0.1)
        assert len(stats["by_tool"]) == 2  # dsl and story

    def test_stats_filtered_by_session(self, graph):
        from dazzle.mcp.server.activity_log import ActivityStore

        sid1 = graph.start_activity_session(project_name="proj1")
        sid2 = graph.start_activity_session(project_name="proj2")
        s1 = ActivityStore(graph, sid1)
        s2 = ActivityStore(graph, sid2)

        s1.log_event("tool_end", "dsl", success=True, duration_ms=10)
        s2.log_event("tool_end", "story", success=True, duration_ms=20)
        s2.log_event("tool_end", "story", success=False, duration_ms=5)

        stats1 = graph.get_activity_stats(session_id=sid1)
        assert stats1["tool_calls_ok"] == 1
        assert stats1["tool_calls_error"] == 0

        stats2 = graph.get_activity_stats(session_id=sid2)
        assert stats2["tool_calls_ok"] == 1
        assert stats2["tool_calls_error"] == 1


# ── Thread safety ────────────────────────────────────────────────────────────


class TestThreadSafety:
    def test_concurrent_writes(self, tmp_path):
        """Multiple threads writing events should all succeed.

        Uses a file-based DB because in-memory SQLite shares a single
        connection which is not safe for concurrent access from threads.
        """
        from dazzle.mcp.knowledge_graph import KnowledgeGraph
        from dazzle.mcp.server.activity_log import ActivityStore

        db = tmp_path / "thread_test.db"
        g = KnowledgeGraph(db)
        sid = g.start_activity_session(project_name="thread_test")
        store = ActivityStore(g, sid)

        results: list[int] = []
        lock = threading.Lock()

        def writer(n: int) -> None:
            for _ in range(10):
                eid = store.log_event("log", "test", message=f"thread-{n}")
                with lock:
                    results.append(eid)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 40
        assert len(set(results)) == 40  # All unique IDs


# ── End session via store ────────────────────────────────────────────────────


class TestActivityStoreEndSession:
    def test_end_session(self, activity_store, graph):
        activity_store.end_session()
        sessions = graph.get_activity_sessions()
        assert sessions[0]["ended_at"] is not None
