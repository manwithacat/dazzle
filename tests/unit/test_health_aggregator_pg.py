"""Tests for HealthAggregator PostgreSQL dual-backend support."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dazzle_back.runtime.health_aggregator import (
    ComponentType,
    HealthStatus,
    create_database_check,
)


class TestCreateDatabaseCheck:
    """Tests for create_database_check with both backends."""

    @pytest.mark.asyncio()
    async def test_sqlite_check_healthy(self, tmp_path: Path) -> None:
        """SQLite health check returns healthy for a valid database."""
        import sqlite3

        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER)")
        conn.close()

        check_fn = create_database_check(db_path)
        result = await check_fn()

        assert result.status == HealthStatus.HEALTHY
        assert result.component_type == ComponentType.DATABASE
        assert result.latency_ms is not None
        assert result.latency_ms > 0

    @pytest.mark.asyncio()
    async def test_sqlite_check_with_custom_name(self, tmp_path: Path) -> None:
        import sqlite3

        db_path = str(tmp_path / "test.db")
        sqlite3.connect(db_path).close()

        check_fn = create_database_check(db_path, name="my_db")
        result = await check_fn()
        assert result.name == "my_db"

    @pytest.mark.asyncio()
    async def test_sqlite_check_unhealthy(self) -> None:
        """SQLite health check returns unhealthy for non-existent path."""
        check_fn = create_database_check("/nonexistent/path/to/db.sqlite")
        # sqlite3 will create the file if it can, but the directory doesn't exist
        # so this should fail
        result = await check_fn()
        assert result.status == HealthStatus.UNHEALTHY

    @pytest.mark.asyncio()
    async def test_database_url_uses_psycopg(self) -> None:
        """When database_url is provided, psycopg is used instead of sqlite3."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (1,)

        mock_psycopg = MagicMock()
        mock_psycopg.connect.return_value = mock_conn

        import sys

        with patch.dict(sys.modules, {"psycopg": mock_psycopg}):
            check_fn = create_database_check(
                db_path="unused",
                database_url="postgresql://localhost/test",
            )
            result = await check_fn()

            mock_psycopg.connect.assert_called_once_with("postgresql://localhost/test")
            mock_cursor.execute.assert_called_once_with("SELECT 1")
            mock_conn.close.assert_called_once()
            assert result.status == HealthStatus.HEALTHY
            assert result.latency_ms is not None

    @pytest.mark.asyncio()
    async def test_database_url_unhealthy_on_error(self) -> None:
        """When psycopg.connect fails, returns unhealthy."""
        mock_psycopg = MagicMock()
        mock_psycopg.connect.side_effect = Exception("Connection refused")

        import sys

        with patch.dict(sys.modules, {"psycopg": mock_psycopg}):
            check_fn = create_database_check(
                db_path="unused",
                database_url="postgresql://localhost/test",
            )
            result = await check_fn()

            assert result.status == HealthStatus.UNHEALTHY
            assert "Connection refused" in (result.message or "")

    @pytest.mark.asyncio()
    async def test_no_database_url_uses_sqlite(self, tmp_path: Path) -> None:
        """Without database_url, sqlite3 is used."""
        import sqlite3

        db_path = str(tmp_path / "test.db")
        sqlite3.connect(db_path).close()

        check_fn = create_database_check(db_path, database_url=None)
        result = await check_fn()
        assert result.status == HealthStatus.HEALTHY
