"""Tests for test result persistence in the Knowledge Graph."""

from __future__ import annotations

import importlib.util
import sys
import time
import uuid
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


# Import modules in dependency order
_import_knowledge_graph_module("models")
_import_knowledge_graph_module("_protocol")
_import_knowledge_graph_module("query")
_import_knowledge_graph_module("metadata")
_import_knowledge_graph_module("activity")
_import_knowledge_graph_module("test_results")
_store_module = _import_knowledge_graph_module("store")
KnowledgeGraph = _store_module.KnowledgeGraph


def _make_graph():
    """Create an in-memory graph."""
    return KnowledgeGraph(":memory:")


def _make_run_id() -> str:
    return str(uuid.uuid4())


class TestSaveAndGetTestRuns:
    """Test saving and retrieving test runs."""

    def test_round_trip(self) -> None:
        graph = _make_graph()
        run_id = _make_run_id()
        now = time.time()

        graph.save_test_run(
            run_id=run_id,
            project_name="test_project",
            dsl_hash="abc123",
            started_at=now,
            completed_at=now + 5.0,
            total_tests=10,
            passed=8,
            failed=2,
            success_rate=80.0,
            tests_generated=10,
            trigger="run_all",
        )

        runs = graph.get_test_runs(project_name="test_project")
        assert len(runs) == 1
        assert runs[0]["id"] == run_id
        assert runs[0]["total_tests"] == 10
        assert runs[0]["passed"] == 8
        assert runs[0]["failed"] == 2
        assert runs[0]["success_rate"] == 80.0
        assert runs[0]["trigger"] == "run_all"

    def test_filter_by_project_name(self) -> None:
        graph = _make_graph()
        now = time.time()

        for name in ["project_a", "project_b"]:
            graph.save_test_run(
                run_id=_make_run_id(),
                project_name=name,
                dsl_hash="hash",
                started_at=now,
            )

        runs = graph.get_test_runs(project_name="project_a")
        assert len(runs) == 1
        assert runs[0]["project_name"] == "project_a"

    def test_filter_by_dsl_hash(self) -> None:
        graph = _make_graph()
        now = time.time()

        graph.save_test_run(
            run_id=_make_run_id(), project_name="p", dsl_hash="hash_a", started_at=now
        )
        graph.save_test_run(
            run_id=_make_run_id(), project_name="p", dsl_hash="hash_b", started_at=now
        )

        runs = graph.get_test_runs(dsl_hash="hash_a")
        assert len(runs) == 1
        assert runs[0]["dsl_hash"] == "hash_a"

    def test_limit(self) -> None:
        graph = _make_graph()
        now = time.time()

        for i in range(5):
            graph.save_test_run(
                run_id=_make_run_id(), project_name="p", dsl_hash="h", started_at=now + i
            )

        runs = graph.get_test_runs(limit=3)
        assert len(runs) == 3

    def test_ordering_newest_first(self) -> None:
        graph = _make_graph()
        now = time.time()

        id1 = _make_run_id()
        id2 = _make_run_id()
        graph.save_test_run(run_id=id1, project_name="p", dsl_hash="h", started_at=now)
        graph.save_test_run(run_id=id2, project_name="p", dsl_hash="h", started_at=now + 10)

        runs = graph.get_test_runs()
        assert runs[0]["id"] == id2  # newest first


class TestSaveAndGetTestCases:
    """Test saving and retrieving test cases."""

    def _setup_run(self, graph) -> str:
        run_id = _make_run_id()
        graph.save_test_run(run_id=run_id, project_name="p", dsl_hash="h", started_at=time.time())
        return run_id

    def test_save_single_case(self) -> None:
        graph = _make_graph()
        run_id = self._setup_run(graph)

        graph.save_test_case(
            run_id=run_id,
            test_id="CRUD_Task_create",
            title="Create Task",
            category="crud",
            result="passed",
        )

        cases = graph.get_test_cases(run_id)
        assert len(cases) == 1
        assert cases[0]["test_id"] == "CRUD_Task_create"
        assert cases[0]["result"] == "passed"

    def test_batch_save(self) -> None:
        graph = _make_graph()
        run_id = self._setup_run(graph)

        cases = [
            {
                "test_id": f"CRUD_Task_{i}",
                "title": f"Test {i}",
                "category": "crud",
                "result": "passed",
            }
            for i in range(5)
        ]
        inserted = graph.save_test_cases_batch(run_id, cases)
        assert inserted == 5

        retrieved = graph.get_test_cases(run_id)
        assert len(retrieved) == 5

    def test_batch_empty(self) -> None:
        graph = _make_graph()
        inserted = graph.save_test_cases_batch("no-run", [])
        assert inserted == 0

    def test_filter_by_result(self) -> None:
        graph = _make_graph()
        run_id = self._setup_run(graph)

        graph.save_test_cases_batch(
            run_id,
            [
                {"test_id": "T1", "title": "T1", "category": "crud", "result": "passed"},
                {
                    "test_id": "T2",
                    "title": "T2",
                    "category": "crud",
                    "result": "failed",
                    "error_message": "err",
                },
            ],
        )

        failed = graph.get_test_cases(run_id, result_filter="failed")
        assert len(failed) == 1
        assert failed[0]["test_id"] == "T2"

    def test_filter_by_category(self) -> None:
        graph = _make_graph()
        run_id = self._setup_run(graph)

        graph.save_test_cases_batch(
            run_id,
            [
                {"test_id": "T1", "title": "T1", "category": "crud", "result": "passed"},
                {"test_id": "T2", "title": "T2", "category": "state_machine", "result": "passed"},
            ],
        )

        sm = graph.get_test_cases(run_id, category_filter="state_machine")
        assert len(sm) == 1
        assert sm[0]["test_id"] == "T2"

    def test_filter_by_failure_type(self) -> None:
        graph = _make_graph()
        run_id = self._setup_run(graph)

        graph.save_test_cases_batch(
            run_id,
            [
                {
                    "test_id": "T1",
                    "title": "T1",
                    "category": "crud",
                    "result": "failed",
                    "failure_type": "rbac_denied",
                },
                {
                    "test_id": "T2",
                    "title": "T2",
                    "category": "crud",
                    "result": "failed",
                    "failure_type": "timeout",
                },
            ],
        )

        rbac = graph.get_test_cases(run_id, failure_type_filter="rbac_denied")
        assert len(rbac) == 1
        assert rbac[0]["test_id"] == "T1"


class TestFailureSummary:
    """Test failure summary aggregation."""

    def _populate(self, graph, run_count=2, tests_per_run=3):
        """Create runs with some failures."""
        now = time.time()
        for i in range(run_count):
            run_id = _make_run_id()
            graph.save_test_run(
                run_id=run_id,
                project_name="p",
                dsl_hash="h",
                started_at=now + i,
                total_tests=tests_per_run,
            )
            graph.save_test_cases_batch(
                run_id,
                [
                    {"test_id": "T_pass", "title": "Pass", "category": "crud", "result": "passed"},
                    {
                        "test_id": "T_fail",
                        "title": "Fail",
                        "category": "crud",
                        "result": "failed",
                        "failure_type": "rbac_denied",
                    },
                    {
                        "test_id": "T_flaky",
                        "title": "Flaky",
                        "category": "state_machine",
                        "result": "passed" if i % 2 == 0 else "failed",
                        "failure_type": None if i % 2 == 0 else "timeout",
                    },
                ],
            )

    def test_by_failure_type(self) -> None:
        graph = _make_graph()
        self._populate(graph)
        summary = graph.get_failure_summary(project_name="p")

        assert "rbac_denied" in summary["by_failure_type"]
        assert summary["by_failure_type"]["rbac_denied"] == 2

    def test_by_category(self) -> None:
        graph = _make_graph()
        self._populate(graph)
        summary = graph.get_failure_summary(project_name="p")

        assert "crud" in summary["by_category"]

    def test_flaky_detection(self) -> None:
        graph = _make_graph()
        self._populate(graph)
        summary = graph.get_failure_summary(project_name="p")

        flaky_ids = {t["test_id"] for t in summary["flaky_tests"]}
        assert "T_flaky" in flaky_ids

    def test_persistent_failures(self) -> None:
        graph = _make_graph()
        self._populate(graph)
        summary = graph.get_failure_summary(project_name="p")

        persistent_ids = {t["test_id"] for t in summary["persistent_failures"]}
        assert "T_fail" in persistent_ids

    def test_empty_state(self) -> None:
        graph = _make_graph()
        summary = graph.get_failure_summary(project_name="empty")
        assert summary["runs_analyzed"] == 0
        assert summary["flaky_tests"] == []


class TestRegressionDetection:
    """Test regression detection between runs."""

    def test_detects_pass_to_fail(self) -> None:
        graph = _make_graph()
        now = time.time()

        # Older run: T1 passes
        run1 = _make_run_id()
        graph.save_test_run(run_id=run1, project_name="p", dsl_hash="h1", started_at=now)
        graph.save_test_cases_batch(
            run1,
            [{"test_id": "T1", "title": "T1", "category": "crud", "result": "passed"}],
        )

        # Newer run: T1 fails
        run2 = _make_run_id()
        graph.save_test_run(run_id=run2, project_name="p", dsl_hash="h2", started_at=now + 10)
        graph.save_test_cases_batch(
            run2,
            [
                {
                    "test_id": "T1",
                    "title": "T1",
                    "category": "crud",
                    "result": "failed",
                    "failure_type": "timeout",
                }
            ],
        )

        result = graph.detect_regressions(project_name="p")
        assert len(result["regressions"]) == 1
        assert result["regressions"][0]["test_id"] == "T1"
        assert result["dsl_changed"] is True

    def test_no_regression_when_still_passing(self) -> None:
        graph = _make_graph()
        now = time.time()

        for i in range(2):
            run_id = _make_run_id()
            graph.save_test_run(run_id=run_id, project_name="p", dsl_hash="h", started_at=now + i)
            graph.save_test_cases_batch(
                run_id,
                [{"test_id": "T1", "title": "T1", "category": "crud", "result": "passed"}],
            )

        result = graph.detect_regressions(project_name="p")
        assert len(result["regressions"]) == 0

    def test_insufficient_runs(self) -> None:
        graph = _make_graph()
        result = graph.detect_regressions(project_name="p")
        assert result["regressions"] == []
        assert "Need at least" in result.get("message", "")


class TestCoverageTrend:
    """Test coverage trend calculation."""

    def test_trend_data(self) -> None:
        graph = _make_graph()
        now = time.time()

        for i in range(3):
            graph.save_test_run(
                run_id=_make_run_id(),
                project_name="p",
                dsl_hash=f"h{i}",
                started_at=now + i,
                total_tests=10,
                passed=10 - i,
                failed=i,
                success_rate=(10 - i) / 10 * 100,
            )

        trend = graph.get_test_coverage_trend(project_name="p", limit_runs=3)
        assert len(trend) == 3
        # Newest first
        assert trend[0]["failed"] == 2
        assert trend[2]["failed"] == 0

    def test_empty_trend(self) -> None:
        graph = _make_graph()
        trend = graph.get_test_coverage_trend(project_name="empty")
        assert trend == []
