"""Tests for PostgresBackend connection pooling (#438)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def _pg_backend():
    """Create a PostgresBackend with a fake URL (no real DB needed)."""
    from dazzle_back.runtime.pg_backend import PostgresBackend

    return PostgresBackend("postgresql://localhost:5432/test_db")


class TestPoolLifecycle:
    """Pool open/close lifecycle."""

    def test_pool_is_none_by_default(self, _pg_backend):
        assert _pg_backend._pool is None

    @patch("psycopg_pool.ConnectionPool")
    def test_open_pool_creates_pool(self, mock_pool_cls, _pg_backend):
        """open_pool() creates a ConnectionPool with the correct args."""
        _pg_backend.open_pool(min_size=3, max_size=20)

        mock_pool_cls.assert_called_once()
        call_kwargs = mock_pool_cls.call_args
        assert call_kwargs[0][0] == "postgresql://localhost:5432/test_db"
        assert call_kwargs[1]["min_size"] == 3
        assert call_kwargs[1]["max_size"] == 20
        assert call_kwargs[1]["open"] is True
        assert _pg_backend._pool is not None

    def test_close_pool_when_no_pool(self, _pg_backend):
        """close_pool() is a no-op when no pool is open."""
        _pg_backend.close_pool()  # should not raise
        assert _pg_backend._pool is None

    def test_close_pool_closes_and_clears(self, _pg_backend):
        """close_pool() calls close() on the pool and sets it to None."""
        mock_pool = MagicMock()
        _pg_backend._pool = mock_pool

        _pg_backend.close_pool()

        mock_pool.close.assert_called_once()
        assert _pg_backend._pool is None


class TestConnectionFallback:
    """connection() behavior with and without pool."""

    @patch("psycopg.connect")
    def test_connection_without_pool_uses_direct_connect(self, mock_connect, _pg_backend):
        """Without pool, connection() opens a direct psycopg connection."""
        mock_conn = MagicMock()
        mock_conn.closed = False
        mock_connect.return_value = mock_conn

        with _pg_backend.connection() as conn:
            assert conn is not None

        mock_connect.assert_called_once()
        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()

    def test_connection_with_pool_uses_pool(self, _pg_backend):
        """With pool open, connection() leases from the pool."""
        mock_pool = MagicMock()
        mock_pool_conn = MagicMock()
        mock_pool.connection.return_value.__enter__ = MagicMock(return_value=mock_pool_conn)
        mock_pool.connection.return_value.__exit__ = MagicMock(return_value=False)
        _pg_backend._pool = mock_pool

        with _pg_backend.connection() as conn:
            assert conn is not None

        mock_pool.connection.assert_called_once()

    def test_connection_with_pool_sets_search_path(self, _pg_backend):
        """Pool connections get search_path set on each checkout."""
        _pg_backend.search_path = "tenant_abc"
        mock_pool = MagicMock()
        mock_pool_conn = MagicMock()
        mock_pool.connection.return_value.__enter__ = MagicMock(return_value=mock_pool_conn)
        mock_pool.connection.return_value.__exit__ = MagicMock(return_value=False)
        _pg_backend._pool = mock_pool

        with _pg_backend.connection():
            pass

        mock_pool_conn.execute.assert_called_with("SET search_path TO tenant_abc, public")


class TestPoolEnvConfig:
    """Environment variable configuration for pool size."""

    @patch.dict("os.environ", {"DAZZLE_DB_POOL_MIN": "5", "DAZZLE_DB_POOL_MAX": "25"})
    def test_env_vars_are_read(self):
        """Pool size env vars are parsed correctly."""
        import os

        assert int(os.environ.get("DAZZLE_DB_POOL_MIN", "2")) == 5
        assert int(os.environ.get("DAZZLE_DB_POOL_MAX", "10")) == 25

    @patch.dict("os.environ", {}, clear=False)
    def test_env_vars_default(self):
        """Default pool sizes when env vars are not set."""
        import os

        # Remove if present
        os.environ.pop("DAZZLE_DB_POOL_MIN", None)
        os.environ.pop("DAZZLE_DB_POOL_MAX", None)
        assert int(os.environ.get("DAZZLE_DB_POOL_MIN", "2")) == 2
        assert int(os.environ.get("DAZZLE_DB_POOL_MAX", "10")) == 10
