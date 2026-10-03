"""Tests for the SQLite-backed ActivityStore and KG activity methods."""

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


# ── Cursor protocol (#1754) ─────────────────────────────────────────────────
#
# The MCP handler used to fabricate `cursor.epoch: 0`, `stale: false` and
# `active_tool: null` — so an agent polling its own activity was told its
# cursor was live in exactly the case it was not. These tests pin the real
# values.


class TestCursorProtocol:
    def test_epoch_is_this_sessions_ordinal(self, graph, activity_store):
        """1 for the first session in the database, 2 for the next — stable for
        the life of the session, which is what a held cursor compares against."""
        assert activity_store.current_epoch() == 1
        graph.start_activity_session(project_name="second")
        assert activity_store.current_epoch() == 1, "a later session does not change mine"

        from dazzle.mcp.server.activity_log import ActivityStore

        restarted = ActivityStore(graph, graph.get_activity_sessions()[0]["id"])
        assert restarted.current_epoch() == 2

    def test_initial_read_is_never_stale(self, activity_store):
        """The schema documents cursor_epoch=0 as "initial"; a first read has no
        cursor to have gone stale."""
        activity_store.log_event("tool_start", "dsl", "validate")

        assert activity_store.read_page()["stale"] is False

    def test_page_returns_cursor_epoch_and_no_staleness(self, activity_store):
        activity_store.log_event("tool_start", "dsl", "validate")
        activity_store.log_event("tool_end", "dsl", "validate", success=True)

        page = activity_store.read_page()

        assert page["stale"] is False
        assert page["cursor"]["epoch"] == 1
        assert page["cursor"]["seq"] == page["entries"][-1]["id"]

    def test_a_cursor_from_a_previous_session_reads_as_stale_and_restarts(
        self, graph, activity_store
    ):
        """The case the epoch exists for: a restart gives the caller a new
        session and new event ids, so its held sequence id no longer refers to
        this history. Before, `stale` was hardcoded false and the agent was told
        its cursor was live (#1754)."""
        from dazzle.mcp.server.activity_log import ActivityStore

        for i in range(5):
            activity_store.log_event("tool_start", "dsl", f"op{i}")
        stale_cursor = activity_store.read_page(limit=2)["cursor"]

        new_session = graph.start_activity_session(project_name="restarted")
        restarted = ActivityStore(graph, new_session)
        restarted.log_event("tool_start", "story", "propose")

        page = restarted.read_page(since_id=stale_cursor["seq"], cursor_epoch=stale_cursor["epoch"])

        assert page["stale"] is True
        assert page["cursor"]["epoch"] == 2
        # Restarted from zero rather than honouring a cursor from a session whose
        # events this store cannot see.
        assert [e["tool"] for e in page["entries"]] == ["story"]

    def test_recreated_database_invalidates_a_held_cursor(self, graph):
        """The other way a cursor dies: the KG db is re-created, so event ids
        restart at 1 while the caller's cursor points into the old numbering."""
        from dazzle.mcp.server.activity_log import ActivityStore

        old = ActivityStore(graph, graph.start_activity_session(project_name="original"))
        for i in range(3):
            old.log_event("tool_start", "dsl", f"op{i}")
        held = old.read_page()["cursor"]
        assert held["seq"] == 3

        fresh_graph = type(graph)(":memory:")
        fresh = ActivityStore(
            fresh_graph, fresh_graph.start_activity_session(project_name="rebuilt")
        )
        fresh.log_event("tool_start", "story", "propose")

        page = fresh.read_page(since_id=held["seq"], cursor_epoch=held["epoch"])

        assert page["stale"] is True
        assert len(page["entries"]) == 1

    def test_honoured_cursor_does_not_restart(self, activity_store):
        for i in range(3):
            activity_store.log_event("tool_start", "dsl", f"op{i}")
        cursor = activity_store.read_page(limit=2)["cursor"]

        page = activity_store.read_page(since_id=cursor["seq"], cursor_epoch=cursor["epoch"])

        assert page["stale"] is False
        assert [e["tool"] for e in page["entries"]] == ["dsl"]

    def test_has_more_is_a_fact_not_a_full_page(self, activity_store):
        for i in range(3):
            activity_store.log_event("tool_start", "dsl", f"op{i}")

        exact = activity_store.read_page(limit=3)
        assert len(exact["entries"]) == 3
        assert exact["has_more"] is False  # 3 events, asked for 3 → no more

        short = activity_store.read_page(limit=2)
        assert short["has_more"] is True

    def test_active_tool_reports_an_unclosed_call(self, activity_store):
        activity_store.log_event("tool_start", "dsl", "validate")
        activity_store.log_event("tool_end", "dsl", "validate", success=True)

        assert activity_store.active_tool() is None
        activity_store.log_event("tool_start", "composition", "audit")
        active = activity_store.active_tool()
        assert active["tool"] == "composition"
        assert active["operation"] == "audit"
        assert active["elapsed_ms"] is not None
