"""Tests for failure_classifier.classify_failure."""

import importlib.util
import sys
from pathlib import Path

import pytest


def _import_classifier():
    """Import failure_classifier directly to avoid MCP package init issues."""
    module_path = (
        Path(__file__).parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "knowledge_graph"
        / "failure_classifier.py"
    )
    spec = importlib.util.spec_from_file_location(
        "dazzle.mcp.knowledge_graph.failure_classifier",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["dazzle.mcp.knowledge_graph.failure_classifier"] = module
    spec.loader.exec_module(module)
    return module


_classifier = _import_classifier()
classify_failure = _classifier.classify_failure


class TestClassifyFailure:
    """Test each failure type classification.

    Each (test_name, persona, error_msg) tuple → expected category. The
    classifier reads the message, persona, and step context to bucket
    failures into actionable categories for the QA report.
    """

    @pytest.mark.parametrize(
        ("test_name", "persona", "error_msg", "expected"),
        [
            # rbac_denied: HTTP 401/403 + permission-denied phrases
            ("CRUD_Task_create", "crud", "Got 401 Unauthorized", "rbac_denied"),
            ("CRUD_Task_create", "crud", "403 Forbidden response", "rbac_denied"),
            ("ACL_admin", "persona", "Permission denied for role", "rbac_denied"),
            # validation_error: 422 + required-field phrases
            ("CRUD_Task_create", "crud", "Field 'title' is required", "validation_error"),
            ("CRUD_Task_create", "crud", "422 Unprocessable Entity", "validation_error"),
            # dsl_surface_gap: 404 + missing-surface phrases
            ("CRUD_Widget_list", "crud", "404 Not Found for /api/widgets", "dsl_surface_gap"),
            ("WS_main", "workspace", "No surface found for widget_list", "dsl_surface_gap"),
            # state_machine: explicit transition error OR SM_ test prefix
            (
                "CRUD_Task_update",
                "crud",
                "Invalid transition from draft to published",
                "state_machine",
            ),
            ("SM_Task_approve", "state_machine", "Some error", "state_machine"),
            # timeout
            ("CRUD_Task_create", "crud", "Request timed out after 30s", "timeout"),
            # framework_bug: 500 / connection refused
            ("CRUD_Task_create", "crud", "500 Internal Server Error", "framework_bug"),
            ("CRUD_Task_create", "crud", "Connection refused on port 8000", "framework_bug"),
            # unknown: fallback
            ("CRUD_Task_create", "crud", "Something unexpected happened", "unknown"),
            ("CRUD_Task_create", "crud", None, "unknown"),
        ],
        ids=[
            "rbac_denied_401",
            "rbac_denied_403",
            "rbac_denied_permission",
            "validation_error_required",
            "validation_error_422",
            "dsl_surface_gap_404",
            "dsl_surface_gap_no_surface",
            "state_machine_transition",
            "state_machine_prefix",
            "timeout",
            "framework_bug_500",
            "framework_bug_connection",
            "unknown_fallback",
            "none_error_message",
        ],
    )
    def test_classify(self, test_name, persona, error_msg, expected) -> None:
        assert classify_failure(test_name, persona, error_msg) == expected

    def test_failed_step_contributes(self) -> None:
        """Failed-step message is consulted in addition to the test-level error."""
        result = classify_failure(
            "CRUD_Task_create",
            "crud",
            "Test failed",
            failed_step={"action": "click", "target": "submit", "message": "Got 403 error"},
        )
        assert result == "rbac_denied"
