"""Tests for the fidelity MCP handlers."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


def _import_fidelity():
    """Import fidelity handlers directly to avoid MCP package init issues.

    The dazzle.mcp.__init__.py imports mcp.server which may not be installed
    in test environments. We need to import the handlers module directly.
    """
    # Create mock modules to satisfy imports
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
    common_mock.handler_error_json = lambda fn: fn
    sys.modules["dazzle.mcp.server.handlers.common"] = common_mock

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

    # Set up the package structure for relative imports
    module.__package__ = "dazzle.mcp.server.handlers"
    sys.modules["dazzle.mcp.server.handlers.fidelity"] = module

    spec.loader.exec_module(module)
    return module


# Import the module once at module load time
_fi = _import_fidelity()

# Get references to the functions we need
score_fidelity_handler = _fi.score_fidelity_handler
_build_next_steps = _fi._build_next_steps


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

    # Create main.dsl
    main_dsl = dsl_dir / "main.dsl"
    main_dsl.write_text(
        """
module test_project
app test_project "Test Project"

entity Task "Task":
    id: uuid pk
    title: str(200) required

surface task_list "Tasks":
    uses entity Task
    mode: list
    section main:
        field title "Title"
"""
    )

    return project_dir


# =============================================================================
# Handler Tests
# =============================================================================


class TestScoreFidelityHandler:
    """Tests for score_fidelity_handler."""

    def test_handles_missing_manifest(self, tmp_path) -> None:
        """Test handling when dazzle.toml is missing."""
        project_dir = tmp_path / "no_manifest"
        project_dir.mkdir()

        result = score_fidelity_handler(project_dir, {})
        data = json.loads(result)

        assert "error" in data

    def test_handles_parse_errors(self, tmp_path) -> None:
        """Test handling parse errors."""
        project_dir = tmp_path / "bad_dsl"
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

        # Invalid DSL
        main_dsl = dsl_dir / "main.dsl"
        main_dsl.write_text("this is not valid dsl syntax {{{")

        result = score_fidelity_handler(project_dir, {})
        data = json.loads(result)

        assert "error" in data


class TestBuildNextSteps:
    """Tests for _build_next_steps helper."""

    def test_low_overall_score(self) -> None:
        """Test next steps for low fidelity score."""
        mock_report = SimpleNamespace(
            overall=0.3,
            gap_counts={},
            story_coverage=0.5,
        )

        steps = _build_next_steps(mock_report)

        assert len(steps) > 0
        assert any("critical" in s.lower() for s in steps)

    def test_medium_overall_score(self) -> None:
        """Test next steps for medium fidelity score."""
        mock_report = SimpleNamespace(
            overall=0.6,
            gap_counts={},
            story_coverage=0.5,
        )

        steps = _build_next_steps(mock_report)

        assert len(steps) > 0
        assert any("major" in s.lower() or "0.8" in s for s in steps)

    def test_good_overall_score(self) -> None:
        """Test next steps for good fidelity score."""
        mock_report = SimpleNamespace(
            overall=0.9,
            gap_counts={},
            story_coverage=0.8,
        )

        steps = _build_next_steps(mock_report)

        assert len(steps) > 0
        assert any("good" in s.lower() or "story" in s.lower() for s in steps)

    def test_missing_field_gaps(self) -> None:
        """Test next steps when missing fields."""
        mock_report = SimpleNamespace(
            overall=0.7,
            gap_counts={"missing_field": 3},
            story_coverage=0.5,
        )

        steps = _build_next_steps(mock_report)

        assert any("missing fields" in s.lower() for s in steps)

    def test_incorrect_input_type_gaps(self) -> None:
        """Test next steps when input types are incorrect."""
        mock_report = SimpleNamespace(
            overall=0.7,
            gap_counts={"incorrect_input_type": 2},
            story_coverage=0.5,
        )

        steps = _build_next_steps(mock_report)

        assert any("input types" in s.lower() for s in steps)

    def test_missing_design_tokens(self) -> None:
        """Test next steps when design tokens are missing."""
        mock_report = SimpleNamespace(
            overall=0.7,
            gap_counts={"missing_design_tokens": 1},
            story_coverage=0.5,
        )

        steps = _build_next_steps(mock_report)

        assert any("design tokens" in s.lower() for s in steps)

    def test_low_story_coverage(self) -> None:
        """Test next steps when story coverage is low."""
        mock_report = SimpleNamespace(
            overall=0.8,
            gap_counts={},
            story_coverage=0.3,
        )

        steps = _build_next_steps(mock_report)

        assert any("story" in s.lower() for s in steps)
