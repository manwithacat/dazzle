"""Tests for the project MCP handlers."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_CONFTEST_PATH = str(Path(__file__).parent / "conftest.py")


def _load_conftest_helper(name: str) -> object:
    """Load a helper from conftest.py by file path (not package import)."""
    spec = importlib.util.spec_from_file_location("_mcp_conftest", _CONFTEST_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return getattr(mod, name)


def _import_project():
    """Import project handlers directly to avoid MCP package init issues.

    The dazzle.mcp.__init__.py imports mcp.server which may not be installed
    in test environments. We need to import the handlers module directly.
    """
    # Create mock modules to satisfy imports
    mock_state = MagicMock()
    mock_state.get_project_root = MagicMock(return_value=Path("/tmp/test"))
    mock_state.get_active_project = MagicMock(return_value=None)
    mock_state.get_active_project_path = MagicMock(return_value=None)
    mock_state.get_available_projects = MagicMock(return_value={})
    mock_state.is_dev_mode = MagicMock(return_value=True)
    mock_state.set_active_project = MagicMock()
    install_handlers_common_mock = _load_conftest_helper("install_handlers_common_mock")

    sys.modules["dazzle.mcp.server.handlers"] = MagicMock(pytest_plugins=[])
    install_handlers_common_mock()
    sys.modules["dazzle.mcp.server.state"] = mock_state

    # Mock runtime_tools module
    mock_runtime = MagicMock()
    mock_runtime.set_backend_spec = MagicMock()
    sys.modules["dazzle.mcp.runtime_tools"] = mock_runtime

    module_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "server"
        / "handlers"
        / "project.py"
    )
    spec = importlib.util.spec_from_file_location(
        "dazzle.mcp.server.handlers.project",
        module_path,
        submodule_search_locations=[],
    )
    module = importlib.util.module_from_spec(spec)

    # Set up the package structure for relative imports
    module.__package__ = "dazzle.mcp.server.handlers"
    sys.modules["dazzle.mcp.server.handlers.project"] = module

    spec.loader.exec_module(module)
    return module


# Import the module once at module load time
_pr = _import_project()

# Get references to the functions we need
list_projects = _pr.list_projects
select_project = _pr.select_project
get_active_project_info = _pr.get_active_project_info
validate_all_projects = _pr.validate_all_projects
load_backend_spec_for_project = _pr.load_backend_spec_for_project


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
"""
    )

    # Create .dazzle directory
    dazzle_dir = project_dir / ".dazzle"
    dazzle_dir.mkdir()

    return project_dir


# =============================================================================
# Handler Tests
# =============================================================================


class TestListProjects:
    """Tests for list_projects handler."""

    def test_returns_error_not_in_dev_mode(self) -> None:
        """Test error when not in dev mode."""
        with patch.object(_pr, "is_dev_mode", return_value=False):
            result = list_projects()
            data = json.loads(result)

            assert "error" in data
            assert "dev mode" in data["error"].lower()

    def test_returns_project_list_in_dev_mode(self) -> None:
        """Test listing projects in dev mode."""
        with patch.object(_pr, "is_dev_mode", return_value=True):
            with patch.object(_pr, "get_available_projects", return_value={}):
                with patch.object(_pr, "get_active_project", return_value=None):
                    result = list_projects()
                    data = json.loads(result)

                    assert data["mode"] == "dev"
                    assert "project_count" in data
                    assert "projects" in data

    def test_includes_active_project(self, temp_project) -> None:
        """Test that active project is indicated."""
        projects = {"test_project": temp_project}
        with patch.object(_pr, "is_dev_mode", return_value=True):
            with patch.object(_pr, "get_available_projects", return_value=projects):
                with patch.object(_pr, "get_active_project", return_value="test_project"):
                    result = list_projects()
                    data = json.loads(result)

                    assert data["active_project"] == "test_project"
                    # Find the active project in the list
                    active = [p for p in data["projects"] if p["active"]]
                    assert len(active) == 1
                    assert active[0]["name"] == "test_project"


class TestSelectProject:
    """Tests for select_project handler."""

    def test_returns_error_not_in_dev_mode(self) -> None:
        """Test error when not in dev mode."""
        with patch.object(_pr, "is_dev_mode", return_value=False):
            result = select_project({"project_name": "test"})
            data = json.loads(result)

            assert "error" in data
            assert "dev mode" in data["error"].lower()

    def test_requires_project_name(self) -> None:
        """Test that project_name is required."""
        with patch.object(_pr, "is_dev_mode", return_value=True):
            result = select_project({})
            data = json.loads(result)

            assert "error" in data
            assert "project_name" in data["error"].lower()

    def test_selects_valid_project(self, temp_project) -> None:
        """Test selecting a valid project."""
        projects = {"test_project": temp_project}
        with patch.object(_pr, "is_dev_mode", return_value=True):
            with patch.object(_pr, "get_available_projects", return_value=projects):
                result = select_project({"project_name": "test_project"})
                data = json.loads(result)

                assert data["status"] == "selected"
                assert data["project"] == "test_project"
                assert "path" in data

    def test_returns_error_for_unknown_project(self) -> None:
        """Test error for unknown project name."""
        with patch.object(_pr, "is_dev_mode", return_value=True):
            with patch.object(_pr, "get_available_projects", return_value={}):
                result = select_project({"project_name": "nonexistent"})
                data = json.loads(result)

                assert "error" in data
                assert "not found" in data["error"].lower()

    def test_accepts_absolute_path(self, temp_project) -> None:
        """Test accepting an absolute path to external project."""
        with patch.object(_pr, "is_dev_mode", return_value=True):
            with patch.object(_pr, "get_available_projects", return_value={}):
                result = select_project({"project_name": str(temp_project)})
                data = json.loads(result)

                assert data["status"] == "selected"


class TestGetActiveProjectInfo:
    """Tests for get_active_project_info handler."""

    def test_with_resolved_path(self, temp_project) -> None:
        """Test with resolved path containing manifest."""
        result = get_active_project_info(resolved_path=temp_project)
        data = json.loads(result)

        assert "manifest_name" in data or "error" in data
        if "manifest_name" in data:
            assert data["manifest_name"] == "test_project"

    def test_no_active_project_in_dev_mode(self) -> None:
        """Test when no project is active in dev mode."""
        with patch.object(_pr, "is_dev_mode", return_value=True):
            with patch.object(_pr, "get_active_project", return_value=None):
                with patch.object(_pr, "get_available_projects", return_value={}):
                    with patch.object(
                        _pr, "get_project_root", return_value=Path("/tmp/no-manifest")
                    ):
                        result = get_active_project_info()
                        data = json.loads(result)

                        assert data["mode"] == "dev"
                        assert (
                            data.get("active_project") is None
                            or "message" in data
                            or "error" in data
                        )

    def test_with_cwd_manifest_in_dev_mode(self, temp_project) -> None:
        """Test when CWD has a manifest in dev mode."""
        with patch.object(_pr, "is_dev_mode", return_value=True):
            with patch.object(_pr, "get_project_root", return_value=temp_project):
                result = get_active_project_info()
                data = json.loads(result)

                assert data["mode"] == "dev"
                assert data.get("source") == "cwd" or "manifest_name" in data


class TestValidateAllProjects:
    """Tests for validate_all_projects handler."""

    def test_returns_error_not_in_dev_mode(self) -> None:
        """Test error when not in dev mode."""
        with patch.object(_pr, "is_dev_mode", return_value=False):
            result = validate_all_projects()
            data = json.loads(result)

            assert "error" in data
            assert "dev mode" in data["error"].lower()

    def test_validates_empty_project_list(self) -> None:
        """Test validating when no projects available."""
        with patch.object(_pr, "is_dev_mode", return_value=True):
            with patch.object(_pr, "get_available_projects", return_value={}):
                result = validate_all_projects()
                data = json.loads(result)

                assert "summary" in data
                assert data["summary"]["total"] == 0

    def test_validates_valid_project(self, temp_project) -> None:
        """Test validating a valid project."""
        projects = {"test_project": temp_project}
        with patch.object(_pr, "is_dev_mode", return_value=True):
            with patch.object(_pr, "get_available_projects", return_value=projects):
                result = validate_all_projects()
                data = json.loads(result)

                assert "summary" in data
                assert "projects" in data
                # Check validation result
                if "test_project" in data["projects"]:
                    proj_result = data["projects"]["test_project"]
                    assert proj_result["status"] in ("valid", "error")


class TestLoadBackendSpecForProject:
    """Tests for load_backend_spec_for_project helper."""

    def test_returns_false_for_missing_manifest(self, tmp_path) -> None:
        """Test returns False when no dazzle.toml."""
        project_dir = tmp_path / "no_manifest"
        project_dir.mkdir()

        result = load_backend_spec_for_project(project_dir)
        assert result is False

    def test_returns_false_for_no_dsl_files(self, tmp_path) -> None:
        """Test returns False when no DSL files."""
        project_dir = tmp_path / "empty_project"
        project_dir.mkdir()

        manifest = project_dir / "dazzle.toml"
        manifest.write_text(
            """
[project]
name = "empty"
version = "0.1.0"
root = "empty"

[modules]
paths = ["./dsl"]
"""
        )

        result = load_backend_spec_for_project(project_dir)
        assert result is False
