"""
Unit tests for VersionManager PostgreSQL support.

Tests cover:
- Constructor accepts database_url
- _connect method returns appropriate connection type (mock psycopg)
- _use_postgres flag is set correctly
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dazzle.core.process import VersionManager


class TestVersionManagerPgInit:
    """Tests for VersionManager PostgreSQL initialization."""

    def test_constructor_accepts_database_url(self) -> None:
        """Test that constructor accepts database_url parameter."""
        vm = VersionManager(db_path="test.db", database_url="postgresql://localhost/test")
        assert vm._database_url == "postgresql://localhost/test"
        assert vm._use_postgres is True

    def test_constructor_default_sqlite(self) -> None:
        """Test that constructor defaults to SQLite mode."""
        vm = VersionManager(db_path="test.db")
        assert vm._database_url is None
        assert vm._use_postgres is False

    def test_constructor_database_url_none_is_sqlite(self) -> None:
        """Test that None database_url means SQLite mode."""
        vm = VersionManager(db_path="test.db", database_url=None)
        assert vm._use_postgres is False


class TestVersionManagerPgConnect:
    """Tests for VersionManager._connect with PostgreSQL."""

    @pytest.mark.asyncio
    async def test_connect_returns_psycopg_connection(self) -> None:
        """Test that _connect returns psycopg connection in pg mode."""
        vm = VersionManager(db_path="test.db", database_url="postgresql://localhost/test")

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.fetchone = AsyncMock()
        mock_conn.fetchall = AsyncMock()
        mock_conn.commit = AsyncMock()
        mock_conn.close = AsyncMock()

        mock_psycopg = MagicMock()
        mock_async_conn_cls = MagicMock()
        mock_async_conn_cls.connect = AsyncMock(return_value=mock_conn)
        mock_psycopg.AsyncConnection = mock_async_conn_cls
        mock_rows = MagicMock()
        mock_rows.dict_row = MagicMock()
        saved_psycopg = sys.modules.get("psycopg")
        saved_rows = sys.modules.get("psycopg.rows")
        sys.modules["psycopg"] = mock_psycopg
        sys.modules["psycopg.rows"] = mock_rows

        try:
            conn = await vm._connect()
            assert conn is mock_conn
            mock_psycopg.AsyncConnection.connect.assert_called_once_with(
                "postgresql://localhost/test", row_factory=mock_rows.dict_row
            )
        finally:
            if saved_psycopg is None:
                sys.modules.pop("psycopg", None)
            else:
                sys.modules["psycopg"] = saved_psycopg
            if saved_rows is None:
                sys.modules.pop("psycopg.rows", None)
            else:
                sys.modules["psycopg.rows"] = saved_rows

    @pytest.mark.asyncio
    async def test_connect_normalizes_postgres_url(self) -> None:
        """Test that _connect normalizes postgres:// to postgresql://."""
        vm = VersionManager(db_path="test.db", database_url="postgres://localhost/test")

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.fetchone = AsyncMock()
        mock_conn.fetchall = AsyncMock()
        mock_conn.commit = AsyncMock()
        mock_conn.close = AsyncMock()

        mock_psycopg = MagicMock()
        mock_async_conn_cls = MagicMock()
        mock_async_conn_cls.connect = AsyncMock(return_value=mock_conn)
        mock_psycopg.AsyncConnection = mock_async_conn_cls
        mock_rows = MagicMock()
        mock_rows.dict_row = MagicMock()
        saved_psycopg = sys.modules.get("psycopg")
        saved_rows = sys.modules.get("psycopg.rows")
        sys.modules["psycopg"] = mock_psycopg
        sys.modules["psycopg.rows"] = mock_rows

        try:
            await vm._connect()
            mock_psycopg.AsyncConnection.connect.assert_called_once_with(
                "postgresql://localhost/test", row_factory=mock_rows.dict_row
            )
        finally:
            if saved_psycopg is None:
                sys.modules.pop("psycopg", None)
            else:
                sys.modules["psycopg"] = saved_psycopg
            if saved_rows is None:
                sys.modules.pop("psycopg.rows", None)
            else:
                sys.modules["psycopg.rows"] = saved_rows

    @pytest.mark.asyncio
    async def test_connect_returns_aiosqlite_connection(self) -> None:
        """Test that _connect returns aiosqlite connection in SQLite mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            vm = VersionManager(db_path=db_path)

            conn = await vm._connect()
            try:
                import aiosqlite

                assert isinstance(conn, aiosqlite.Connection)
            finally:
                await conn.close()


class TestVersionManagerPgInitialize:
    """Tests for VersionManager.initialize with PostgreSQL."""

    @pytest.mark.asyncio
    async def test_initialize_sqlite_still_works(self) -> None:
        """Test that SQLite initialize path still works correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.db"
            vm = VersionManager(db_path=db_path)
            await vm.initialize()
            assert vm._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_postgres_calls_execute(self) -> None:
        """Test that Postgres initialize creates tables via conn.execute."""
        vm = VersionManager(
            db_path="test.db",
            database_url="postgresql://localhost/test",
        )

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
        mock_conn.close = AsyncMock()

        with patch.object(vm, "_connect", new_callable=AsyncMock, return_value=mock_conn):
            await vm.initialize()

        assert vm._initialized is True
        # Should have called execute multiple times for CREATE TABLE and CREATE INDEX
        assert mock_conn.execute.call_count >= 3  # 3 tables + indexes
        mock_conn.close.assert_called_once()


class TestVersionManagerPgOperations:
    """Tests for VersionManager operations with PostgreSQL (mocked)."""

    @pytest.mark.asyncio
    async def test_deploy_version_postgres(self) -> None:
        """Test deploy_version in Postgres mode uses %s placeholders."""
        vm = VersionManager(
            db_path="test.db",
            database_url="postgresql://localhost/test",
        )
        vm._initialized = True  # Skip initialize

        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value=None)  # No existing version

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=mock_cursor)
        mock_conn.commit = AsyncMock()
        mock_conn.close = AsyncMock()

        with patch.object(vm, "_connect", new_callable=AsyncMock, return_value=mock_conn):
            await vm.deploy_version("v1", "hash1", {"name": "test"})

        # Should have called execute twice: once to check existence, once to insert
        assert mock_conn.execute.call_count == 2
        mock_conn.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_current_version_postgres(self) -> None:
        """Test get_current_version in Postgres mode."""
        vm = VersionManager(
            db_path="test.db",
            database_url="postgresql://localhost/test",
        )
        vm._initialized = True

        mock_cursor = AsyncMock()
        mock_cursor.fetchone = AsyncMock(return_value={"version_id": "v1"})

        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock(return_value=mock_cursor)
        mock_conn.close = AsyncMock()

        with patch.object(vm, "_connect", new_callable=AsyncMock, return_value=mock_conn):
            result = await vm.get_current_version()

        assert result == "v1"
