"""Tests for test_intelligence MCP handler operations."""

from __future__ import annotations

import importlib.util
import json
import sys
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch


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


# Ensure KG modules are importable
_import_knowledge_graph_module("models")
_import_knowledge_graph_module("_protocol")
_import_knowledge_graph_module("query")
_import_knowledge_graph_module("metadata")
_import_knowledge_graph_module("activity")
_import_knowledge_graph_module("test_results")
_store_module = _import_knowledge_graph_module("store")
KnowledgeGraph = _store_module.KnowledgeGraph

# Pre-mock mcp and all submodules to avoid import errors
_mcp_mock = MagicMock(pytest_plugins=[])
for mod_name in [
    "mcp",
    "mcp.types",
    "mcp.server",
    "mcp.server.stdio",
    "mcp.server.models",
    "mcp.server.fastmcp",
]:
    sys.modules.setdefault(mod_name, _mcp_mock)

# Now import the handler module directly (file-based to skip dazzle.mcp.__init__)
_src = Path(__file__).parent.parent.parent / "src"

# We need to import the common module first since test_intelligence imports from it
_common_path = _src / "dazzle" / "mcp" / "server" / "handlers" / "common.py"
_common_spec = importlib.util.spec_from_file_location(
    "dazzle.mcp.server.handlers.common",
    _common_path,
)
_common_module = importlib.util.module_from_spec(_common_spec)
sys.modules["dazzle.mcp.server.handlers.common"] = _common_module
_common_spec.loader.exec_module(_common_module)

# Import the progress module (needed by common)
_progress_path = _src / "dazzle" / "mcp" / "server" / "progress.py"
if "dazzle.mcp.server.progress" not in sys.modules:
    _progress_spec = importlib.util.spec_from_file_location(
        "dazzle.mcp.server.progress",
        _progress_path,
    )
    _progress_module = importlib.util.module_from_spec(_progress_spec)
    sys.modules["dazzle.mcp.server.progress"] = _progress_module
    # Also add the parent packages so relative imports work
    sys.modules.setdefault("dazzle.mcp.server", MagicMock())
    sys.modules.setdefault("dazzle.mcp.server.handlers", MagicMock())

# Import the handler
_handler_module_path = _src / "dazzle" / "mcp" / "server" / "handlers" / "test_intelligence.py"
_spec = importlib.util.spec_from_file_location(
    "dazzle.mcp.server.handlers.test_intelligence",
    _handler_module_path,
)
_handler_module = importlib.util.module_from_spec(_spec)
sys.modules["dazzle.mcp.server.handlers.test_intelligence"] = _handler_module
_spec.loader.exec_module(_handler_module)

_summary_handler = _handler_module.test_summary_handler
_failures_handler = _handler_module.test_failures_handler
_regression_handler = _handler_module.test_regression_handler
_coverage_handler = _handler_module.test_coverage_handler
_context_handler = _handler_module.test_context_handler


def _make_graph_with_data() -> KnowledgeGraph:
    """Create graph with sample test data."""
    graph = KnowledgeGraph(":memory:")
    now = time.time()

    # Run 1 (older): 2 pass, 1 fail
    run1 = str(uuid.uuid4())
    graph.save_test_run(
        run_id=run1,
        project_name="test_project",
        dsl_hash="hash_old",
        started_at=now - 60,
        completed_at=now - 55,
        total_tests=3,
        passed=2,
        failed=1,
        success_rate=66.7,
    )
    graph.save_test_cases_batch(
        run1,
        [
            {"test_id": "T1", "title": "T1", "category": "crud", "result": "passed"},
            {"test_id": "T2", "title": "T2", "category": "crud", "result": "passed"},
            {
                "test_id": "T3",
                "title": "T3",
                "category": "state_machine",
                "result": "failed",
                "failure_type": "timeout",
            },
        ],
    )

    # Run 2 (newer): T1 regresses, T3 still fails
    run2 = str(uuid.uuid4())
    graph.save_test_run(
        run_id=run2,
        project_name="test_project",
        dsl_hash="hash_new",
        started_at=now,
        completed_at=now + 5,
        total_tests=3,
        passed=1,
        failed=2,
        success_rate=33.3,
    )
    graph.save_test_cases_batch(
        run2,
        [
            {
                "test_id": "T1",
                "title": "T1",
                "category": "crud",
                "result": "failed",
                "failure_type": "rbac_denied",
            },
            {"test_id": "T2", "title": "T2", "category": "crud", "result": "passed"},
            {
                "test_id": "T3",
                "title": "T3",
                "category": "state_machine",
                "result": "failed",
                "failure_type": "timeout",
            },
        ],
    )

    return graph


def _make_mock_manifest():
    """Create a mock manifest."""
    m = MagicMock()
    m.project_name = "test_project"
    return m


class TestTestSummaryHandler:
    """Test the summary operation."""

    def test_returns_valid_json(self) -> None:
        graph = _make_graph_with_data()
        project_root = Path("/tmp/test_project")

        with (
            patch.object(_handler_module, "_get_graph", return_value=graph),
            patch.object(_handler_module, "_project_name_from_root", return_value="test_project"),
        ):
            result = _summary_handler(project_root, {})

        data = json.loads(result)
        assert data["project"] == "test_project"
        assert data["total_runs"] == 2
        assert len(data["runs"]) == 2

    def test_runs_ordered_newest_first(self) -> None:
        graph = _make_graph_with_data()

        with (
            patch.object(_handler_module, "_get_graph", return_value=graph),
            patch.object(_handler_module, "_project_name_from_root", return_value="test_project"),
        ):
            result = _summary_handler(Path("/tmp"), {})

        data = json.loads(result)
        assert data["runs"][0]["success_rate"] == 33.3  # newer run

    def test_no_graph_returns_error(self) -> None:
        with (
            patch.object(_handler_module, "_get_graph", return_value=None),
        ):
            result = _summary_handler(Path("/tmp"), {})

        data = json.loads(result)
        assert "error" in data


class TestTestFailuresHandler:
    """Test the failures operation."""

    def test_returns_failure_breakdown(self) -> None:
        graph = _make_graph_with_data()

        with (
            patch.object(_handler_module, "_get_graph", return_value=graph),
            patch.object(_handler_module, "_project_name_from_root", return_value="test_project"),
        ):
            result = _failures_handler(Path("/tmp"), {})

        data = json.loads(result)
        assert "by_failure_type" in data
        assert "by_category" in data
        assert "flaky_tests" in data
        assert "persistent_failures" in data

    def test_filter_by_failure_type(self) -> None:
        graph = _make_graph_with_data()

        with (
            patch.object(_handler_module, "_get_graph", return_value=graph),
            patch.object(_handler_module, "_project_name_from_root", return_value="test_project"),
        ):
            result = _failures_handler(Path("/tmp"), {"failure_type": "timeout"})

        data = json.loads(result)
        assert "timeout" in data["by_failure_type"]
        # Should not include rbac_denied
        assert "rbac_denied" not in data["by_failure_type"]


class TestTestRegressionHandler:
    """Test the regression operation."""

    def test_detects_regression(self) -> None:
        graph = _make_graph_with_data()

        with (
            patch.object(_handler_module, "_get_graph", return_value=graph),
            patch.object(_handler_module, "_project_name_from_root", return_value="test_project"),
        ):
            result = _regression_handler(Path("/tmp"), {})

        data = json.loads(result)
        assert "regressions" in data
        regression_ids = {r["test_id"] for r in data["regressions"]}
        assert "T1" in regression_ids  # T1 went pass→fail
        assert "T3" not in regression_ids  # T3 was already failing


class TestTestCoverageHandler:
    """Test the coverage operation."""

    def test_returns_trend(self) -> None:
        graph = _make_graph_with_data()

        with (
            patch.object(_handler_module, "_get_graph", return_value=graph),
            patch.object(_handler_module, "_project_name_from_root", return_value="test_project"),
        ):
            result = _coverage_handler(Path("/tmp"), {})

        data = json.loads(result)
        assert data["runs"] == 2
        assert len(data["trend"]) == 2


class TestTestContextHandler:
    """Test the context operation (single-call snapshot)."""

    def test_returns_combined_context(self) -> None:
        graph = _make_graph_with_data()

        with (
            patch.object(_handler_module, "_get_graph", return_value=graph),
            patch.object(_handler_module, "_project_name_from_root", return_value="test_project"),
        ):
            result = _context_handler(Path("/tmp"), {})

        data = json.loads(result)
        assert data["project"] == "test_project"
        assert data["latest_run"] is not None
        assert "failure_patterns" in data
        assert "regressions" in data
        assert "trend" in data

    def test_empty_state(self) -> None:
        graph = KnowledgeGraph(":memory:")

        with (
            patch.object(_handler_module, "_get_graph", return_value=graph),
            patch.object(_handler_module, "_project_name_from_root", return_value="empty_project"),
        ):
            result = _context_handler(Path("/tmp"), {})

        data = json.loads(result)
        assert data["latest_run"] is None
        assert data["runs_total"] == 0
