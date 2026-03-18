"""Tests for db MCP handlers."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch


def _import_db_handler():
    """Import db handlers directly to avoid MCP package init issues."""
    # Mock the handlers package and common module
    sys.modules.setdefault("dazzle.mcp.server.handlers", MagicMock(pytest_plugins=[]))

    common_mock = ModuleType("dazzle.mcp.server.handlers.common")

    def _extract_progress(args=None):
        ctx = MagicMock()
        ctx.log_sync = MagicMock()
        return ctx

    def _load_project_appspec(project_root):
        return MagicMock()

    def _wrap_handler_errors(fn):
        from functools import wraps

        @wraps(fn)
        def wrapper(*a, **kw):
            try:
                return fn(*a, **kw)
            except Exception as exc:
                return json.dumps({"error": str(exc)})

        return wrapper

    def _error_response(msg):
        return json.dumps({"error": msg})

    common_mock.error_response = _error_response
    common_mock.extract_progress = _extract_progress
    common_mock.load_project_appspec = _load_project_appspec
    common_mock.wrap_handler_errors = _wrap_handler_errors
    sys.modules["dazzle.mcp.server.handlers.common"] = common_mock

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
    @patch.object(_db_mod, "get_connection")
    @patch.object(_db_mod, "load_project_appspec")
    def test_returns_status_json(self, mock_load: MagicMock, mock_conn_factory: MagicMock) -> None:
        appspec = MagicMock()
        e1 = MagicMock()
        e1.name = "Task"
        appspec.domain.entities = [e1]
        mock_load.return_value = appspec

        mock_conn = AsyncMock()
        mock_conn.fetchval = AsyncMock(side_effect=[10, "1 MB"])
        mock_conn.close = AsyncMock()

        async def fake_connect(**kw: object) -> AsyncMock:
            return mock_conn

        mock_conn_factory.side_effect = fake_connect

        project_path = Path("/fake/project")
        args: dict[str, object] = {"_progress": MagicMock()}
        result_str = _db_mod.db_status_handler(project_path, args)
        result = json.loads(result_str)
        assert "entities" in result or "total_rows" in result


class TestDbVerifyHandler:
    @patch.object(_db_mod, "get_connection")
    @patch.object(_db_mod, "load_project_appspec")
    def test_returns_verify_json(self, mock_load: MagicMock, mock_conn_factory: MagicMock) -> None:
        appspec = MagicMock()
        appspec.domain.entities = []
        mock_load.return_value = appspec

        mock_conn = AsyncMock()
        mock_conn.close = AsyncMock()

        async def fake_connect(**kw: object) -> AsyncMock:
            return mock_conn

        mock_conn_factory.side_effect = fake_connect

        project_path = Path("/fake/project")
        args: dict[str, object] = {"_progress": MagicMock()}
        result_str = _db_mod.db_verify_handler(project_path, args)
        result = json.loads(result_str)
        assert "checks" in result
