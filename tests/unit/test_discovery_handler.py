"""Tests for the MCP discovery handler."""

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def tmp_project(tmp_path: Path) -> Path:
    """Create a minimal project directory with dazzle.toml."""
    (tmp_path / "dazzle.toml").write_text('[project]\nname = "test"\n')
    (tmp_path / ".dazzle").mkdir()
    return tmp_path


# =============================================================================
# Tests: Consolidated Handler Registration
# =============================================================================


class TestDiscoveryRegistration:
    def test_registered_in_consolidated_handlers(self) -> None:
        """Discovery handler is registered in the dispatch table."""
        from dazzle.mcp.server.handlers_consolidated import CONSOLIDATED_TOOL_HANDLERS

        assert "discovery" in CONSOLIDATED_TOOL_HANDLERS

    def test_tool_definition_exists(self) -> None:
        """Discovery tool has a schema definition."""
        from dazzle.mcp.server.tools_consolidated import get_consolidated_tools

        tools = get_consolidated_tools()
        discovery_tools = [t for t in tools if t.name == "discovery"]
        assert len(discovery_tools) == 1

    def test_tool_has_operations(self) -> None:
        """Discovery tool schema has the expected operations."""
        from dazzle.mcp.server.tools_consolidated import get_consolidated_tools

        tools = get_consolidated_tools()
        discovery_tool = next(t for t in tools if t.name == "discovery")
        ops = discovery_tool.inputSchema["properties"]["operation"]["enum"]
        assert set(ops) == {
            "coherence",
        }


# =============================================================================
# Tests: Consolidated Dispatch
# =============================================================================


class TestConsolidatedDispatch:
    @patch("dazzle.mcp.server.handlers_consolidated._resolve_project")
    def test_dispatch_unknown_operation(
        self,
        mock_resolve: MagicMock,
        tmp_project: Path,
    ) -> None:
        from dazzle.mcp.server.handlers_consolidated import handle_discovery

        mock_resolve.return_value = tmp_project

        result = json.loads(asyncio.run(handle_discovery({"operation": "invalid"})))
        assert "error" in result
        assert "Unknown" in result["error"]

    @patch("dazzle.mcp.server.handlers_consolidated._resolve_project")
    def test_dispatch_no_project(self, mock_resolve: MagicMock) -> None:
        from dazzle.mcp.server.handlers_consolidated import handle_discovery

        mock_resolve.return_value = None

        result = json.loads(asyncio.run(handle_discovery({"operation": "coherence"})))
        assert "error" in result
