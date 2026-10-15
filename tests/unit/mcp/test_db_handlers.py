"""Tests for db MCP handlers."""

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.unit.mcp.conftest import install_handlers_common_real

from .._fake_pg import scalar_conn


def _import_db_handler():
    """Import db handlers directly to avoid MCP package init issues."""
    # Mock the handlers package and common module
    sys.modules.setdefault("dazzle.mcp.server.handlers", MagicMock(pytest_plugins=[]))

    install_handlers_common_real()

    # Import the module directly from file
    module_path = (
        Path(__file__).parent.parent.parent.parent
        / "src"
        / "dazzle"
        / "mcp"
        / "server"
        / "handlers"
        / "db.py"
    )
    spec = importlib.util.spec_from_file_location("dazzle.mcp.server.handlers.db", module_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["dazzle.mcp.server.handlers.db"] = mod
    spec.loader.exec_module(mod)
    return mod


_db_mod = _import_db_handler()


class TestDbStatusHandler:
    @pytest.mark.asyncio
    @patch.object(_db_mod, "get_connection")
    @patch.object(_db_mod, "load_project_appspec")
    async def test_returns_status_json(
        self, mock_load: MagicMock, mock_conn_factory: MagicMock
    ) -> None:
        appspec = MagicMock()
        e1 = MagicMock()
        e1.name = "Task"
        appspec.domain.entities = [e1]
        mock_load.return_value = appspec

        mock_conn = scalar_conn([10, "1 MB"])

        async def fake_connect(**kw: object) -> object:
            return mock_conn

        mock_conn_factory.side_effect = fake_connect

        project_path = Path("/fake/project")
        args: dict[str, object] = {"_progress": MagicMock()}
        result_str = await _db_mod.db_status_handler(project_path, args)
        result = json.loads(result_str)
        assert result["entities"] == [
            {"name": "Task", "table": "Task", "rows": 10, "error": None, "status": "ok"}
        ]
        assert result["total_rows"] == 10
        assert result["database_size"] == "1 MB"
        assert result["project_root"] == "/fake/project"


class TestDbVerifyHandler:
    @pytest.mark.asyncio
    @patch.object(_db_mod, "get_connection")
    @patch.object(_db_mod, "load_project_appspec")
    async def test_returns_verify_json(
        self, mock_load: MagicMock, mock_conn_factory: MagicMock
    ) -> None:
        appspec = MagicMock()
        appspec.domain.entities = []
        mock_load.return_value = appspec

        mock_conn = scalar_conn([])

        async def fake_connect(**kw: object) -> object:
            return mock_conn

        mock_conn_factory.side_effect = fake_connect

        project_path = Path("/fake/project")
        args: dict[str, object] = {"_progress": MagicMock()}
        result_str = await _db_mod.db_verify_handler(project_path, args)
        result = json.loads(result_str)
        assert result == {"checks": [], "total_issues": 0, "warning_count": 0, "error_count": 0}
