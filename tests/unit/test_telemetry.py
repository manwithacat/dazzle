"""Tests for MCP tool call telemetry logging."""

from __future__ import annotations

import importlib.util
import sys
import time
from pathlib import Path


def _import_knowledge_graph_module(module_name: str):
    """Import knowledge graph modules directly to avoid MCP package init issues."""
    module_path = (
        Path(__file__).parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "knowledge_graph"
        / f"{module_name}.py"
    )
    spec = importlib.util.spec_from_file_location(
        f"dazzle.mcp.knowledge_graph.{module_name}",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[f"dazzle.mcp.knowledge_graph.{module_name}"] = module
    spec.loader.exec_module(module)
    return module


_store_module = _import_knowledge_graph_module("store")
KnowledgeGraph = _store_module.KnowledgeGraph


class TestTelemetrySchema:
    """Tests for the tool_invocations table schema."""

    def test_telemetry_table_exists(self) -> None:
        """Fresh KG should have a tool_invocations table."""
        graph = KnowledgeGraph(":memory:")
        conn = graph._get_connection()
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='tool_invocations'"
            ).fetchone()
            assert row is not None
            assert row["name"] == "tool_invocations"
        finally:
            graph._close_connection(conn)


class TestTelemetryLogging:
    """Tests for log_tool_invocation and retrieval methods."""

    def test_log_and_retrieve(self) -> None:
        """Log one call, retrieve it, verify fields."""
        graph = KnowledgeGraph(":memory:")
        graph.log_tool_invocation(
            tool_name="dsl",
            operation="validate",
            argument_keys=["operation", "project_path"],
            project_path="/tmp/test",
            success=True,
            error_message=None,
            result_size=42,
            duration_ms=12.5,
        )

        rows = graph.get_tool_invocations(limit=10)
        assert len(rows) == 1
        row = rows[0]
        assert row["tool_name"] == "dsl"
        assert row["operation"] == "validate"
        assert row["argument_keys"] == '["operation", "project_path"]'
        assert row["project_path"] == "/tmp/test"
        assert row["success"] == 1
        assert row["error_message"] is None
        assert row["result_size"] == 42
        assert row["duration_ms"] == 12.5
        assert row["created_at"] > 0

    def test_argument_keys_not_values(self) -> None:
        """Verify only key names are stored, never values."""
        graph = KnowledgeGraph(":memory:")
        graph.log_tool_invocation(
            tool_name="story",
            operation="propose",
            argument_keys=["operation", "entities", "max_stories"],
            project_path=None,
            success=True,
            error_message=None,
            result_size=100,
            duration_ms=5.0,
        )

        rows = graph.get_tool_invocations()
        assert len(rows) == 1
        import json

        keys = json.loads(rows[0]["argument_keys"])
        assert keys == ["operation", "entities", "max_stories"]
        # No argument values should appear anywhere in the row
        row_str = str(rows[0])
        assert "secret_value" not in row_str

    def test_filter_by_tool_name(self) -> None:
        """Log multiple tools, filter works."""
        graph = KnowledgeGraph(":memory:")
        for tool in ["dsl", "dsl", "story", "graph"]:
            graph.log_tool_invocation(
                tool_name=tool,
                operation="test",
                argument_keys=None,
                project_path=None,
                success=True,
                error_message=None,
                result_size=None,
                duration_ms=1.0,
            )

        all_rows = graph.get_tool_invocations(limit=100)
        assert len(all_rows) == 4

        dsl_rows = graph.get_tool_invocations(tool_name_filter="dsl")
        assert len(dsl_rows) == 2
        assert all(r["tool_name"] == "dsl" for r in dsl_rows)

        story_rows = graph.get_tool_invocations(tool_name_filter="story")
        assert len(story_rows) == 1

    def test_filter_by_since(self) -> None:
        """Log calls, query with since, verify recency filter."""
        graph = KnowledgeGraph(":memory:")

        # Log an old call by inserting directly with an old timestamp
        conn = graph._get_connection()
        old_time = time.time() - 3600  # 1 hour ago
        try:
            conn.execute(
                """INSERT INTO tool_invocations
                   (tool_name, operation, success, duration_ms, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                ("dsl", "old_op", 1, 1.0, old_time),
            )
            conn.commit()
        finally:
            graph._close_connection(conn)

        # Log a recent call
        graph.log_tool_invocation(
            tool_name="dsl",
            operation="new_op",
            argument_keys=None,
            project_path=None,
            success=True,
            error_message=None,
            result_size=None,
            duration_ms=2.0,
        )

        # All calls
        all_rows = graph.get_tool_invocations(limit=100)
        assert len(all_rows) == 2

        # Only recent (last 30 minutes)
        since = time.time() - 1800
        recent_rows = graph.get_tool_invocations(since=since)
        assert len(recent_rows) == 1
        assert recent_rows[0]["operation"] == "new_op"

    def test_stats_aggregation(self) -> None:
        """Log mixed success/failure, verify counts and averages."""
        graph = KnowledgeGraph(":memory:")

        # 2 successes, 1 failure for "dsl"
        graph.log_tool_invocation(
            tool_name="dsl",
            operation="v",
            argument_keys=None,
            project_path=None,
            success=True,
            error_message=None,
            result_size=None,
            duration_ms=10.0,
        )
        graph.log_tool_invocation(
            tool_name="dsl",
            operation="v",
            argument_keys=None,
            project_path=None,
            success=True,
            error_message=None,
            result_size=None,
            duration_ms=20.0,
        )
        graph.log_tool_invocation(
            tool_name="dsl",
            operation="v",
            argument_keys=None,
            project_path=None,
            success=False,
            error_message="boom",
            result_size=None,
            duration_ms=30.0,
        )

        # 1 success for "story"
        graph.log_tool_invocation(
            tool_name="story",
            operation="p",
            argument_keys=None,
            project_path=None,
            success=True,
            error_message=None,
            result_size=None,
            duration_ms=5.0,
        )

        stats = graph.get_tool_stats()
        assert stats["total_calls"] == 4

        by_tool = {t["tool_name"]: t for t in stats["by_tool"]}
        assert "dsl" in by_tool
        assert by_tool["dsl"]["call_count"] == 3
        assert by_tool["dsl"]["error_count"] == 1
        assert by_tool["dsl"]["avg_duration_ms"] == 20.0
        assert by_tool["dsl"]["max_duration_ms"] == 30.0

        assert "story" in by_tool
        assert by_tool["story"]["call_count"] == 1
        assert by_tool["story"]["error_count"] == 0

    def test_error_message_stored(self) -> None:
        """Log a failed call, verify error_message is present."""
        graph = KnowledgeGraph(":memory:")
        graph.log_tool_invocation(
            tool_name="graph",
            operation="query",
            argument_keys=["operation", "text"],
            project_path=None,
            success=False,
            error_message="ValueError: something went wrong",
            result_size=None,
            duration_ms=3.0,
        )

        rows = graph.get_tool_invocations()
        assert len(rows) == 1
        assert rows[0]["success"] == 0
        assert rows[0]["error_message"] == "ValueError: something went wrong"

    def test_result_size_captured(self) -> None:
        """Verify result_size matches logged value."""
        graph = KnowledgeGraph(":memory:")
        graph.log_tool_invocation(
            tool_name="status",
            operation="mcp",
            argument_keys=["operation"],
            project_path=None,
            success=True,
            error_message=None,
            result_size=1234,
            duration_ms=0.5,
        )

        rows = graph.get_tool_invocations()
        assert rows[0]["result_size"] == 1234
