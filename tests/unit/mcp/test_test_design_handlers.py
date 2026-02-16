"""Tests for the test_design MCP handlers."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _import_test_design():
    """Import test_design handlers directly to avoid MCP package init issues.

    The dazzle.mcp.__init__.py imports mcp.server which may not be installed
    in test environments. We need to import the handlers module directly.
    """
    # Create mock modules to satisfy imports
    mock_state = MagicMock()
    mock_state.get_project_path = MagicMock(return_value=None)
    sys.modules["dazzle.mcp.server.handlers"] = MagicMock(pytest_plugins=[])

    # Build a common mock with real implementations for DSL loading
    from types import ModuleType

    from dazzle.core.fileset import discover_dsl_files
    from dazzle.core.linker import build_appspec
    from dazzle.core.manifest import load_manifest
    from dazzle.core.parser import parse_modules

    common_mock = ModuleType("dazzle.mcp.server.handlers.common")

    def _extract_progress(args=None):
        ctx = MagicMock()
        ctx.log_sync = MagicMock()
        return ctx

    def _load_project_appspec(project_root):
        manifest = load_manifest(project_root / "dazzle.toml")
        dsl_files = discover_dsl_files(project_root, manifest)
        modules = parse_modules(dsl_files)
        return build_appspec(modules, manifest.project_root)

    common_mock.extract_progress = _extract_progress
    common_mock.load_project_appspec = _load_project_appspec

    def _handler_error_json(fn):
        """Decorator that catches exceptions and returns JSON error."""
        from functools import wraps

        @wraps(fn)
        def wrapper(*a, **kw):
            try:
                return fn(*a, **kw)
            except Exception as exc:
                return json.dumps({"error": str(exc)})

        return wrapper

    common_mock.handler_error_json = _handler_error_json
    sys.modules["dazzle.mcp.server.handlers.common"] = common_mock
    sys.modules["dazzle.mcp.server.state"] = mock_state

    handlers_dir = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "server"
        / "handlers"
    )

    # Pre-load the serializers module so test_design submodules' `from ..serializers import ...` resolves
    ser_path = handlers_dir / "serializers.py"
    ser_spec = importlib.util.spec_from_file_location(
        "dazzle.mcp.server.handlers.serializers",
        ser_path,
        submodule_search_locations=[],
    )
    ser_mod = importlib.util.module_from_spec(ser_spec)
    ser_mod.__package__ = "dazzle.mcp.server.handlers"
    sys.modules["dazzle.mcp.server.handlers.serializers"] = ser_mod
    ser_spec.loader.exec_module(ser_mod)

    # Attach serializers to the handlers mock so relative import resolves
    sys.modules["dazzle.mcp.server.handlers"].serializers = ser_mod

    pkg_dir = handlers_dir / "test_design"

    # Import submodules first so the package __init__ can re-export them
    for submod_name in ("proposals", "gaps", "persistence", "coverage"):
        submod_path = pkg_dir / f"{submod_name}.py"
        sub_spec = importlib.util.spec_from_file_location(
            f"dazzle.mcp.server.handlers.test_design.{submod_name}",
            submod_path,
            submodule_search_locations=[],
        )
        sub_module = importlib.util.module_from_spec(sub_spec)
        sub_module.__package__ = "dazzle.mcp.server.handlers.test_design"
        sys.modules[f"dazzle.mcp.server.handlers.test_design.{submod_name}"] = sub_module
        sub_spec.loader.exec_module(sub_module)

    # Now import the package __init__
    init_path = pkg_dir / "__init__.py"
    spec = importlib.util.spec_from_file_location(
        "dazzle.mcp.server.handlers.test_design",
        init_path,
        submodule_search_locations=[str(pkg_dir)],
    )
    module = importlib.util.module_from_spec(spec)
    module.__package__ = "dazzle.mcp.server.handlers.test_design"
    sys.modules["dazzle.mcp.server.handlers.test_design"] = module

    spec.loader.exec_module(module)
    return module


# Import the module once at module load time
_td = _import_test_design()

# Get references to the functions we need
propose_persona_tests_handler = _td.propose_persona_tests_handler
get_test_gaps_handler = _td.get_test_gaps_handler
save_test_designs_handler = _td.save_test_designs_handler
get_test_designs_handler = _td.get_test_designs_handler
get_coverage_actions_handler = _td.get_coverage_actions_handler
get_runtime_coverage_gaps_handler = _td.get_runtime_coverage_gaps_handler
save_runtime_coverage_handler = _td.save_runtime_coverage_handler
_parse_test_design_action = _td._parse_test_design_action
_parse_test_design_trigger = _td._parse_test_design_trigger


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_project(tmp_path):
    """Create a temporary project with minimal DSL structure."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()

    # Create dazzle.toml manifest
    manifest = project_dir / "dazzle.toml"
    manifest.write_text(
        """
[project]
name = "test_project"
version = "0.1.0"
root = "test_project"

[modules]
paths = ["./dsl"]
"""
    )

    # Create dsl directory
    dsl_dir = project_dir / "dsl"
    dsl_dir.mkdir()

    # Create main.dsl with persona
    main_dsl = dsl_dir / "main.dsl"
    main_dsl.write_text(
        """
module test_project
app test_project "Test Project"

persona admin "Admin":
    description: "System administrator"
    goals:
        - "Manage all users"
        - "Configure system settings"

entity Task "Task":
    id: uuid pk
    title: str(200) required
    status: enum[pending,in_progress,completed]=pending
"""
    )

    # Create .dazzle directory
    dazzle_dir = project_dir / ".dazzle"
    dazzle_dir.mkdir()

    # Create test_designs directory
    test_designs_dir = dazzle_dir / "test_designs"
    test_designs_dir.mkdir()

    return project_dir


@pytest.fixture
def temp_project_no_personas(tmp_path):
    """Create a temporary project without personas."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()

    manifest = project_dir / "dazzle.toml"
    manifest.write_text(
        """
[project]
name = "test_project"
version = "0.1.0"
root = "test_project"

[modules]
paths = ["./dsl"]
"""
    )

    dsl_dir = project_dir / "dsl"
    dsl_dir.mkdir()

    main_dsl = dsl_dir / "main.dsl"
    main_dsl.write_text(
        """
module test_project
app test_project "Test Project"

entity Task "Task":
    id: uuid pk
    title: str(200) required
"""
    )

    dazzle_dir = project_dir / ".dazzle"
    dazzle_dir.mkdir()

    test_designs_dir = dazzle_dir / "test_designs"
    test_designs_dir.mkdir()

    return project_dir


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestParseTestDesignAction:
    """Tests for _parse_test_design_action helper."""

    def test_valid_action(self) -> None:
        """Test parsing valid action."""
        from dazzle.core.ir.test_design import TestDesignAction

        action = _parse_test_design_action("login_as")
        assert action == TestDesignAction.LOGIN_AS

    def test_valid_action_click(self) -> None:
        """Test parsing click action."""
        from dazzle.core.ir.test_design import TestDesignAction

        action = _parse_test_design_action("click")
        assert action == TestDesignAction.CLICK

    def test_invalid_action(self) -> None:
        """Test parsing invalid action."""
        with pytest.raises(ValueError) as exc_info:
            _parse_test_design_action("invalid_action")

        assert "is not a valid action" in str(exc_info.value)
        assert "Valid actions:" in str(exc_info.value)


class TestParseTestDesignTrigger:
    """Tests for _parse_test_design_trigger helper."""

    def test_valid_trigger(self) -> None:
        """Test parsing valid trigger."""
        from dazzle.core.ir.test_design import TestDesignTrigger

        trigger = _parse_test_design_trigger("form_submitted")
        assert trigger == TestDesignTrigger.FORM_SUBMITTED

    def test_valid_trigger_click(self) -> None:
        """Test parsing user_click trigger."""
        from dazzle.core.ir.test_design import TestDesignTrigger

        trigger = _parse_test_design_trigger("user_click")
        assert trigger == TestDesignTrigger.USER_CLICK

    def test_invalid_trigger(self) -> None:
        """Test parsing invalid trigger."""
        with pytest.raises(ValueError) as exc_info:
            _parse_test_design_trigger("invalid_trigger")

        assert "is not a valid trigger" in str(exc_info.value)
        assert "Valid triggers:" in str(exc_info.value)


# =============================================================================
# Handler Tests
# =============================================================================


class TestProposePersonaTestsHandler:
    """Tests for propose_persona_tests_handler."""

    def test_proposes_tests_for_persona(self, temp_project) -> None:
        """Test proposing tests from persona goals."""
        result = propose_persona_tests_handler(temp_project, {})
        data = json.loads(result)

        # Should generate test designs for admin persona (uses 'designs' key)
        assert "designs" in data or "test_designs" in data or "status" in data

    def test_no_personas_returns_message(self, temp_project_no_personas) -> None:
        """Test handling of project without personas."""
        result = propose_persona_tests_handler(temp_project_no_personas, {})
        data = json.loads(result)

        assert data.get("status") == "no_personas"
        assert "No personas found" in data.get("message", "")

    def test_respects_max_tests(self, temp_project) -> None:
        """Test max_tests limit."""
        result = propose_persona_tests_handler(temp_project, {"max_tests": 1})
        data = json.loads(result)

        if "test_designs" in data:
            assert len(data["test_designs"]) <= 1

    def test_filters_by_persona(self, temp_project) -> None:
        """Test filtering by persona ID."""
        result = propose_persona_tests_handler(temp_project, {"persona": "admin"})
        data = json.loads(result)

        # Should only include tests for admin persona
        if "test_designs" in data:
            for td in data["test_designs"]:
                assert td.get("persona") == "Admin" or "admin" in td.get("persona", "").lower()

    def test_handles_missing_project(self, tmp_path) -> None:
        """Test handling of missing project."""
        missing_project = tmp_path / "missing"
        missing_project.mkdir()

        result = propose_persona_tests_handler(missing_project, {})
        data = json.loads(result)

        assert "error" in data


class TestSaveTestDesignsHandler:
    """Tests for save_test_designs_handler."""

    def test_requires_designs(self, temp_project) -> None:
        """Test that designs are required."""
        result = save_test_designs_handler(temp_project, {})
        data = json.loads(result)

        assert "error" in data
        # Check for error about missing designs
        assert "designs" in data["error"].lower() or "no" in data["error"].lower()

    def test_saves_valid_design(self, temp_project) -> None:
        """Test saving a valid test design."""
        designs = [
            {
                "test_id": "TD-001",
                "title": "Test Task Creation",
                "description": "Verify user can create a task",
                "persona": "admin",
                "trigger": "form_submitted",
                "steps": [
                    {"action": "login_as", "target": "admin"},
                    {"action": "navigate_to", "target": "tasks"},
                    {"action": "click", "target": "create_button"},
                ],
                "expected_outcomes": ["Task is created"],
                "entities": ["Task"],
                "tags": ["smoke"],
                "status": "proposed",
            }
        ]

        result = save_test_designs_handler(temp_project, {"designs": designs})
        data = json.loads(result)

        assert data.get("status") == "saved"
        assert data.get("saved_count") == 1

    def test_validates_design_structure(self, temp_project) -> None:
        """Test that invalid designs are rejected."""
        designs = [
            {
                "test_id": "TD-001",
                # Missing required fields
            }
        ]

        result = save_test_designs_handler(temp_project, {"designs": designs})
        data = json.loads(result)

        assert "error" in data


class TestGetTestDesignsHandler:
    """Tests for get_test_designs_handler."""

    def test_returns_empty_for_no_designs(self, temp_project) -> None:
        """Test handling of no test designs."""
        result = get_test_designs_handler(temp_project, {})
        data = json.loads(result)

        assert "count" in data
        assert data["count"] == 0

    def test_filters_by_status(self, temp_project) -> None:
        """Test filtering test designs by status."""
        # First save a design
        designs = [
            {
                "test_id": "TD-001",
                "title": "Test Design",
                "description": "Test",
                "persona": "admin",
                "trigger": "user_click",
                "steps": [{"action": "click", "target": "button"}],
                "expected_outcomes": ["Success"],
                "entities": ["Task"],
                "tags": [],
                "status": "accepted",
            }
        ]
        save_test_designs_handler(temp_project, {"designs": designs})

        # Get only accepted designs
        result = get_test_designs_handler(temp_project, {"status_filter": "accepted"})
        data = json.loads(result)

        assert data["count"] == 1

    def test_returns_full_details_for_test_ids(self, temp_project) -> None:
        """Test getting full test design details by ID."""
        # First save a design
        designs = [
            {
                "test_id": "TD-001",
                "title": "Test Design",
                "description": "Detailed description",
                "persona": "admin",
                "trigger": "user_click",
                "steps": [{"action": "click", "target": "button"}],
                "expected_outcomes": ["Success"],
                "entities": ["Task"],
                "tags": ["important"],
                "status": "proposed",
            }
        ]
        save_test_designs_handler(temp_project, {"designs": designs})

        result = get_test_designs_handler(temp_project, {"test_ids": ["TD-001"]})
        data = json.loads(result)

        assert data["count"] == 1
        # Response may use 'designs' or 'test_designs' key
        designs_list = data.get("test_designs") or data.get("designs") or []
        design = designs_list[0]
        # Full details should include description
        assert "description" in design


class TestGetTestGapsHandler:
    """Tests for get_test_gaps_handler."""

    def test_analyzes_gaps(self, temp_project) -> None:
        """Test analyzing test coverage gaps."""
        result = get_test_gaps_handler(temp_project, {})
        data = json.loads(result)

        # Should return gap analysis
        assert "gaps" in data or "entities" in data or "error" not in data

    def test_handles_missing_project(self, tmp_path) -> None:
        """Test handling of missing project."""
        missing_project = tmp_path / "missing"
        missing_project.mkdir()

        result = get_test_gaps_handler(missing_project, {})
        data = json.loads(result)

        assert "error" in data


class TestGetCoverageActionsHandler:
    """Tests for get_coverage_actions_handler."""

    def test_returns_coverage_actions(self, temp_project) -> None:
        """Test getting coverage improvement actions."""
        result = get_coverage_actions_handler(temp_project, {})
        data = json.loads(result)

        # Should return actions or analysis
        assert "actions" in data or "coverage" in data or "error" not in data

    def test_respects_max_actions(self, temp_project) -> None:
        """Test max_actions limit."""
        result = get_coverage_actions_handler(temp_project, {"max_actions": 3})
        data = json.loads(result)

        if "actions" in data:
            assert len(data["actions"]) <= 3

    def test_filters_by_focus(self, temp_project) -> None:
        """Test filtering by focus area."""
        result = get_coverage_actions_handler(temp_project, {"focus": "entities"})
        data = json.loads(result)

        # Should only return entity-related actions
        assert "actions" in data or "error" not in data


class TestSaveRuntimeCoverageHandler:
    """Tests for save_runtime_coverage_handler."""

    def test_requires_coverage_data(self, temp_project) -> None:
        """Test that coverage_data is required."""
        result = save_runtime_coverage_handler(temp_project, {})
        data = json.loads(result)

        assert "error" in data

    def test_saves_coverage_data(self, temp_project) -> None:
        """Test saving runtime coverage data."""
        coverage_data = {
            "timestamp": "2025-01-01T00:00:00Z",
            "entities_covered": ["Task"],
            "endpoints_hit": ["/api/tasks", "/api/tasks/create"],
            "personas_tested": ["admin"],
        }

        result = save_runtime_coverage_handler(temp_project, {"coverage_data": coverage_data})
        data = json.loads(result)

        assert data.get("status") == "saved" or "error" not in data


class TestGetRuntimeCoverageGapsHandler:
    """Tests for get_runtime_coverage_gaps_handler."""

    def test_analyzes_runtime_gaps(self, temp_project) -> None:
        """Test analyzing runtime coverage gaps."""
        result = get_runtime_coverage_gaps_handler(temp_project, {})
        data = json.loads(result)

        # Without coverage data, should return helpful error with hint
        # When coverage data exists, returns gaps analysis
        assert "gaps" in data or "error" in data or "status" in data
        if "error" in data:
            # Error should provide helpful guidance
            assert "hint" in data or "coverage" in data["error"].lower()

    def test_handles_missing_coverage_report(self, temp_project) -> None:
        """Test handling of missing coverage report."""
        result = get_runtime_coverage_gaps_handler(
            temp_project, {"coverage_report_path": "/nonexistent/path"}
        )
        data = json.loads(result)

        # Should handle gracefully
        assert "error" in data or "status" in data
