"""Tests for workshop screen data and navigation logic."""

from __future__ import annotations

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
