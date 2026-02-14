"""Tests for the MCP activity log module."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest


@pytest.fixture()
def log_path(tmp_path: Path) -> Path:
    return tmp_path / ".dazzle" / "mcp-activity.log"


@pytest.fixture()
def activity_log(log_path: Path):
    from dazzle.mcp.server.activity_log import ActivityLog

    return ActivityLog(log_path)


# ── Basic append / read ─────────────────────────────────────────────────────


class TestAppendAndRead:
    def test_append_creates_file(self, activity_log, log_path):
        activity_log.append({"type": "log", "message": "hello"})
        assert log_path.exists()

    def test_append_returns_seq(self, activity_log):
        s1 = activity_log.append({"type": "log", "message": "one"})
        s2 = activity_log.append({"type": "log", "message": "two"})
        assert s1 == 1
        assert s2 == 2

    def test_append_adds_seq_and_epoch(self, activity_log, log_path):
        activity_log.append({"type": "log", "message": "test"})
        line = log_path.read_text().strip()
        entry = json.loads(line)
        assert entry["seq"] == 1
        assert entry["epoch"] == 0
        assert "ts" in entry

    def test_read_since_zero(self, activity_log):
        activity_log.append({"type": "log", "message": "a"})
        activity_log.append({"type": "log", "message": "b"})
        result = activity_log.read_since(cursor_seq=0)
        assert len(result["entries"]) == 2
        assert result["entries"][0]["message"] == "a"
        assert result["entries"][1]["message"] == "b"

    def test_read_since_partial(self, activity_log):
        activity_log.append({"type": "log", "message": "a"})
        activity_log.append({"type": "log", "message": "b"})
        activity_log.append({"type": "log", "message": "c"})
        result = activity_log.read_since(cursor_seq=1)
        assert len(result["entries"]) == 2
        assert result["entries"][0]["message"] == "b"

    def test_read_since_empty(self, activity_log):
        result = activity_log.read_since(cursor_seq=0)
        assert result["entries"] == []
        assert result["has_more"] is False

    def test_read_since_count_limit(self, activity_log):
        for i in range(10):
            activity_log.append({"type": "log", "message": f"msg-{i}"})
        result = activity_log.read_since(cursor_seq=0, count=3)
        assert len(result["entries"]) == 3
        assert result["has_more"] is True

    def test_cursor_tracks_position(self, activity_log):
        for i in range(5):
            activity_log.append({"type": "log", "message": f"msg-{i}"})

        # First read
        r1 = activity_log.read_since(cursor_seq=0, count=2)
        assert len(r1["entries"]) == 2
        cursor = r1["cursor"]

        # Continue from cursor
        r2 = activity_log.read_since(cursor_seq=cursor["seq"], count=10)
        assert len(r2["entries"]) == 3
        assert r2["entries"][0]["message"] == "msg-2"


# ── Truncation and epoch ────────────────────────────────────────────────────


class TestTruncation:
    def test_truncation_bumps_epoch(self, log_path):
        from dazzle.mcp.server.activity_log import (
            KEEP_AFTER_TRUNCATE,
            MAX_ENTRIES,
            ActivityLog,
        )

        log = ActivityLog(log_path)
        assert log.current_epoch == 0

        for i in range(MAX_ENTRIES + 1):
            log.append({"type": "log", "message": f"msg-{i}"})

        assert log.current_epoch == 1
        # Entry count should be around KEEP_AFTER_TRUNCATE + 1 (the one that triggered)
        lines = [ln for ln in log_path.read_text().splitlines() if ln.strip()]
        assert len(lines) <= KEEP_AFTER_TRUNCATE + 5  # small tolerance

    def test_stale_cursor_detection(self, log_path):
        from dazzle.mcp.server.activity_log import MAX_ENTRIES, ActivityLog

        log = ActivityLog(log_path)

        # Write some entries at epoch 0
        log.append({"type": "log", "message": "old"})
        old_cursor = log.read_since(cursor_seq=0)["cursor"]

        # Force truncation
        for i in range(MAX_ENTRIES + 1):
            log.append({"type": "log", "message": f"fill-{i}"})

        # Read with old cursor — should detect staleness
        result = log.read_since(
            cursor_seq=old_cursor["seq"],
            cursor_epoch=old_cursor["epoch"],
        )
        assert result["stale"] is True
        # Should return entries from the beginning (cursor reset)
        assert len(result["entries"]) > 0


# ── Clear ────────────────────────────────────────────────────────────────────


class TestClear:
    def test_clear_empties_log(self, activity_log, log_path):
        activity_log.append({"type": "log", "message": "data"})
        activity_log.clear()
        assert log_path.read_text() == ""

    def test_clear_bumps_epoch(self, activity_log):
        assert activity_log.current_epoch == 0
        activity_log.clear()
        assert activity_log.current_epoch == 1

    def test_clear_resets_seq(self, activity_log):
        activity_log.append({"type": "log", "message": "x"})
        assert activity_log.current_seq == 1
        activity_log.clear()
        assert activity_log.current_seq == 0


# ── Active tool tracking ────────────────────────────────────────────────────


class TestActiveToolTracking:
    def test_tracks_tool_start(self, activity_log):
        activity_log.append({"type": "tool_start", "tool": "pipeline", "operation": "run"})
        assert activity_log.active_tool == "pipeline"

    def test_clears_on_tool_end(self, activity_log):
        activity_log.append({"type": "tool_start", "tool": "pipeline", "operation": "run"})
        activity_log.append({"type": "tool_end", "tool": "pipeline", "operation": "run"})
        assert activity_log.active_tool is None

    def test_read_since_includes_active_tool(self, activity_log):
        activity_log.append({"type": "tool_start", "tool": "dsl", "operation": "validate"})
        result = activity_log.read_since(cursor_seq=0)
        assert result["active_tool"] is not None
        assert result["active_tool"]["tool"] == "dsl"
        assert result["active_tool"]["operation"] == "validate"

    def test_read_since_no_active_when_complete(self, activity_log):
        activity_log.append({"type": "tool_start", "tool": "dsl", "operation": "validate"})
        activity_log.append({"type": "tool_end", "tool": "dsl"})
        result = activity_log.read_since(cursor_seq=0)
        assert result["active_tool"] is None


# ── Thread safety ────────────────────────────────────────────────────────────


class TestThreadSafety:
    def test_concurrent_appends(self, activity_log):
        """Multiple threads appending should produce unique, monotonic seq numbers."""
        results: list[int] = []
        lock = threading.Lock()

        def writer(n: int) -> None:
            for _ in range(50):
                seq = activity_log.append({"type": "log", "message": f"t{n}"})
                with lock:
                    results.append(seq)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 200
        assert len(set(results)) == 200  # All unique
        assert sorted(results) == list(range(1, 201))  # Monotonic


# ── State recovery ──────────────────────────────────────────────────────────


class TestRecovery:
    def test_recovers_seq_from_existing_log(self, log_path):
        from dazzle.mcp.server.activity_log import ActivityLog

        # Write some entries
        log1 = ActivityLog(log_path)
        log1.append({"type": "log", "message": "first"})
        log1.append({"type": "log", "message": "second"})
        assert log1.current_seq == 2

        # Create new instance from same file
        log2 = ActivityLog(log_path)
        assert log2.current_seq == 2
        # Next append should continue from 3
        seq = log2.append({"type": "log", "message": "third"})
        assert seq == 3


# ── Entry factories ─────────────────────────────────────────────────────────


class TestEntryFactories:
    def test_make_tool_start_entry(self):
        from dazzle.mcp.server.activity_log import make_tool_start_entry

        entry = make_tool_start_entry("pipeline", "run")
        assert entry["type"] == "tool_start"
        assert entry["tool"] == "pipeline"
        assert entry["operation"] == "run"

    def test_make_tool_end_entry_success(self):
        from dazzle.mcp.server.activity_log import make_tool_end_entry

        entry = make_tool_end_entry("dsl", "validate", success=True, duration_ms=123.456)
        assert entry["type"] == "tool_end"
        assert entry["success"] is True
        assert entry["duration_ms"] == 123.5  # rounded

    def test_make_tool_end_entry_failure(self):
        from dazzle.mcp.server.activity_log import make_tool_end_entry

        entry = make_tool_end_entry("dsl", "validate", success=False, error="boom")
        assert entry["success"] is False
        assert entry["error"] == "boom"

    def test_make_progress_entry(self):
        from dazzle.mcp.server.activity_log import make_progress_entry

        entry = make_progress_entry("pipeline", "Running step 3", current=3, total=10)
        assert entry["type"] == "progress"
        assert entry["current"] == 3
        assert entry["total"] == 10

    def test_make_log_entry(self):
        from dazzle.mcp.server.activity_log import make_progress_entry

        entry = make_progress_entry("dsl", "Parsing modules")
        assert entry["type"] == "log"
        assert "current" not in entry

    def test_make_error_entry(self):
        from dazzle.mcp.server.activity_log import make_error_entry

        entry = make_error_entry("pipeline", "Step failed", operation="run")
        assert entry["type"] == "error"
        assert entry["level"] == "error"


# ── Formatting ──────────────────────────────────────────────────────────────


class TestFormatting:
    def test_format_tool_start_plain(self):
        from dazzle.mcp.server.activity_log import ActivityLog

        entry = {
            "type": "tool_start",
            "tool": "pipeline",
            "operation": "run",
            "ts": "2026-02-11T14:30:00.123+00:00",
            "seq": 1,
        }
        text = ActivityLog.format_entry(entry, color=False)
        assert "pipeline.run" in text
        assert "\u25b6" in text  # ▶

    def test_format_tool_end_success_plain(self):
        from dazzle.mcp.server.activity_log import ActivityLog

        entry = {
            "type": "tool_end",
            "tool": "dsl",
            "operation": "validate",
            "success": True,
            "duration_ms": 42.3,
            "ts": "2026-02-11T14:30:00.165+00:00",
            "seq": 2,
        }
        text = ActivityLog.format_entry(entry, color=False)
        assert "dsl.validate" in text
        assert "42ms" in text
        assert "OK" in text

    def test_format_tool_end_failure_plain(self):
        from dazzle.mcp.server.activity_log import ActivityLog

        entry = {
            "type": "tool_end",
            "tool": "dsl",
            "operation": "validate",
            "success": False,
            "error": "Parse error",
            "duration_ms": 10,
            "ts": "2026-02-11T14:30:00.165+00:00",
            "seq": 2,
        }
        text = ActivityLog.format_entry(entry, color=False)
        assert "FAIL" in text
        assert "Parse error" in text

    def test_format_progress_with_bar_plain(self):
        from dazzle.mcp.server.activity_log import ActivityLog

        entry = {
            "type": "progress",
            "tool": "pipeline",
            "message": "Running fidelity",
            "current": 3,
            "total": 10,
            "ts": "2026-02-11T14:30:01.000+00:00",
            "seq": 5,
        }
        text = ActivityLog.format_entry(entry, color=False)
        assert "30%" in text
        assert "[3/10]" in text
        assert "Running fidelity" in text

    def test_format_entry_with_color(self):
        from dazzle.mcp.server.activity_log import ActivityLog

        entry = {
            "type": "tool_start",
            "tool": "pipeline",
            "operation": "run",
            "ts": "2026-02-11T14:30:00.123+00:00",
            "seq": 1,
        }
        text = ActivityLog.format_entry(entry, color=True)
        assert "\033[" in text  # Contains ANSI codes
        assert "pipeline.run" in text

    def test_format_summary_with_active(self):
        from dazzle.mcp.server.activity_log import ActivityLog

        data = {
            "entries": [
                {
                    "type": "tool_start",
                    "tool": "pipeline",
                    "operation": "run",
                    "ts": "2026-02-11T14:30:00.123+00:00",
                    "seq": 1,
                }
            ],
            "cursor": {"seq": 1, "epoch": 0},
            "has_more": False,
            "stale": False,
            "active_tool": {"tool": "pipeline", "operation": "run", "elapsed_ms": 5000},
        }
        text = ActivityLog.format_summary(data, color=False)
        assert "IN PROGRESS" in text
        assert "pipeline.run" in text
        assert "5.0s" in text

    def test_format_summary_empty(self):
        from dazzle.mcp.server.activity_log import ActivityLog

        data = {
            "entries": [],
            "cursor": {"seq": 0, "epoch": 0},
            "has_more": False,
            "stale": False,
            "active_tool": None,
        }
        text = ActivityLog.format_summary(data, color=False)
        assert "No recent activity" in text

    def test_progress_bar(self):
        from dazzle.mcp.server.activity_log import _progress_bar

        bar = _progress_bar(5, 10, color=False)
        assert "50%" in bar
        assert "[5/10]" in bar
        assert "━" in bar  # filled portion
        assert "─" in bar  # empty portion


# ── ProgressContext integration ─────────────────────────────────────────────


@pytest.fixture()
def _activity_store_for_progress():
    """ActivityStore backed by an in-memory KG for ProgressContext tests."""
    from dazzle.mcp.knowledge_graph import KnowledgeGraph
    from dazzle.mcp.server.activity_log import ActivityStore

    graph = KnowledgeGraph(":memory:")
    session_id = graph.start_activity_session(
        project_name="test_project",
        project_path="/tmp/test",
        version="0.1.0",
    )
    return ActivityStore(graph, session_id)


class TestProgressContextIntegration:
    def test_log_writes_to_sqlite(self, _activity_store_for_progress):
        """ProgressContext.log_sync should write to the attached activity store."""
        from dazzle.mcp.server.progress import ProgressContext

        ctx = ProgressContext(
            session=None,
            activity_store=_activity_store_for_progress,
            tool_name="test_tool",
            operation="test_op",
        )
        ctx.log_sync("hello from sync")

        events = _activity_store_for_progress.read_since(since_id=0)
        assert len(events) == 1
        assert events[0]["message"] == "hello from sync"
        assert events[0]["tool"] == "test_tool"

    def test_advance_sync_writes_progress(self, _activity_store_for_progress):
        """ProgressContext.advance_sync should write a progress entry."""
        from dazzle.mcp.server.progress import ProgressContext

        ctx = ProgressContext(
            session=None,
            activity_store=_activity_store_for_progress,
            tool_name="pipeline",
            operation="run",
        )
        ctx.advance_sync(3, 10, "Step 3")

        events = _activity_store_for_progress.read_since(since_id=0)
        assert len(events) == 1
        assert events[0]["event_type"] == "progress"
        assert events[0]["progress_current"] == 3
        assert events[0]["progress_total"] == 10

    @pytest.mark.asyncio
    async def test_async_log_writes_to_sqlite(self, _activity_store_for_progress):
        """ProgressContext.log should write to the attached activity store."""
        from dazzle.mcp.server.progress import ProgressContext

        ctx = ProgressContext(
            session=None,
            activity_store=_activity_store_for_progress,
            tool_name="dsl",
            operation="validate",
        )
        await ctx.log("parsing modules")

        events = _activity_store_for_progress.read_since(since_id=0)
        assert len(events) == 1
        assert events[0]["message"] == "parsing modules"

    @pytest.mark.asyncio
    async def test_async_advance_writes_progress(self, _activity_store_for_progress):
        """ProgressContext.advance should write a structured progress entry."""
        from dazzle.mcp.server.progress import ProgressContext

        ctx = ProgressContext(
            session=None,
            activity_store=_activity_store_for_progress,
            tool_name="pipeline",
            operation="run",
        )
        await ctx.advance(5, 12, "Fidelity check")

        events = _activity_store_for_progress.read_since(since_id=0)
        assert len(events) == 1
        assert events[0]["event_type"] == "progress"
        assert events[0]["progress_current"] == 5
        assert events[0]["progress_total"] == 12


# ── Status handler integration ──────────────────────────────────────────────


class TestStatusHandler:
    def test_get_activity_handler_structured(self, monkeypatch):
        from dazzle.mcp.knowledge_graph import KnowledgeGraph
        from dazzle.mcp.server.activity_log import ActivityStore
        from dazzle.mcp.server.handlers import status as status_mod

        graph = KnowledgeGraph(":memory:")
        session_id = graph.start_activity_session(
            project_name="test", project_path="/tmp/test", version="0.1.0"
        )
        store = ActivityStore(graph, session_id)
        monkeypatch.setattr("dazzle.mcp.server.state._activity_store", store)

        store.log_event("tool_start", "dsl", "validate")
        store.log_event("tool_end", "dsl", "validate", success=True, duration_ms=50)

        result = json.loads(status_mod.get_activity_handler({"count": 10}))
        assert len(result["entries"]) == 2
        assert "cursor" in result

    def test_get_activity_handler_formatted(self, monkeypatch):
        from dazzle.mcp.knowledge_graph import KnowledgeGraph
        from dazzle.mcp.server.activity_log import ActivityStore

        graph = KnowledgeGraph(":memory:")
        session_id = graph.start_activity_session(
            project_name="test", project_path="/tmp/test", version="0.1.0"
        )
        store = ActivityStore(graph, session_id)
        monkeypatch.setattr("dazzle.mcp.server.state._activity_store", store)

        store.log_event("tool_start", "pipeline", "run")

        from dazzle.mcp.server.handlers.status import get_activity_handler

        result = json.loads(get_activity_handler({"format": "formatted"}))
        assert "formatted" in result
        assert "pipeline.run" in result["formatted"]
