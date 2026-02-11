"""Tests for MCP pre-flight server reachability check."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import httpx

from dazzle.mcp.server.handlers.preflight import check_server_reachable


class TestCheckServerReachable:
    """Tests for check_server_reachable."""

    def test_returns_none_when_server_ok(self):
        """Reachable server returns None."""
        with patch.object(httpx, "Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
            result = check_server_reachable("http://localhost:3000")
            assert result is None

    def test_returns_error_on_connect_error(self):
        """Unreachable server returns error JSON."""
        with patch.object(httpx, "Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get.side_effect = httpx.ConnectError("Connection refused")
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
            result = check_server_reachable("http://localhost:3000")
            assert result is not None
            data = json.loads(result)
            assert "error" in data
            assert "not reachable" in data["error"]

    def test_returns_error_on_timeout(self):
        """Timed-out server returns error JSON."""
        with patch.object(httpx, "Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get.side_effect = httpx.TimeoutException("Timed out")
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
            result = check_server_reachable("http://localhost:3000")
            assert result is not None
            data = json.loads(result)
            assert "timed out" in data["error"]

    def test_returns_none_on_unexpected_error(self):
        """Unexpected exceptions don't block."""
        with patch.object(httpx, "Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get.side_effect = RuntimeError("Weird error")
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
            result = check_server_reachable("http://localhost:3000")
            assert result is None

    def test_custom_timeout(self):
        """Custom timeout is passed through."""
        with patch.object(httpx, "Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
            check_server_reachable("http://localhost:3000", timeout=10.0)
            mock_client_cls.assert_called_once_with(timeout=10.0)

    def test_url_included_in_error(self):
        """Error message includes the target URL."""
        with patch.object(httpx, "Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.get.side_effect = httpx.ConnectError("refused")
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=mock_client)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
            result = check_server_reachable("http://example.com:8080")
            assert result is not None
            data = json.loads(result)
            assert "example.com:8080" in data["error"]
            assert "hint" in data

    def test_graceful_when_httpx_missing(self):
        """When httpx is not importable, returns None (skip check)."""
        with patch.dict("sys.modules", {"httpx": None}):
            result = check_server_reachable("http://localhost:3000")
            assert result is None
