"""Tests for failure_classifier.classify_failure."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


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
    """Test each failure type classification."""

    def test_rbac_denied_401(self) -> None:
        result = classify_failure("CRUD_Task_create", "crud", "Got 401 Unauthorized")
        assert result == "rbac_denied"

    def test_rbac_denied_403(self) -> None:
        result = classify_failure("CRUD_Task_create", "crud", "403 Forbidden response")
        assert result == "rbac_denied"

    def test_rbac_denied_permission(self) -> None:
        result = classify_failure("ACL_admin", "persona", "Permission denied for role")
        assert result == "rbac_denied"

    def test_validation_error_required(self) -> None:
        result = classify_failure("CRUD_Task_create", "crud", "Field 'title' is required")
        assert result == "validation_error"

    def test_validation_error_422(self) -> None:
        result = classify_failure("CRUD_Task_create", "crud", "422 Unprocessable Entity")
        assert result == "validation_error"

    def test_dsl_surface_gap_404(self) -> None:
        result = classify_failure("CRUD_Widget_list", "crud", "404 Not Found for /api/widgets")
        assert result == "dsl_surface_gap"

    def test_dsl_surface_gap_no_surface(self) -> None:
        result = classify_failure("WS_main", "workspace", "No surface found for widget_list")
        assert result == "dsl_surface_gap"

    def test_state_machine_transition(self) -> None:
        result = classify_failure(
            "CRUD_Task_update", "crud", "Invalid transition from draft to published"
        )
        assert result == "state_machine"

    def test_state_machine_prefix(self) -> None:
        result = classify_failure("SM_Task_approve", "state_machine", "Some error")
        assert result == "state_machine"

    def test_timeout(self) -> None:
        result = classify_failure("CRUD_Task_create", "crud", "Request timed out after 30s")
        assert result == "timeout"

    def test_framework_bug_500(self) -> None:
        result = classify_failure("CRUD_Task_create", "crud", "500 Internal Server Error")
        assert result == "framework_bug"

    def test_framework_bug_connection(self) -> None:
        result = classify_failure("CRUD_Task_create", "crud", "Connection refused on port 8000")
        assert result == "framework_bug"

    def test_unknown_fallback(self) -> None:
        result = classify_failure("CRUD_Task_create", "crud", "Something unexpected happened")
        assert result == "unknown"

    def test_none_error_message(self) -> None:
        result = classify_failure("CRUD_Task_create", "crud", None)
        assert result == "unknown"

    def test_failed_step_contributes(self) -> None:
        """Failed step message should also be checked."""
        result = classify_failure(
            "CRUD_Task_create",
            "crud",
            "Test failed",
            failed_step={"action": "click", "target": "submit", "message": "Got 403 error"},
        )
        assert result == "rbac_denied"
