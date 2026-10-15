"""Tests for the project MCP handlers."""

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
    )
    module = importlib.util.module_from_spec(spec)

    # Set up the package structure for relative imports
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
load_appspec_for_project = _pr.load_appspec_for_project


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


def _state(dev: bool = True, projects: dict | None = None, active: str | None = None, root=None):
    """Patch the server-state accessors the project handlers read."""
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(patch.object(_pr, "is_dev_mode", return_value=dev))
    stack.enter_context(patch.object(_pr, "get_available_projects", return_value=projects or {}))
    stack.enter_context(patch.object(_pr, "get_active_project", return_value=active))
    if root is not None:
        stack.enter_context(patch.object(_pr, "get_project_root", return_value=root))
    return stack


# The project-switching tools exist only in the Dazzle dev environment.
@pytest.mark.parametrize(
    "call",
    [
        pytest.param(list_projects, id="list_projects"),
        pytest.param(lambda: select_project({"project_name": "test"}), id="select_project"),
        pytest.param(validate_all_projects, id="validate_all_projects"),
    ],
)
def test_dev_mode_only_tools_refuse_outside_dev_mode(call) -> None:
    with _state(dev=False):
        data = json.loads(call())
    assert "dev mode" in data["error"].lower()


def test_list_projects_marks_the_active_project(temp_project) -> None:
    with _state(projects={"test_project": temp_project}, active="test_project"):
        data = json.loads(list_projects())
    assert data["mode"] == "dev"
    assert data["project_count"] == 1
    assert data["active_project"] == "test_project"
    assert [p["name"] for p in data["projects"] if p["active"]] == ["test_project"]


@pytest.mark.parametrize(
    ("args", "phrase"),
    [
        pytest.param({}, "project_name", id="requires-project-name"),
        pytest.param({"project_name": "nonexistent"}, "not found", id="unknown-project"),
    ],
)
def test_select_project_errors(args: dict, phrase: str) -> None:
    with _state():
        data = json.loads(select_project(args))
    assert phrase in data["error"].lower()


# A project is selected by its registered name or by an absolute path to an
# external project.
@pytest.mark.parametrize("by_path", [False, True], ids=["by-name", "by-absolute-path"])
def test_select_project_selects(temp_project, by_path: bool) -> None:
    projects = {} if by_path else {"test_project": temp_project}
    name = str(temp_project) if by_path else "test_project"
    with _state(projects=projects):
        data = json.loads(select_project({"project_name": name}))
    assert data["status"] == "selected"
    assert data["path"] == str(temp_project)
    if not by_path:
        assert data["project"] == "test_project"


def test_active_project_info_prefers_roots_resolved_path(temp_project) -> None:
    data = json.loads(get_active_project_info(resolved_path=temp_project))
    assert data["manifest_name"] == "test_project"
    assert data["project_root"] == str(temp_project)
    assert data["appspec"] == "loaded"


def test_active_project_info_dev_mode_cwd_manifest(temp_project) -> None:
    with _state(root=temp_project):
        data = json.loads(get_active_project_info())
    assert data["mode"] == "dev"
    assert data["source"] == "cwd"
    assert data["manifest_name"] == "test_project"


def test_active_project_info_dev_mode_nothing_selected(tmp_path) -> None:
    with _state(root=tmp_path / "no-manifest"):
        data = json.loads(get_active_project_info())
    assert data["mode"] == "dev"
    assert data["active_project"] is None
    assert data["available_projects"] == []


@pytest.mark.parametrize("with_project", [False, True], ids=["empty", "one-valid-project"])
def test_validate_all_projects_summary(temp_project, with_project: bool) -> None:
    projects = {"test_project": temp_project} if with_project else {}
    with _state(projects=projects):
        data = json.loads(validate_all_projects())
    n = int(with_project)
    assert data["summary"] == {"total": n, "valid": n, "errors": 0}
    if with_project:
        assert data["projects"]["test_project"]["status"] == "valid"


# load_appspec_for_project reports False (not raise) when there is nothing to build.
@pytest.mark.parametrize(
    "manifest",
    [
        pytest.param(None, id="missing-manifest"),
        pytest.param(
            '[project]\nname = "empty"\nversion = "0.1.0"\nroot = "empty"\n\n'
            '[modules]\npaths = ["./dsl"]\n',
            id="no-dsl-files",
        ),
    ],
)
def test_load_appspec_for_project_false_when_nothing_to_build(tmp_path, manifest) -> None:
    if manifest is not None:
        (tmp_path / "dazzle.toml").write_text(manifest)
    assert load_appspec_for_project(tmp_path) is False
