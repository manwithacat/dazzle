"""Tests for pipeline adaptive detail levels and _meta block."""

from __future__ import annotations

import json
import time

from dazzle.mcp.server.handlers.pipeline import (
    _build_pipeline_response,
    _filter_issues_result,
    _step_has_issues,
)


class TestStepHasIssues:
    """Tests for _step_has_issues helper."""

    def test_lint_with_errors(self):
        assert _step_has_issues("dsl(lint)", {"errors": ["bad"], "warnings": []}) is True

    def test_lint_with_warnings_only(self):
        # Warnings alone are baseline noise — don't expand
        assert _step_has_issues("dsl(lint)", {"errors": [], "warnings": ["hmm"]}) is False

    def test_lint_with_errors_and_warnings(self):
        # Errors trigger expansion even when warnings are also present
        assert _step_has_issues("dsl(lint)", {"errors": ["bad"], "warnings": ["hmm"]}) is True

    def test_lint_clean(self):
        assert _step_has_issues("dsl(lint)", {"errors": [], "warnings": []}) is False

    def test_fidelity_with_gaps(self):
        assert _step_has_issues("dsl(fidelity)", {"total_gaps": 3}) is True

    def test_fidelity_no_gaps(self):
        assert _step_has_issues("dsl(fidelity)", {"total_gaps": 0}) is False

    def test_composition_low_score(self):
        assert _step_has_issues("composition(audit)", {"overall_score": 85}) is True

    def test_composition_perfect(self):
        assert _step_has_issues("composition(audit)", {"overall_score": 100}) is False

    def test_test_run_failures(self):
        assert _step_has_issues("dsl_test(run_all)", {"failed": 2}) is True

    def test_test_run_all_passed(self):
        assert _step_has_issues("dsl_test(run_all)", {"failed": 0}) is False

    def test_semantics_with_errors(self):
        assert (
            _step_has_issues("semantics(validate_events)", {"error_count": 1, "warning_count": 0})
            is True
        )

    def test_semantics_clean(self):
        assert (
            _step_has_issues("semantics(validate_events)", {"error_count": 0, "warning_count": 0})
            is False
        )

    def test_non_dict_result(self):
        assert _step_has_issues("dsl(lint)", "some string") is False

    def test_unknown_operation(self):
        assert _step_has_issues("unknown_op", {"stuff": True}) is False

    def test_test_design_gaps(self):
        assert _step_has_issues("test_design(gaps)", {"gaps": [{"desc": "missing"}]}) is True

    def test_test_design_no_gaps(self):
        assert _step_has_issues("test_design(gaps)", {"gaps": []}) is False

    def test_coverage_below_100(self):
        assert _step_has_issues("dsl_test(coverage)", {"coverage_percent": 80}) is True

    def test_coverage_at_100(self):
        assert _step_has_issues("dsl_test(coverage)", {"coverage_percent": 100}) is False

    def test_coverage_string_percent(self):
        assert _step_has_issues("story(coverage)", {"coverage_percent": "75%"}) is True


class TestFilterIssuesResult:
    """Tests for _filter_issues_result trimming."""

    def test_story_coverage_keeps_only_partial_and_uncovered(self):
        result = {
            "total_stories": 50,
            "covered": 47,
            "partial": 2,
            "uncovered": 1,
            "coverage_percent": 94.0,
            "showing": 50,
            "offset": 0,
            "has_more": False,
            "guidance": "Use offset=50 for next page",
            "stories": [
                {"story_id": "ST-001", "status": "covered", "title": "Good story"},
                {"story_id": "ST-002", "status": "partial", "title": "Half done"},
                {"story_id": "ST-003", "status": "uncovered", "title": "Not started"},
                {"story_id": "ST-004", "status": "covered", "title": "Another good one"},
            ],
        }
        filtered = _filter_issues_result("story(coverage)", result)
        assert len(filtered["stories"]) == 2
        assert filtered["stories"][0]["story_id"] == "ST-002"
        assert filtered["stories"][1]["story_id"] == "ST-003"
        # Pagination fields stripped
        assert "showing" not in filtered
        assert "offset" not in filtered
        assert "has_more" not in filtered
        assert "guidance" not in filtered
        # Aggregate metrics preserved
        assert filtered["total_stories"] == 50
        assert filtered["coverage_percent"] == 94.0

    def test_process_coverage_same_as_story(self):
        result = {
            "total_stories": 10,
            "stories": [
                {"story_id": "ST-001", "status": "covered"},
                {"story_id": "ST-002", "status": "partial"},
            ],
        }
        filtered = _filter_issues_result("process(coverage)", result)
        assert len(filtered["stories"]) == 1
        assert filtered["stories"][0]["story_id"] == "ST-002"

    def test_composition_audit_strips_markdown(self):
        result = {
            "pages": [{"route": "/", "score": 85}],
            "overall_score": 85,
            "summary": "1 page audited",
            "markdown": "# Composition Audit: 85/100\n...",
        }
        filtered = _filter_issues_result("composition(audit)", result)
        assert "markdown" not in filtered
        assert filtered["overall_score"] == 85
        assert filtered["pages"] == [{"route": "/", "score": 85}]

    def test_unknown_operation_passes_through(self):
        result = {"some": "data"}
        assert _filter_issues_result("dsl(validate)", result) is result

    def test_non_dict_passes_through(self):
        assert _filter_issues_result("story(coverage)", "not a dict") == "not a dict"


class TestBuildPipelineResponse:
    """Tests for _build_pipeline_response with detail levels."""

    def _make_steps(self):
        """Create sample steps with a mix of clean and problematic results."""
        return [
            {
                "step": 1,
                "operation": "dsl(validate)",
                "status": "passed",
                "duration_ms": 50.0,
                "result": {
                    "status": "valid",
                    "modules": 1,
                    "entities": 3,
                    "surfaces": 2,
                },
            },
            {
                "step": 2,
                "operation": "dsl(lint)",
                "status": "passed",
                "duration_ms": 30.0,
                "result": {
                    "errors": ["Missing field description"],
                    "warnings": ["Unused entity"],
                },
            },
            {
                "step": 3,
                "operation": "dsl(fidelity)",
                "status": "passed",
                "duration_ms": 20.0,
                "result": {"total_gaps": 0, "overall_fidelity": 1.0},
            },
        ]

    def test_metrics_mode_returns_compact(self):
        steps = self._make_steps()
        start = time.monotonic() - 0.1
        raw = _build_pipeline_response(steps, [], start, detail="metrics")
        data = json.loads(raw)
        # All steps should have metrics, not full results
        for step in data["steps"]:
            assert "result" not in step
            if step["status"] == "passed":
                assert "metrics" in step or step.get("operation") == "dsl(lint)"
        assert "top_issues" in data

    def test_issues_mode_expands_problematic_steps(self):
        steps = self._make_steps()
        start = time.monotonic() - 0.1
        raw = _build_pipeline_response(steps, [], start, detail="issues")
        data = json.loads(raw)
        # Step 1 (validate, clean) should have metrics
        assert "metrics" in data["steps"][0]
        assert "result" not in data["steps"][0]
        # Step 2 (lint with errors) should have full result
        assert "result" in data["steps"][1]
        # Step 3 (fidelity, clean) should have metrics
        assert "metrics" in data["steps"][2]
        assert "result" not in data["steps"][2]

    def test_full_mode_returns_everything(self):
        steps = self._make_steps()
        start = time.monotonic() - 0.1
        raw = _build_pipeline_response(steps, [], start, detail="full")
        data = json.loads(raw)
        # All steps should have their original results
        for step in data["steps"]:
            assert "result" in step
        # No top_issues in full mode
        assert "top_issues" not in data

    def test_meta_block_present(self):
        steps = self._make_steps()
        start = time.monotonic() - 0.1
        raw = _build_pipeline_response(steps, [], start, detail="issues")
        data = json.loads(raw)
        assert "_meta" in data
        meta = data["_meta"]
        assert "wall_time_ms" in meta
        assert meta["steps_executed"] == 3
        assert meta["detail_level"] == "issues"

    def test_meta_block_in_full_mode(self):
        steps = self._make_steps()
        start = time.monotonic() - 0.1
        raw = _build_pipeline_response(steps, [], start, detail="full")
        data = json.loads(raw)
        assert "_meta" in data
        assert data["_meta"]["detail_level"] == "full"

    def test_meta_block_in_metrics_mode(self):
        steps = self._make_steps()
        start = time.monotonic() - 0.1
        raw = _build_pipeline_response(steps, [], start, detail="metrics")
        data = json.loads(raw)
        assert "_meta" in data
        assert data["_meta"]["detail_level"] == "metrics"

    def test_backward_compat_summary_true(self):
        """summary=True should map to detail='metrics' behavior."""
        # This tests that the mapping in run_pipeline_handler works
        # We test the response builder directly with metrics
        steps = self._make_steps()
        start = time.monotonic() - 0.1
        raw = _build_pipeline_response(steps, [], start, detail="metrics")
        data = json.loads(raw)
        assert "top_issues" in data  # metrics mode includes top_issues

    def test_error_steps_always_show_error(self):
        steps = [
            {
                "step": 1,
                "operation": "dsl(validate)",
                "status": "error",
                "duration_ms": 10.0,
                "error": "Parse error",
            }
        ]
        start = time.monotonic() - 0.1
        for detail in ("metrics", "issues", "full"):
            raw = _build_pipeline_response(
                steps, ["dsl(validate): Parse error"], start, detail=detail
            )
            data = json.loads(raw)
            assert data["steps"][0]["error"] == "Parse error"
            assert data["status"] == "failed"

    def test_errors_included(self):
        steps = self._make_steps()
        start = time.monotonic() - 0.1
        raw = _build_pipeline_response(steps, ["some error"], start, detail="issues")
        data = json.loads(raw)
        assert "errors" in data
        assert data["errors"] == ["some error"]

    def test_skipped_steps_show_reason(self):
        steps = [
            {
                "step": 1,
                "operation": "semantics(extract)",
                "status": "skipped",
                "reason": "event_first_tools not available",
            }
        ]
        start = time.monotonic() - 0.1
        for detail in ("metrics", "issues"):
            raw = _build_pipeline_response(steps, [], start, detail=detail)
            data = json.loads(raw)
            assert data["steps"][0]["reason"] == "event_first_tools not available"
