"""
Unit tests for LiteProcessAdapter PostgreSQL support.

Tests cover:
- Constructor accepts database_url
- schema_postgres.sql exists
- Initialization handles Postgres mode
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.core.process.lite_adapter import LiteProcessAdapter


class TestLiteProcessAdapterPgInit:
    """Tests for LiteProcessAdapter PostgreSQL initialization."""

    def test_constructor_accepts_database_url(self) -> None:
        """Test that constructor accepts database_url parameter."""
        adapter = LiteProcessAdapter(database_url="postgresql://localhost/test")
        assert adapter._database_url == "postgresql://localhost/test"
        assert adapter._use_postgres is True

    def test_constructor_default_sqlite(self) -> None:
        """Test that constructor defaults to SQLite mode."""
        adapter = LiteProcessAdapter()
        assert adapter._database_url is None
        assert adapter._use_postgres is False

    def test_constructor_database_url_none_is_sqlite(self) -> None:
        """Test that None database_url means SQLite mode."""
        adapter = LiteProcessAdapter(database_url=None)
        assert adapter._use_postgres is False


class TestSchemaPostgresFile:
    """Tests for schema_postgres.sql file."""

    def test_schema_postgres_sql_exists(self) -> None:
        """Test that schema_postgres.sql file exists."""
        schema_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "dazzle"
            / "core"
            / "process"
            / "schema_postgres.sql"
        )
        assert schema_path.exists(), f"schema_postgres.sql not found at {schema_path}"

    def test_schema_postgres_sql_has_tables(self) -> None:
        """Test that schema_postgres.sql contains required table definitions."""
        schema_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "dazzle"
            / "core"
            / "process"
            / "schema_postgres.sql"
        )
        schema = schema_path.read_text()

        assert "CREATE TABLE IF NOT EXISTS process_runs" in schema
        assert "CREATE TABLE IF NOT EXISTS process_tasks" in schema
        assert "CREATE TABLE IF NOT EXISTS schedule_runs" in schema
        assert "CREATE TABLE IF NOT EXISTS step_executions" in schema
        assert "CREATE TABLE IF NOT EXISTS process_signals" in schema
        assert "CREATE TABLE IF NOT EXISTS process_events" in schema
        assert "CREATE TABLE IF NOT EXISTS dsl_versions" in schema
        assert "CREATE TABLE IF NOT EXISTS version_migrations" in schema

    def test_schema_postgres_sql_no_autoincrement(self) -> None:
        """Test that schema_postgres.sql does not use AUTOINCREMENT (SQLite-ism)."""
        schema_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "dazzle"
            / "core"
            / "process"
            / "schema_postgres.sql"
        )
        schema = schema_path.read_text()

        assert "AUTOINCREMENT" not in schema, "PostgreSQL schema should not use AUTOINCREMENT"

    def test_schema_postgres_sql_uses_serial(self) -> None:
        """Test that schema_postgres.sql uses SERIAL for auto-increment columns."""
        schema_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "dazzle"
            / "core"
            / "process"
            / "schema_postgres.sql"
        )
        schema = schema_path.read_text()

        assert "SERIAL" in schema, "PostgreSQL schema should use SERIAL for auto-increment"

    def test_schema_postgres_no_triggers(self) -> None:
        """Test that schema_postgres.sql does not use SQLite CREATE TRIGGER syntax."""
        schema_path = (
            Path(__file__).parent.parent.parent
            / "src"
            / "dazzle"
            / "core"
            / "process"
            / "schema_postgres.sql"
        )
        schema = schema_path.read_text()

        # SQLite trigger syntax won't work in PostgreSQL
        assert "CREATE TRIGGER" not in schema or "BEGIN" not in schema, (
            "PostgreSQL schema should not use SQLite TRIGGER syntax"
        )


class TestLiteProcessAdapterPgInitialize:
    """Tests for LiteProcessAdapter.initialize with PostgreSQL."""

    @pytest.mark.asyncio
    async def test_initialize_sqlite_still_works(self) -> None:
        """Test that SQLite initialize path still works correctly."""
        adapter = LiteProcessAdapter(db_path=":memory:")
        await adapter.initialize()
        assert adapter._db is not None
        await adapter.shutdown()

    @pytest.mark.asyncio
    async def test_initialize_postgres_creates_schema(self) -> None:
        """Test that Postgres initialize loads and executes schema_postgres.sql."""
        adapter = LiteProcessAdapter(database_url="postgresql://localhost/test")

        mock_pg_conn = AsyncMock()
        mock_pg_conn.execute = AsyncMock()
        mock_pg_conn.close = AsyncMock()

        mock_psycopg = MagicMock()
        mock_async_conn_cls = MagicMock()
        mock_async_conn_cls.connect = AsyncMock(return_value=mock_pg_conn)
        mock_psycopg.AsyncConnection = mock_async_conn_cls
        saved = sys.modules.get("psycopg")
        sys.modules["psycopg"] = mock_psycopg

        try:
            await adapter.initialize()

            # Should have executed the postgres schema
            mock_pg_conn.execute.assert_called_once()
            mock_pg_conn.close.assert_called_once()

            # Should have connected with autocommit=True
            mock_psycopg.AsyncConnection.connect.assert_called_once_with(
                "postgresql://localhost/test", autocommit=True
            )

            # Should still have an aiosqlite _db for runtime operations
            assert adapter._db is not None

            await adapter.shutdown()
        finally:
            if saved is None:
                sys.modules.pop("psycopg", None)
            else:
                sys.modules["psycopg"] = saved

    @pytest.mark.asyncio
    async def test_initialize_postgres_normalizes_url(self) -> None:
        """Test that postgres:// is normalized to postgresql://."""
        adapter = LiteProcessAdapter(database_url="postgres://localhost/test")

        mock_pg_conn = AsyncMock()
        mock_pg_conn.execute = AsyncMock()
        mock_pg_conn.close = AsyncMock()

        mock_psycopg = MagicMock()
        mock_async_conn_cls = MagicMock()
        mock_async_conn_cls.connect = AsyncMock(return_value=mock_pg_conn)
        mock_psycopg.AsyncConnection = mock_async_conn_cls
        saved = sys.modules.get("psycopg")
        sys.modules["psycopg"] = mock_psycopg

        try:
            await adapter.initialize()
            mock_psycopg.AsyncConnection.connect.assert_called_once_with(
                "postgresql://localhost/test", autocommit=True
            )
            await adapter.shutdown()
        finally:
            if saved is None:
                sys.modules.pop("psycopg", None)
            else:
                sys.modules["psycopg"] = saved
