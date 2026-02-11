"""Tests for the pipeline MCP handler — summary mode, metrics extractors, top issues."""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Direct-import helper (same pattern as test_fidelity_handlers.py)
# ---------------------------------------------------------------------------


def _import_pipeline():
    """Import pipeline handlers directly to avoid MCP package init issues."""
    sys.modules.setdefault("dazzle.mcp.server.handlers", MagicMock(pytest_plugins=[]))

    module_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "server"
        / "handlers"
        / "pipeline.py"
    )
    spec = importlib.util.spec_from_file_location(
        "dazzle.mcp.server.handlers.pipeline",
        module_path,
        submodule_search_locations=[],
    )
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "dazzle.mcp.server.handlers"
    sys.modules["dazzle.mcp.server.handlers.pipeline"] = module
    spec.loader.exec_module(module)
    return module


_pl = _import_pipeline()

_extract_step_metrics = _pl._extract_step_metrics
_collect_top_issues = _pl._collect_top_issues
_build_pipeline_response = _pl._build_pipeline_response
run_pipeline_handler = _pl.run_pipeline_handler


# =============================================================================
# TestExtractStepMetrics
# =============================================================================


class TestExtractStepMetrics:
    """Unit tests for _extract_step_metrics dispatch."""

    def test_validate_metrics(self) -> None:
        data = {"status": "valid", "module_count": 2, "entity_count": 5, "surface_count": 3}
        m = _extract_step_metrics("dsl(validate)", data)
        assert m == {"status": "valid", "modules": 2, "entities": 5, "surfaces": 3}

    def test_validate_metrics_alternate_keys(self) -> None:
        data = {"modules": 1, "entities": 2, "surfaces": 1}
        m = _extract_step_metrics("dsl(validate)", data)
        assert m["modules"] == 1
        assert m["entities"] == 2

    def test_lint_metrics_lists(self) -> None:
        data = {"errors": ["err1", "err2"], "warnings": ["w1"]}
        m = _extract_step_metrics("dsl(lint)", data)
        assert m == {"errors": 2, "warnings": 1}

    def test_lint_metrics_counts(self) -> None:
        data = {"errors": 3, "warnings": 0}
        m = _extract_step_metrics("dsl(lint)", data)
        assert m == {"errors": 3, "warnings": 0}

    def test_fidelity_metrics(self) -> None:
        data = {
            "overall_fidelity": 0.85,
            "total_gaps": 3,
            "story_coverage": 0.7,
            "surfaces": [{"surface": "a"}, {"surface": "b"}],
        }
        m = _extract_step_metrics("dsl(fidelity)", data)
        assert m["overall_fidelity"] == 0.85
        assert m["surfaces_with_gaps"] == 2
        assert m["total_gaps"] == 3

    def test_composition_audit_metrics(self) -> None:
        data = {
            "overall_score": 75,
            "pages": [
                {
                    "route": "/",
                    "score": 75,
                    "violations_count": {"high": 1, "medium": 2, "low": 0},
                },
                {
                    "route": "/about",
                    "score": 90,
                    "violations_count": {"high": 0, "medium": 1, "low": 0},
                },
            ],
        }
        m = _extract_step_metrics("composition(audit)", data)
        assert m["overall_score"] == 75
        assert m["pages_audited"] == 2
        assert m["violations"] == {"high": 1, "medium": 3, "low": 0}

    def test_composition_audit_no_pages(self) -> None:
        data = {"overall_score": 100, "pages": []}
        m = _extract_step_metrics("composition(audit)", data)
        assert m["overall_score"] == 100
        assert m["pages_audited"] == 0
        assert m["violations"] == {}

    def test_test_generate_metrics(self) -> None:
        data = {
            "tests": [
                {"category": "crud", "name": "t1"},
                {"category": "crud", "name": "t2"},
                {"category": "auth", "name": "t3"},
            ]
        }
        m = _extract_step_metrics("dsl_test(generate)", data)
        assert m["total_tests"] == 3
        assert m["categories"] == {"crud": 2, "auth": 1}

    def test_test_coverage_metrics(self) -> None:
        data = {"overall_coverage": 0.6, "total_constructs": 10, "tested_constructs": 6}
        m = _extract_step_metrics("dsl_test(coverage)", data)
        assert m["overall_coverage"] == 0.6
        assert m["total_constructs"] == 10

    def test_story_coverage_metrics(self) -> None:
        data = {
            "total_stories": 5,
            "covered": 3,
            "partial": 1,
            "uncovered": 1,
            "coverage_percent": 70,
        }
        m = _extract_step_metrics("story(coverage)", data)
        assert m["total_stories"] == 5
        assert m["coverage_percent"] == 70

    def test_process_coverage_uses_same_extractor(self) -> None:
        data = {"total": 4, "covered": 2, "partial": 1, "uncovered": 1, "coverage": 50}
        m = _extract_step_metrics("process(coverage)", data)
        assert m["total_stories"] == 4
        assert m["coverage_percent"] == 50

    def test_test_design_gaps_metrics(self) -> None:
        data = {
            "coverage_score": 0.5,
            "gaps": [
                {"severity": "critical", "description": "g1"},
                {"severity": "minor", "description": "g2"},
                {"severity": "critical", "description": "g3"},
            ],
        }
        m = _extract_step_metrics("test_design(gaps)", data)
        assert m["gap_count"] == 3
        assert m["gaps_by_severity"] == {"critical": 2, "minor": 1}

    def test_semantics_extract_metrics(self) -> None:
        data = {
            "entity_count": 5,
            "command_count": 3,
            "event_count": 8,
            "tenancy_signal_count": 2,
            "compliance_signal_count": 5,
        }
        m = _extract_step_metrics("semantics(extract)", data)
        assert m == {
            "entity_count": 5,
            "command_count": 3,
            "event_count": 8,
            "tenancy_signal_count": 2,
            "compliance_signal_count": 5,
        }

    def test_semantics_validate_metrics(self) -> None:
        data = {"valid": True, "error_count": 0, "warning_count": 2}
        m = _extract_step_metrics("semantics(validate_events)", data)
        assert m == {"valid": True, "error_count": 0, "warning_count": 2}

    def test_run_all_metrics(self) -> None:
        data = {
            "total": 10,
            "passed": 8,
            "failed": 2,
            "results": [
                {"category": "crud", "status": "passed"},
                {"category": "crud", "status": "failed"},
                {"category": "auth", "status": "passed"},
            ],
        }
        m = _extract_step_metrics("dsl_test(run_all)", data)
        assert m["total"] == 10
        assert m["passed"] == 8
        assert m["by_category"]["crud"]["failed"] == 1

    def test_unknown_operation_returns_empty(self) -> None:
        assert _extract_step_metrics("unknown(op)", {"foo": 1}) == {}

    def test_non_dict_data_returns_empty(self) -> None:
        assert _extract_step_metrics("dsl(validate)", "not a dict") == {}

    def test_missing_keys_dont_crash(self) -> None:
        m = _extract_step_metrics("dsl(validate)", {})
        assert "status" in m  # returns defaults


# =============================================================================
# TestCollectTopIssues
# =============================================================================


class TestCollectTopIssues:
    """Unit tests for _collect_top_issues."""

    def test_collects_lint_errors(self) -> None:
        steps = [
            {
                "operation": "dsl(lint)",
                "status": "passed",
                "result": {"errors": ["bad import"], "warnings": []},
            },
        ]
        issues = _collect_top_issues(steps)
        assert len(issues) == 1
        assert issues[0]["source"] == "lint"
        assert issues[0]["severity"] == "error"

    def test_collects_lint_warnings(self) -> None:
        steps = [
            {
                "operation": "dsl(lint)",
                "status": "passed",
                "result": {"errors": [], "warnings": ["unused field"]},
            },
        ]
        issues = _collect_top_issues(steps)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"

    def test_collects_composition_violations(self) -> None:
        steps = [
            {
                "operation": "composition(audit)",
                "status": "passed",
                "result": {
                    "pages": [
                        {
                            "route": "/",
                            "page_violations": [
                                {"severity": "high", "message": "Missing hero section"},
                            ],
                            "sections": [
                                {
                                    "type": "hero",
                                    "violations": [
                                        {"severity": "medium", "message": "CTA weight too low"},
                                    ],
                                },
                            ],
                        },
                    ]
                },
            },
        ]
        issues = _collect_top_issues(steps)
        assert len(issues) == 2
        assert all(i["source"] == "composition" for i in issues)
        severities = {i["severity"] for i in issues}
        assert "high" in severities
        assert "medium" in severities

    def test_collects_fidelity_recommendations(self) -> None:
        steps = [
            {
                "operation": "dsl(fidelity)",
                "status": "passed",
                "result": {
                    "top_recommendations": [
                        {"severity": "major", "recommendation": "Add missing field title"},
                    ]
                },
            },
        ]
        issues = _collect_top_issues(steps)
        assert len(issues) == 1
        assert issues[0]["source"] == "fidelity"

    def test_collects_test_failures(self) -> None:
        steps = [
            {
                "operation": "dsl_test(run_all)",
                "status": "passed",
                "result": {
                    "results": [
                        {
                            "status": "failed",
                            "error": "404 on /api/tasks",
                            "name": "test_list_tasks",
                        },
                        {"status": "passed", "name": "test_create_task"},
                    ]
                },
            },
        ]
        issues = _collect_top_issues(steps)
        assert len(issues) == 1
        assert issues[0]["source"] == "test_failure"

    def test_collects_test_design_gaps(self) -> None:
        steps = [
            {
                "operation": "test_design(gaps)",
                "status": "passed",
                "result": {
                    "gaps": [
                        {
                            "severity": "critical",
                            "description": "No negative test for Task deletion",
                        },
                    ]
                },
            },
        ]
        issues = _collect_top_issues(steps)
        assert len(issues) == 1
        assert issues[0]["source"] == "test_design"
        assert issues[0]["severity"] == "critical"

    def test_severity_ordering(self) -> None:
        steps = [
            {
                "operation": "dsl(lint)",
                "status": "passed",
                "result": {"errors": [], "warnings": ["minor warning"]},
            },
            {
                "operation": "test_design(gaps)",
                "status": "passed",
                "result": {"gaps": [{"severity": "critical", "description": "critical gap"}]},
            },
        ]
        issues = _collect_top_issues(steps)
        assert issues[0]["severity"] == "critical"
        assert issues[1]["severity"] == "warning"

    def test_max_issues_cap(self) -> None:
        steps = [
            {
                "operation": "dsl(lint)",
                "status": "passed",
                "result": {"errors": [f"err{i}" for i in range(10)], "warnings": []},
            },
        ]
        issues = _collect_top_issues(steps, max_issues=3)
        assert len(issues) == 3

    def test_empty_steps(self) -> None:
        assert _collect_top_issues([]) == []

    def test_steps_without_results(self) -> None:
        steps = [
            {"operation": "dsl(validate)", "status": "error", "error": "parse failed"},
            {"operation": "semantics(extract)", "status": "skipped", "reason": "not available"},
        ]
        assert _collect_top_issues(steps) == []


# =============================================================================
# TestBuildPipelineResponse (directly test the response builder)
# =============================================================================


def _make_passed_step(step: int, operation: str, result: dict[str, Any]) -> dict[str, Any]:
    """Helper to build a passed step dict."""
    return {
        "step": step,
        "operation": operation,
        "status": "passed",
        "duration_ms": 10.0,
        "result": result,
    }


def _make_error_step(step: int, operation: str, error: str) -> dict[str, Any]:
    return {
        "step": step,
        "operation": operation,
        "status": "error",
        "duration_ms": 5.0,
        "error": error,
    }


def _make_skipped_step(step: int, operation: str, reason: str) -> dict[str, Any]:
    return {
        "step": step,
        "operation": operation,
        "status": "skipped",
        "reason": reason,
    }


class TestBuildPipelineResponse:
    """Tests for _build_pipeline_response summary vs full mode."""

    def _sample_steps(self) -> list[dict[str, Any]]:
        return [
            _make_passed_step(
                1,
                "dsl(validate)",
                {
                    "status": "valid",
                    "module_count": 1,
                    "entity_count": 3,
                    "surface_count": 2,
                },
            ),
            _make_passed_step(
                2,
                "dsl(lint)",
                {
                    "errors": ["lint err"],
                    "warnings": ["lint warn"],
                },
            ),
            _make_passed_step(
                3,
                "dsl(fidelity)",
                {
                    "overall_fidelity": 0.85,
                    "total_gaps": 2,
                    "story_coverage": 0.7,
                    "surfaces": [{"surface": "s1"}],
                    "top_recommendations": [{"severity": "major", "recommendation": "fix field"}],
                },
            ),
            _make_error_step(4, "dsl_test(generate)", "generator crashed"),
            _make_skipped_step(5, "semantics(extract)", "not available"),
        ]

    def test_summary_true_has_metrics_not_result(self) -> None:
        steps = self._sample_steps()
        start = time.monotonic()
        raw = _build_pipeline_response(steps, [], start, summary=True)
        data = json.loads(raw)

        assert "top_issues" in data
        for step in data["steps"]:
            assert "result" not in step
            if step["status"] == "passed":
                assert "metrics" in step

    def test_summary_false_has_result_not_metrics(self) -> None:
        steps = self._sample_steps()
        start = time.monotonic()
        raw = _build_pipeline_response(steps, [], start, summary=False)
        data = json.loads(raw)

        assert "top_issues" not in data
        for step in data["steps"]:
            if step["status"] == "passed":
                assert "result" in step
                assert "metrics" not in step

    def test_error_step_preserved_in_summary(self) -> None:
        steps = self._sample_steps()
        start = time.monotonic()
        raw = _build_pipeline_response(
            steps, ["dsl_test(generate): generator crashed"], start, summary=True
        )
        data = json.loads(raw)

        error_steps = [s for s in data["steps"] if s["status"] == "error"]
        assert len(error_steps) == 1
        assert "error" in error_steps[0]
        assert data["status"] == "failed"
        assert "errors" in data

    def test_skipped_step_preserved_in_summary(self) -> None:
        steps = self._sample_steps()
        start = time.monotonic()
        raw = _build_pipeline_response(steps, [], start, summary=True)
        data = json.loads(raw)

        skipped = [s for s in data["steps"] if s["status"] == "skipped"]
        assert len(skipped) == 1
        assert "reason" in skipped[0]

    def test_summary_counts(self) -> None:
        steps = self._sample_steps()
        start = time.monotonic()
        raw = _build_pipeline_response(steps, [], start, summary=True)
        data = json.loads(raw)

        assert data["summary"]["total_steps"] == 5
        assert data["summary"]["passed"] == 3
        assert data["summary"]["failed"] == 1
        assert data["summary"]["skipped"] == 1

    def test_duration_ms_in_summary(self) -> None:
        steps = self._sample_steps()
        start = time.monotonic()
        raw = _build_pipeline_response(steps, [], start, summary=True)
        data = json.loads(raw)

        for step in data["steps"]:
            if step["status"] != "skipped":
                assert "duration_ms" in step

    def test_top_issues_from_lint_and_fidelity(self) -> None:
        steps = self._sample_steps()
        start = time.monotonic()
        raw = _build_pipeline_response(steps, [], start, summary=True)
        data = json.loads(raw)

        sources = {i["source"] for i in data["top_issues"]}
        assert "lint" in sources
        assert "fidelity" in sources

    def test_summary_is_compact(self) -> None:
        steps = self._sample_steps()
        start = time.monotonic()
        summary_raw = _build_pipeline_response(steps, [], start, summary=True)
        full_raw = _build_pipeline_response(steps, [], start, summary=False)

        # Summary should generally be smaller (no full result payloads)
        # Allow margin for top_issues key
        assert len(summary_raw) <= len(full_raw) + 500


# =============================================================================
# TestPipelineSummaryIntegration
# =============================================================================


class TestPipelineSummaryIntegration:
    """Integration tests for run_pipeline_handler with all handlers mocked."""

    def _make_mock_module(self, func_name: str, return_data: dict[str, Any]) -> MagicMock:
        """Create a mock module with a function that returns JSON."""
        mock_mod = MagicMock()
        getattr(mock_mod, func_name).return_value = json.dumps(return_data)
        return mock_mod

    def _run_with_mocks(self, tmp_path: Path, args: dict[str, Any]) -> dict[str, Any]:
        """Run pipeline handler with all sub-handlers mocked."""
        # Mock the handler modules that pipeline imports from
        mock_dsl = MagicMock()
        mock_dsl.validate_dsl.return_value = json.dumps(
            {"status": "valid", "module_count": 1, "entity_count": 2, "surface_count": 1}
        )
        mock_dsl.lint_project.return_value = json.dumps({"errors": [], "warnings": ["unused"]})

        mock_fidelity = MagicMock()
        mock_fidelity.score_fidelity_handler.return_value = json.dumps(
            {
                "overall_fidelity": 0.9,
                "total_gaps": 0,
                "story_coverage": 0.8,
                "surfaces": [],
                "top_recommendations": [],
            }
        )

        mock_composition = MagicMock()
        mock_composition.audit_composition_handler.return_value = json.dumps(
            {
                "pages": [{"route": "/", "score": 100, "violations_count": {}}],
                "overall_score": 100,
                "summary": "1 page audited",
            }
        )

        mock_dsl_test = MagicMock()
        mock_dsl_test.generate_dsl_tests_handler.return_value = json.dumps(
            {"tests": [], "total_tests": 0}
        )
        mock_dsl_test.get_dsl_test_coverage_handler.return_value = json.dumps(
            {"overall_coverage": 1.0, "total_constructs": 5, "tested_constructs": 5}
        )

        mock_process = MagicMock()
        mock_process.stories_coverage_handler.return_value = json.dumps(
            {
                "total_stories": 2,
                "covered": 2,
                "partial": 0,
                "uncovered": 0,
                "coverage_percent": 100,
            }
        )

        mock_test_design = MagicMock()
        mock_test_design.get_test_gaps_handler.return_value = json.dumps(
            {"coverage_score": 0.9, "gaps": []}
        )

        handler_mods = {
            "dazzle.mcp.server.handlers.dsl": mock_dsl,
            "dazzle.mcp.server.handlers.fidelity": mock_fidelity,
            "dazzle.mcp.server.handlers.composition": mock_composition,
            "dazzle.mcp.server.handlers.dsl_test": mock_dsl_test,
            "dazzle.mcp.server.handlers.process": mock_process,
            "dazzle.mcp.server.handlers.test_design": mock_test_design,
            "dazzle.mcp.event_first_tools": None,  # triggers skipped steps
        }

        with patch.dict(sys.modules, handler_mods):
            # Re-import to pick up mocked modules
            pipeline_mod = _import_pipeline()
            raw = pipeline_mod.run_pipeline_handler(tmp_path, args)

        return json.loads(raw)

    def test_default_summary_mode(self, tmp_path: Path) -> None:
        data = self._run_with_mocks(tmp_path, {})
        assert data["status"] == "passed"
        assert "top_issues" in data
        for step in data["steps"]:
            assert "result" not in step

    def test_full_detail_mode(self, tmp_path: Path) -> None:
        data = self._run_with_mocks(tmp_path, {"summary": False})
        assert "top_issues" not in data
        passed = [s for s in data["steps"] if s["status"] == "passed"]
        assert all("result" in s for s in passed)

    def test_stop_on_error_with_summary(self, tmp_path: Path) -> None:
        mock_dsl = MagicMock()
        mock_dsl.validate_dsl.return_value = json.dumps({"error": "parse failure"})

        handler_mods = {
            "dazzle.mcp.server.handlers.dsl": mock_dsl,
            "dazzle.mcp.event_first_tools": None,
        }
        with patch.dict(sys.modules, handler_mods):
            pipeline_mod = _import_pipeline()
            raw = pipeline_mod.run_pipeline_handler(tmp_path, {"stop_on_error": True})

        data = json.loads(raw)
        assert data["status"] == "failed"
        assert len(data["steps"]) == 1
        assert "top_issues" in data


# =============================================================================
# TestFidelityGapsOnly
# =============================================================================


class TestFidelityGapsOnly:
    """Tests for gaps_only parameter in fidelity handler."""

    def _import_fidelity_fresh(self) -> Any:
        """Import fidelity handlers directly."""
        sys.modules.setdefault("dazzle.mcp.server.handlers", MagicMock(pytest_plugins=[]))
        module_path = (
            Path(__file__).parent.parent.parent.parent
            / "src"
            / "dazzle"
            / "mcp"
            / "server"
            / "handlers"
            / "fidelity.py"
        )
        spec = importlib.util.spec_from_file_location(
            "dazzle.mcp.server.handlers.fidelity",
            module_path,
            submodule_search_locations=[],
        )
        module = importlib.util.module_from_spec(spec)
        module.__package__ = "dazzle.mcp.server.handlers"
        sys.modules["dazzle.mcp.server.handlers.fidelity"] = module
        spec.loader.exec_module(module)
        return module

    def _make_fidelity_report(self, surfaces: list[dict[str, Any]]) -> Any:
        scores = []
        for s in surfaces:
            scores.append(
                SimpleNamespace(
                    surface_name=s["name"],
                    structural=s.get("overall", 1.0),
                    semantic=s.get("overall", 1.0),
                    story=s.get("overall", 1.0),
                    overall=s["overall"],
                    gaps=[],
                )
            )
        return SimpleNamespace(
            overall=sum(s["overall"] for s in surfaces) / len(surfaces) if surfaces else 1.0,
            story_coverage=0.8,
            total_gaps=sum(1 for s in surfaces if s["overall"] < 1.0),
            gap_counts={},
            surface_scores=scores,
        )

    def _run_fidelity_with_mocks(
        self, tmp_path: Path, arguments: dict[str, Any], surfaces: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Run fidelity handler with all dependencies mocked."""
        report = self._make_fidelity_report(surfaces)

        # Build mock modules for all fidelity handler imports
        mock_fidelity_scorer = MagicMock()
        mock_fidelity_scorer.score_appspec_fidelity.return_value = report

        mock_fileset = MagicMock()
        mock_fileset.discover_dsl_files.return_value = []

        mock_linker = MagicMock()

        mock_manifest_mod = MagicMock()

        mock_parser = MagicMock()

        mock_lint = MagicMock()
        mock_lint.lint_appspec.return_value = ([], [])

        mock_compiler = MagicMock()
        # Build page contexts from surfaces
        page_contexts = {}
        for s in surfaces:
            ctx = MagicMock()
            ctx.view_name = s["name"]
            page_contexts[f"/{s['name']}"] = ctx
        mock_compiler.compile_appspec_to_templates.return_value = page_contexts

        mock_renderer = MagicMock()
        mock_renderer.render_page.return_value = "<html></html>"

        mods = {
            "dazzle.core.fidelity_scorer": mock_fidelity_scorer,
            "dazzle.core.fileset": mock_fileset,
            "dazzle.core.linker": mock_linker,
            "dazzle.core.manifest": mock_manifest_mod,
            "dazzle.core.parser": mock_parser,
            "dazzle.core.lint": mock_lint,
            "dazzle_ui": MagicMock(),
            "dazzle_ui.converters": MagicMock(),
            "dazzle_ui.converters.template_compiler": mock_compiler,
            "dazzle_ui.runtime": MagicMock(),
            "dazzle_ui.runtime.template_renderer": mock_renderer,
        }

        with patch.dict(sys.modules, mods):
            fi = self._import_fidelity_fresh()
            raw = fi.score_fidelity_handler(tmp_path, arguments)

        return json.loads(raw)

    def test_gaps_only_filters_perfect_surfaces(self, tmp_path: Path) -> None:
        surfaces = [
            {"name": "task_list", "overall": 0.7},
            {"name": "user_list", "overall": 1.0},
        ]
        data = self._run_fidelity_with_mocks(tmp_path, {"gaps_only": True}, surfaces)

        surface_names = [s["surface"] for s in data["surfaces"]]
        assert "task_list" in surface_names
        assert "user_list" not in surface_names

    def test_gaps_only_false_keeps_all(self, tmp_path: Path) -> None:
        surfaces = [
            {"name": "task_list", "overall": 0.7},
            {"name": "user_list", "overall": 1.0},
        ]
        data = self._run_fidelity_with_mocks(tmp_path, {"gaps_only": False}, surfaces)

        surface_names = [s["surface"] for s in data["surfaces"]]
        assert "task_list" in surface_names
        assert "user_list" in surface_names

    def test_gaps_only_default_is_false(self, tmp_path: Path) -> None:
        surfaces = [
            {"name": "task_list", "overall": 1.0},
        ]
        data = self._run_fidelity_with_mocks(tmp_path, {}, surfaces)
        assert len(data["surfaces"]) == 1
