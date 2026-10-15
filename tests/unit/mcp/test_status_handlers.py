"""Tests for the status MCP handlers."""

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


def _import_status():
    """Import status handlers directly to avoid MCP package init issues.

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
    install_handlers_common_mock = _load_conftest_helper("install_handlers_common_mock")

    sys.modules["dazzle.mcp.server.handlers"] = MagicMock(pytest_plugins=[])
    install_handlers_common_mock()
    sys.modules["dazzle.mcp.server.state"] = mock_state

    # Mock semantics module
    mock_semantics = MagicMock()
    mock_semantics.get_mcp_version = MagicMock(return_value="1.0.0")
    sys.modules["dazzle.mcp.semantics"] = mock_semantics

    module_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "server"
        / "handlers"
        / "status.py"
    )
    spec = importlib.util.spec_from_file_location(
        "dazzle.mcp.server.handlers.status",
        module_path,
    )
    module = importlib.util.module_from_spec(spec)

    # Set up the package structure for relative imports
    sys.modules["dazzle.mcp.server.handlers.status"] = module

    spec.loader.exec_module(module)
    return module


# Import the module once at module load time
_st = _import_status()

# Get references to the functions we need
get_mcp_status_handler = _st.get_mcp_status_handler
get_dnr_logs_handler = _st.get_dnr_logs_handler


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

    # Create logs directory
    logs_dir = dazzle_dir / "logs"
    logs_dir.mkdir()

    return project_dir


@pytest.fixture
def project_with_logs(temp_project):
    """Create a project with log files."""
    log_file = temp_project / ".dazzle" / "logs" / "dazzle.log"
    log_entries = [
        '{"level": "INFO", "message": "Server started", "component": "server"}',
        '{"level": "DEBUG", "message": "Loading modules", "component": "loader"}',
        '{"level": "WARNING", "message": "Deprecated feature", "component": "parser"}',
        '{"level": "ERROR", "message": "Connection failed", "component": "db"}',
        '{"level": "ERROR", "message": "Query timeout", "component": "db"}',
        '{"level": "INFO", "message": "Request completed", "component": "server"}',
    ]
    log_file.write_text("\n".join(log_entries))
    return temp_project


# =============================================================================
# Handler Tests
# =============================================================================


def test_mcp_status_base_fields() -> None:
    data = json.loads(get_mcp_status_handler({}))
    assert data["mode"] == "dev"
    assert data["project_root"] == "/tmp/test"
    assert data["version"]
    assert "semantics_version" in data


def test_mcp_status_roots_resolved_path_wins(temp_project) -> None:
    data = json.loads(get_mcp_status_handler({"_resolved_project_path": temp_project}))
    assert data["active_project"] == {
        "path": str(temp_project),
        "manifest_name": "test_project",
        "version": "0.1.0",
    }


def test_mcp_status_reload_skipped_outside_dev_mode() -> None:
    with patch.object(_st, "is_dev_mode", return_value=False):
        data = json.loads(get_mcp_status_handler({"reload": True}))
    assert data["reload"] == "skipped - only available in dev mode"


# new_since_last_check: compact {count, hint} by default (#1629 G6), the full
# list with include_changelog=true; nothing is new once last_seen == current.
@pytest.mark.parametrize(
    ("seen_before", "include_changelog", "expect_new"),
    [
        pytest.param(False, False, True, id="first-run-compact-by-default-1629"),
        pytest.param(False, True, True, id="first-run-full-list-opt-in"),
        pytest.param(True, False, False, id="same-version-compact-zero-1629"),
        pytest.param(True, True, False, id="same-version-full-list-empty"),
    ],
)
def test_new_since_last_check(
    temp_project, seen_before: bool, include_changelog: bool, expect_new: bool
) -> None:
    import dazzle.core.changelog as _cl
    from dazzle._version import get_version

    ver = get_version()
    changelog = temp_project / "CHANGELOG.md"
    changelog.write_text(
        f"## [{ver}] - 2026-01-01\n\n### Added\n- **Cool feature** — does things\n"
    )
    version_file = temp_project / ".dazzle" / "last_seen_version"
    if seen_before:
        version_file.write_text(ver)
    args = {"_resolved_project_path": temp_project, "include_changelog": include_changelog}
    with patch.object(_cl, "get_changelog_path", return_value=changelog):
        data = json.loads(get_mcp_status_handler(args))

    assert data["last_seen_version"] == (ver if seen_before else None)
    nslc = data["new_since_last_check"]
    if include_changelog:
        assert isinstance(nslc, list)
        assert bool(nslc) is expect_new
    else:
        assert "hint" in nslc
        assert (nslc["count"] > 0) is expect_new
    # The check records the current version for next time.
    assert version_file.read_text().strip() == ver


def test_dnr_logs_no_log_file(temp_project) -> None:
    data = json.loads(get_dnr_logs_handler({"_resolved_project_path": temp_project}))
    assert data["status"] == "no_logs"
    assert "hint" in data


@pytest.mark.parametrize(
    ("args", "returned", "levels"),
    [
        pytest.param({}, 6, None, id="all-entries"),
        pytest.param({"count": 2}, 2, None, id="count-limit"),
        pytest.param({"level": "ERROR"}, 2, {"ERROR"}, id="level-filter"),
    ],
)
def test_dnr_logs_entries(project_with_logs, args: dict, returned: int, levels) -> None:
    data = json.loads(get_dnr_logs_handler({"_resolved_project_path": project_with_logs, **args}))
    assert data["status"] == "ok"
    # total_entries counts entries after the level filter, before the count limit.
    assert data["total_entries"] == (2 if levels else 6)
    assert data["returned"] == returned
    assert len(data["entries"]) == returned
    if levels is not None:
        assert {e["level"] for e in data["entries"]} == levels


def test_dnr_logs_errors_only_summary(project_with_logs) -> None:
    data = json.loads(
        get_dnr_logs_handler({"_resolved_project_path": project_with_logs, "errors_only": True})
    )
    assert data["status"] == "error_summary"
    assert data["error_count"] == 2
    assert data["warning_count"] == 1
    assert data["errors_by_component"] == {"db": 2}
    assert len(data["recent_errors"]) == 2
