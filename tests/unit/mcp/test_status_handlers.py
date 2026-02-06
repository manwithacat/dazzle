"""Tests for the status MCP handlers."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


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
    sys.modules["dazzle.mcp.server.handlers"] = MagicMock()
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
        submodule_search_locations=[],
    )
    module = importlib.util.module_from_spec(spec)

    # Set up the package structure for relative imports
    module.__package__ = "dazzle.mcp.server.handlers"
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


class TestGetMcpStatusHandler:
    """Tests for get_mcp_status_handler."""

    def test_returns_status(self) -> None:
        """Test basic status retrieval."""
        result = get_mcp_status_handler({})
        data = json.loads(result)

        # Should return mode and version info
        assert "mode" in data
        assert "version" in data or "semantics_version" in data

    def test_returns_project_root(self) -> None:
        """Test project root is included."""
        result = get_mcp_status_handler({})
        data = json.loads(result)

        assert "project_root" in data

    def test_with_resolved_project_path(self, temp_project) -> None:
        """Test with resolved project path."""
        result = get_mcp_status_handler({"_resolved_project_path": temp_project})
        data = json.loads(result)

        # Should include active project info from resolved path
        assert "active_project" in data or "project_root" in data

    def test_reload_option_in_non_dev_mode(self) -> None:
        """Test reload option when not in dev mode."""
        with patch.object(_st, "is_dev_mode", return_value=False):
            result = get_mcp_status_handler({"reload": True})
            data = json.loads(result)

            # Reload should be skipped in non-dev mode
            if "reload" in data:
                assert "skipped" in data["reload"]


class TestGetDnrLogsHandler:
    """Tests for get_dnr_logs_handler."""

    def test_no_log_file(self, temp_project) -> None:
        """Test handling when no log file exists."""
        # Remove logs directory content
        log_file = temp_project / ".dazzle" / "logs" / "dazzle.log"
        if log_file.exists():
            log_file.unlink()

        result = get_dnr_logs_handler({"_resolved_project_path": temp_project})
        data = json.loads(result)

        assert data["status"] == "no_logs"
        assert "hint" in data

    def test_returns_log_entries(self, project_with_logs) -> None:
        """Test returning log entries."""
        result = get_dnr_logs_handler({"_resolved_project_path": project_with_logs})
        data = json.loads(result)

        assert data["status"] == "ok"
        assert "entries" in data
        assert data["total_entries"] == 6

    def test_respects_count_limit(self, project_with_logs) -> None:
        """Test count limit option."""
        result = get_dnr_logs_handler({"_resolved_project_path": project_with_logs, "count": 2})
        data = json.loads(result)

        assert data["status"] == "ok"
        assert data["returned"] == 2

    def test_filters_by_level(self, project_with_logs) -> None:
        """Test filtering by log level."""
        result = get_dnr_logs_handler(
            {"_resolved_project_path": project_with_logs, "level": "ERROR"}
        )
        data = json.loads(result)

        assert data["status"] == "ok"
        # Should only return ERROR entries
        for entry in data["entries"]:
            assert entry["level"] == "ERROR"

    def test_errors_only_mode(self, project_with_logs) -> None:
        """Test errors_only mode."""
        result = get_dnr_logs_handler(
            {"_resolved_project_path": project_with_logs, "errors_only": True}
        )
        data = json.loads(result)

        assert data["status"] == "error_summary"
        assert "error_count" in data
        assert "warning_count" in data
        assert "errors_by_component" in data
        assert data["error_count"] == 2
        assert data["warning_count"] == 1

    def test_groups_errors_by_component(self, project_with_logs) -> None:
        """Test that errors are grouped by component."""
        result = get_dnr_logs_handler(
            {"_resolved_project_path": project_with_logs, "errors_only": True}
        )
        data = json.loads(result)

        assert "errors_by_component" in data
        assert data["errors_by_component"]["db"] == 2

    def test_includes_recent_errors(self, project_with_logs) -> None:
        """Test that recent errors are included."""
        result = get_dnr_logs_handler(
            {"_resolved_project_path": project_with_logs, "errors_only": True}
        )
        data = json.loads(result)

        assert "recent_errors" in data
        assert len(data["recent_errors"]) == 2
