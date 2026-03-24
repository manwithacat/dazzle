"""
Unit tests for EventFramework PostgreSQL support.

Tests cover:
- EventFrameworkConfig accepts database_url
- Framework selects appropriate bus based on database_url
- Connection handling for postgres mode
"""

from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dazzle_back.events.framework import EventFramework, EventFrameworkConfig


class TestEventFrameworkConfigPg:
    """Tests for EventFrameworkConfig with database_url."""

    def test_config_accepts_database_url(self) -> None:
        """Test that EventFrameworkConfig accepts database_url field."""
        config = EventFrameworkConfig(database_url="postgresql://localhost/test")
        assert config.database_url == "postgresql://localhost/test"

    def test_config_database_url_default_none(self) -> None:
        """Test that database_url defaults to None."""
        config = EventFrameworkConfig()
        assert config.database_url is None


class TestEventFrameworkPgMode:
    """Tests for EventFramework PostgreSQL mode selection."""

    def test_framework_postgres_mode_with_url(self) -> None:
        """Test framework enters Postgres mode with database_url."""
        config = EventFrameworkConfig(database_url="postgresql://localhost/test")
        framework = EventFramework(config)
        assert framework._use_postgres

    def test_framework_no_postgres_without_url(self) -> None:
        """Test framework has _use_postgres=False when database_url is None."""
        config = EventFrameworkConfig()
        framework = EventFramework(config)
        assert not framework._use_postgres

    @pytest.mark.asyncio
    async def test_start_postgres_imports_psycopg(self) -> None:
        """Test that start in postgres mode imports psycopg and PostgresBus."""
        config = EventFrameworkConfig(database_url="postgresql://localhost/test")
        framework = EventFramework(config)

        mock_conn = AsyncMock()

        # Pre-inject psycopg mock into sys.modules so import succeeds
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

        mock_pg_bus = AsyncMock()
        mock_pg_config = MagicMock()

        try:
            with (
                patch(
                    "dazzle_back.events.postgres_bus.PostgresBus",
                    return_value=mock_pg_bus,
                ),
                patch(
                    "dazzle_back.events.postgres_bus.PostgresConfig",
                    mock_pg_config,
                ),
            ):
                await framework.start()

                # Should have connected via psycopg (framework conn + publisher conn)
                assert mock_psycopg.AsyncConnection.connect.call_count >= 1

                # Bus should exist
                assert framework._bus is not None

                await framework.stop()
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
    async def test_get_connection_postgres_mode(self) -> None:
        """Test get_connection returns psycopg connection in pg mode."""
        config = EventFrameworkConfig(database_url="postgresql://localhost/test")
        framework = EventFramework(config)

        mock_conn = AsyncMock()
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
            conn = await framework.get_connection()
            assert conn is mock_conn
            mock_psycopg.AsyncConnection.connect.assert_called_once()
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
    async def test_outbox_and_inbox_created_on_start(self) -> None:
        """Test that EventOutbox and EventInbox are created on framework start."""
        config = EventFrameworkConfig(database_url="postgresql://localhost/test")
        framework = EventFramework(config)

        mock_conn = AsyncMock()
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

        mock_pg_bus = AsyncMock()

        try:
            with (
                patch(
                    "dazzle_back.events.postgres_bus.PostgresBus",
                    return_value=mock_pg_bus,
                ),
                patch(
                    "dazzle_back.events.postgres_bus.PostgresConfig",
                    MagicMock(),
                ),
            ):
                await framework.start()

                assert framework._outbox is not None
                assert framework._inbox is not None

                await framework.stop()
        finally:
            if saved_psycopg is None:
                sys.modules.pop("psycopg", None)
            else:
                sys.modules["psycopg"] = saved_psycopg
            if saved_rows is None:
                sys.modules.pop("psycopg.rows", None)
            else:
                sys.modules["psycopg.rows"] = saved_rows
