"""Tests for HealthAggregator PostgreSQL-only health checks."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from dazzle_back.runtime.health_aggregator import (
    ComponentType,
    HealthStatus,
    create_database_check,
)


class TestCreateDatabaseCheck:
    """Tests for create_database_check (PostgreSQL-only)."""

    @pytest.mark.asyncio()
    async def test_database_url_uses_psycopg(self) -> None:
        """When database_url is provided, psycopg is used."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (1,)

        with patch("psycopg.connect", return_value=mock_conn) as mock_connect:
            check_fn = create_database_check(
                database_url="postgresql://localhost/test",
            )
            result = await check_fn()

            mock_connect.assert_called_once_with("postgresql://localhost/test")
            mock_cursor.execute.assert_called_once_with("SELECT 1")
            mock_conn.close.assert_called_once()
            assert result.status == HealthStatus.HEALTHY
            assert result.latency_ms is not None

    @pytest.mark.asyncio()
    async def test_database_url_unhealthy_on_error(self) -> None:
        """When psycopg.connect fails, returns unhealthy."""
        with patch("psycopg.connect", side_effect=Exception("Connection refused")):
            check_fn = create_database_check(
                database_url="postgresql://localhost/test",
            )
            result = await check_fn()

            assert result.status == HealthStatus.UNHEALTHY
            assert "Connection refused" in (result.message or "")

    @pytest.mark.asyncio()
    async def test_check_with_custom_name(self) -> None:
        """Custom name is used in health check result."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (1,)

        with patch("psycopg.connect", return_value=mock_conn):
            check_fn = create_database_check(
                database_url="postgresql://localhost/test",
                name="my_db",
            )
            result = await check_fn()
            assert result.name == "my_db"

    @pytest.mark.asyncio()
    async def test_healthy_check_includes_latency(self) -> None:
        """Healthy check includes positive latency."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchone.return_value = (1,)

        with patch("psycopg.connect", return_value=mock_conn):
            check_fn = create_database_check(
                database_url="postgresql://localhost/test",
            )
            result = await check_fn()

            assert result.status == HealthStatus.HEALTHY
            assert result.component_type == ComponentType.DATABASE
            assert result.latency_ms is not None
            assert result.latency_ms > 0
