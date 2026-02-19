"""Tests for mock MCP handler operations."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def project_path(tmp_path: Path) -> Path:
    """Create a minimal project directory."""
    return tmp_path


@pytest.fixture
def mock_orchestrator():
    """Create a mock MockOrchestrator."""
    orch = MagicMock()
    orch.is_running = True
    orch.project_root = None

    # Create mock vendor
    vendor_mock = MagicMock()
    vendor_mock.pack_name = "test_vendor"
    vendor_mock.provider = "TestProvider"
    vendor_mock.port = 9001
    vendor_mock.base_url = "http://127.0.0.1:9001"
    vendor_mock.env_var = "DAZZLE_API_TEST_VENDOR_URL"

    orch.vendors = {"test_vendor": vendor_mock}
    orch.health_check.return_value = {"test_vendor": True}

    # Mock app with scenario engine
    mock_app = MagicMock()
    mock_engine = MagicMock()
    mock_engine.list_scenarios.return_value = ["test_vendor/happy_path"]
    mock_engine.active_scenarios = {}
    mock_app.state.scenario_engine = mock_engine
    orch.get_app.return_value = mock_app

    # Mock store
    mock_store = MagicMock()
    mock_store.request_log = [
        {"method": "GET", "path": "/api/items", "timestamp": 1000, "status_code": 200},
        {"method": "POST", "path": "/api/items", "timestamp": 1001, "status_code": 201},
    ]
    orch.get_store.return_value = mock_store

    return orch


def test_mock_status_no_orchestrator(project_path: Path) -> None:
    """Status returns helpful message when no orchestrator running."""
    from dazzle.mcp.server.handlers.mock import mock_status_handler

    with patch("dazzle.mcp.server.handlers.mock._get_orchestrator", return_value=None):
        result = json.loads(mock_status_handler(project_path, {}))

    assert result["running"] is False
    assert "message" in result


def test_mock_status_with_orchestrator(project_path: Path, mock_orchestrator) -> None:
    """Status returns vendor info when orchestrator is running."""
    from dazzle.mcp.server.handlers.mock import mock_status_handler

    with patch("dazzle.mcp.server.handlers.mock._get_orchestrator", return_value=mock_orchestrator):
        result = json.loads(mock_status_handler(project_path, {}))

    assert result["running"] is True
    assert result["vendor_count"] == 1
    assert result["vendors"][0]["pack_name"] == "test_vendor"
    assert result["vendors"][0]["healthy"] is True


def test_mock_scenarios_list(project_path: Path, mock_orchestrator) -> None:
    """Scenarios list returns available scenarios."""
    from dazzle.mcp.server.handlers.mock import mock_scenarios_handler

    with patch("dazzle.mcp.server.handlers.mock._get_orchestrator", return_value=mock_orchestrator):
        result = json.loads(
            mock_scenarios_handler(
                project_path,
                {"action": "list", "vendor": "test_vendor"},
            )
        )

    assert result["count"] == 1
    assert "test_vendor/happy_path" in result["scenarios"]


def test_mock_scenarios_activate(project_path: Path, mock_orchestrator) -> None:
    """Scenarios activate loads and returns scenario info."""
    from dazzle.mcp.server.handlers.mock import mock_scenarios_handler

    mock_scenario = MagicMock()
    mock_scenario.name = "happy_path"
    mock_scenario.description = "Happy path scenario"
    mock_scenario.steps = [MagicMock(), MagicMock()]
    mock_orchestrator.get_app.return_value.state.scenario_engine.load_scenario.return_value = (
        mock_scenario
    )

    with patch("dazzle.mcp.server.handlers.mock._get_orchestrator", return_value=mock_orchestrator):
        result = json.loads(
            mock_scenarios_handler(
                project_path,
                {
                    "action": "activate",
                    "vendor": "test_vendor",
                    "scenario_name": "happy_path",
                },
            )
        )

    assert result["status"] == "activated"
    assert result["steps"] == 2


def test_mock_scenarios_deactivate(project_path: Path, mock_orchestrator) -> None:
    """Scenarios deactivate resets the vendor."""
    from dazzle.mcp.server.handlers.mock import mock_scenarios_handler

    with patch("dazzle.mcp.server.handlers.mock._get_orchestrator", return_value=mock_orchestrator):
        result = json.loads(
            mock_scenarios_handler(
                project_path,
                {"action": "deactivate", "vendor": "test_vendor"},
            )
        )

    assert result["status"] == "deactivated"


def test_mock_request_log(project_path: Path, mock_orchestrator) -> None:
    """Request log returns recorded requests."""
    from dazzle.mcp.server.handlers.mock import mock_request_log_handler

    with patch("dazzle.mcp.server.handlers.mock._get_orchestrator", return_value=mock_orchestrator):
        result = json.loads(
            mock_request_log_handler(
                project_path,
                {"vendor": "test_vendor"},
            )
        )

    assert result["count"] == 2
    assert result["requests"][0]["method"] == "POST"  # Most recent first


def test_mock_request_log_filtered(project_path: Path, mock_orchestrator) -> None:
    """Request log supports method filtering."""
    from dazzle.mcp.server.handlers.mock import mock_request_log_handler

    with patch("dazzle.mcp.server.handlers.mock._get_orchestrator", return_value=mock_orchestrator):
        result = json.loads(
            mock_request_log_handler(
                project_path,
                {"vendor": "test_vendor", "method": "GET"},
            )
        )

    assert result["count"] == 1
    assert result["requests"][0]["method"] == "GET"


def test_mock_inject_error(project_path: Path, mock_orchestrator) -> None:
    """Inject error configures the scenario engine."""
    from dazzle.mcp.server.handlers.mock import mock_inject_error_handler

    with patch("dazzle.mcp.server.handlers.mock._get_orchestrator", return_value=mock_orchestrator):
        result = json.loads(
            mock_inject_error_handler(
                project_path,
                {
                    "vendor": "test_vendor",
                    "operation_name": "create_item",
                    "status_code": 503,
                },
            )
        )

    assert result["status"] == "injected"
    assert result["error_status"] == 503


def test_mock_inject_error_no_orchestrator(project_path: Path) -> None:
    """Inject error returns error when no orchestrator."""
    from dazzle.mcp.server.handlers.mock import mock_inject_error_handler

    with patch("dazzle.mcp.server.handlers.mock._get_orchestrator", return_value=None):
        result = json.loads(
            mock_inject_error_handler(
                project_path,
                {"vendor": "test_vendor", "operation_name": "create_item"},
            )
        )

    assert "error" in result


def test_mock_scaffold_scenario(project_path: Path) -> None:
    """Scaffold scenario generates TOML template."""
    from dazzle.mcp.server.handlers.mock import mock_scaffold_scenario_handler

    result = json.loads(
        mock_scaffold_scenario_handler(
            project_path,
            {"vendor": "my_vendor", "scenario_name": "payment_failed"},
        )
    )

    assert "toml" in result
    assert "save_path" in result
    assert "my_vendor" in result["toml"]
    assert "payment_failed" in result["toml"]
    assert result["save_path"] == ".dazzle/scenarios/my_vendor/payment_failed.toml"
