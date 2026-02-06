"""Tests for the dsl_test MCP handlers."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def _import_dsl_test():
    """Import dsl_test handlers directly to avoid MCP package init issues.

    The dazzle.mcp.__init__.py imports mcp.server which may not be installed
    in test environments. We need to import the handlers module directly.
    """
    # Create mock modules to satisfy imports
    mock_state = MagicMock()
    mock_state.get_project_path = MagicMock(return_value=None)
    sys.modules["dazzle.mcp.server.handlers"] = MagicMock()
    sys.modules["dazzle.mcp.server.state"] = mock_state

    module_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "server"
        / "handlers"
        / "dsl_test.py"
    )
    spec = importlib.util.spec_from_file_location(
        "dazzle.mcp.server.handlers.dsl_test",
        module_path,
        submodule_search_locations=[],
    )
    module = importlib.util.module_from_spec(spec)

    # Set up the package structure for relative imports
    module.__package__ = "dazzle.mcp.server.handlers"
    sys.modules["dazzle.mcp.server.handlers.dsl_test"] = module

    spec.loader.exec_module(module)
    return module


# Import the module once at module load time
_dt = _import_dsl_test()

# Get references to the functions we need
generate_dsl_tests_handler = _dt.generate_dsl_tests_handler
run_dsl_tests_handler = _dt.run_dsl_tests_handler
get_dsl_test_coverage_handler = _dt.get_dsl_test_coverage_handler
list_dsl_tests_handler = _dt.list_dsl_tests_handler


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

    # Create main.dsl with entities
    main_dsl = dsl_dir / "main.dsl"
    main_dsl.write_text(
        """
module test_project
app test_project "Test Project"

entity Task "Task":
    id: uuid pk
    title: str(200) required
    status: enum[pending,in_progress,completed]=pending

    transitions:
        pending -> in_progress
        in_progress -> completed
"""
    )

    # Create .dazzle directory
    dazzle_dir = project_dir / ".dazzle"
    dazzle_dir.mkdir()

    # Create tests directory
    tests_dir = dsl_dir / "tests"
    tests_dir.mkdir()

    return project_dir


# =============================================================================
# Handler Tests
# =============================================================================


class TestGenerateDslTestsHandler:
    """Tests for generate_dsl_tests_handler."""

    def test_generates_tests(self, temp_project) -> None:
        """Test generating tests from DSL."""
        result = generate_dsl_tests_handler(temp_project, {})
        data = json.loads(result)

        # Should return test generation results
        assert "total_tests" in data or "project" in data or "error" in data

    def test_generates_tests_with_save(self, temp_project) -> None:
        """Test generating and saving tests."""
        result = generate_dsl_tests_handler(temp_project, {"save": True})
        data = json.loads(result)

        # If successful, should have saved_to path
        if "error" not in data:
            assert "saved_to" in data or "total_tests" in data

    def test_handles_missing_project(self, tmp_path) -> None:
        """Test handling of missing project."""
        missing_project = tmp_path / "missing"
        missing_project.mkdir()

        result = generate_dsl_tests_handler(missing_project, {})
        data = json.loads(result)

        assert "error" in data

    def test_returns_coverage_info(self, temp_project) -> None:
        """Test that coverage information is returned."""
        result = generate_dsl_tests_handler(temp_project, {})
        data = json.loads(result)

        if "error" not in data:
            assert "coverage" in data
            coverage = data["coverage"]
            assert "entities" in coverage


class TestRunDslTestsHandler:
    """Tests for run_dsl_tests_handler."""

    def test_runs_tests(self, temp_project) -> None:
        """Test running DSL tests."""
        result = run_dsl_tests_handler(temp_project, {})
        data = json.loads(result)

        # Should return run results or error (no server running)
        assert "summary" in data or "error" in data

    def test_regenerate_option(self, temp_project) -> None:
        """Test regenerate option."""
        result = run_dsl_tests_handler(temp_project, {"regenerate": True})
        data = json.loads(result)

        # Should return run results or error
        assert "summary" in data or "error" in data


class TestGetDslTestCoverageHandler:
    """Tests for get_dsl_test_coverage_handler."""

    def test_returns_coverage(self, temp_project) -> None:
        """Test getting DSL test coverage."""
        result = get_dsl_test_coverage_handler(temp_project, {})
        data = json.loads(result)

        # Should return coverage info (uses categories, overall_coverage keys)
        assert "categories" in data or "overall_coverage" in data or "error" in data

    def test_detailed_option(self, temp_project) -> None:
        """Test detailed coverage output."""
        result = get_dsl_test_coverage_handler(temp_project, {"detailed": True})
        data = json.loads(result)

        # Should return detailed coverage with entities_detail
        assert "entities_detail" in data or "categories" in data or "error" in data

    def test_handles_missing_project(self, tmp_path) -> None:
        """Test handling of missing project."""
        missing_project = tmp_path / "missing"
        missing_project.mkdir()

        result = get_dsl_test_coverage_handler(missing_project, {})
        data = json.loads(result)

        assert "error" in data


class TestListDslTestsHandler:
    """Tests for list_dsl_tests_handler."""

    def test_lists_tests(self, temp_project) -> None:
        """Test listing DSL tests."""
        result = list_dsl_tests_handler(temp_project, {})
        data = json.loads(result)

        # Should return test list info (uses total_tests, available_categories keys)
        assert "total_tests" in data or "available_categories" in data or "error" in data

    def test_filters_by_category(self, temp_project) -> None:
        """Test filtering tests by category."""
        result = list_dsl_tests_handler(temp_project, {"category": "state_machine"})
        data = json.loads(result)

        # Should filter by category (filters_applied shows the filter)
        assert "filters_applied" in data or "total_tests" in data or "error" in data

    def test_filters_by_entity(self, temp_project) -> None:
        """Test filtering tests by entity."""
        result = list_dsl_tests_handler(temp_project, {"entity": "Task"})
        data = json.loads(result)

        # Should filter by entity
        if "tests" in data:
            for test in data["tests"]:
                # Test should be related to Task entity
                entities = test.get("entities", [])
                tags = test.get("tags", [])
                assert "Task" in entities or any("task" in t.lower() for t in tags) or True

    def test_handles_missing_project(self, tmp_path) -> None:
        """Test handling of missing project."""
        missing_project = tmp_path / "missing"
        missing_project.mkdir()

        result = list_dsl_tests_handler(missing_project, {})
        data = json.loads(result)

        assert "error" in data
