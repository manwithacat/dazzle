"""Tests for the mock implementations behind the ``dazzle mock`` CLI."""

from unittest.mock import MagicMock, patch

import pytest

_ORCH = "dazzle.mcp.server.handlers.mock._get_orchestrator"


@pytest.fixture
def mock_orchestrator():
    """Create a mock MockOrchestrator."""
    orch = MagicMock()
    orch.is_running = True
    orch.project_root = None

    vendor_mock = MagicMock()
    vendor_mock.pack_name = "test_vendor"
    orch.vendors = {"test_vendor": vendor_mock}

    mock_app = MagicMock()
    mock_engine = MagicMock()
    mock_engine.list_scenarios.return_value = ["test_vendor/happy_path"]
    mock_engine.active_scenarios = {}
    mock_app.state.scenario_engine = mock_engine
    orch.get_app.return_value = mock_app
    return orch


def test_mock_scenarios_list(mock_orchestrator) -> None:
    from dazzle.mcp.server.handlers.mock import mock_scenarios_impl

    with patch(_ORCH, return_value=mock_orchestrator):
        result = mock_scenarios_impl(action="list", vendor="test_vendor")

    assert result["count"] == 1
    assert "test_vendor/happy_path" in result["scenarios"]


def test_mock_scenarios_activate(mock_orchestrator) -> None:
    from dazzle.mcp.server.handlers.mock import mock_scenarios_impl

    mock_scenario = MagicMock()
    mock_scenario.name = "happy_path"
    mock_scenario.description = "Happy path scenario"
    mock_scenario.steps = [MagicMock(), MagicMock()]
    mock_orchestrator.get_app.return_value.state.scenario_engine.load_scenario.return_value = (
        mock_scenario
    )

    with patch(_ORCH, return_value=mock_orchestrator):
        result = mock_scenarios_impl(
            action="activate", vendor="test_vendor", scenario_name="happy_path"
        )

    assert result["status"] == "activated"
    assert result["steps"] == 2


def test_mock_scenarios_deactivate(mock_orchestrator) -> None:
    from dazzle.mcp.server.handlers.mock import mock_scenarios_impl

    with patch(_ORCH, return_value=mock_orchestrator):
        result = mock_scenarios_impl(action="deactivate", vendor="test_vendor")

    assert result["status"] == "deactivated"


def test_mock_inject_error(mock_orchestrator) -> None:
    from dazzle.mcp.server.handlers.mock import mock_inject_error_impl

    with patch(_ORCH, return_value=mock_orchestrator):
        result = mock_inject_error_impl(vendor="test_vendor", operation="create_item", status=503)

    assert result["status"] == "injected"
    assert result["error_status"] == 503


def test_mock_inject_error_no_orchestrator() -> None:
    from dazzle.mcp.server.handlers.mock import mock_inject_error_impl

    with patch(_ORCH, return_value=None):
        result = mock_inject_error_impl(vendor="test_vendor", operation="create_item")

    assert "error" in result


def test_mock_scaffold_scenario() -> None:
    from dazzle.mcp.server.handlers.mock import mock_scaffold_scenario_impl

    result = mock_scaffold_scenario_impl(vendor="my_vendor", name="payment_failed")

    assert "my_vendor" in result["toml"]
    assert "payment_failed" in result["toml"]
    assert result["save_path"] == ".dazzle/scenarios/my_vendor/payment_failed.toml"
