"""
Unit tests for DeviceRegistry PostgreSQL-only support.

Tests verify:
- Constructor accepts database_url parameter
- Heroku URL normalization
- PostgreSQL table initialization with BOOLEAN type
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# =========================================================================
# Initialization tests
# =========================================================================


class TestDeviceRegistryInit:
    """Tests for initialization."""

    def test_normalizes_heroku_postgres_url(self):
        """Verify postgres:// is normalized to postgresql://."""
        with patch("dazzle_back.runtime.device_registry.DeviceRegistry._init_db"):
            from dazzle_back.runtime.device_registry import DeviceRegistry

            reg = DeviceRegistry(database_url="postgres://user:pass@host/db")
            assert reg._database_url == "postgresql://user:pass@host/db"

    def test_postgresql_url_unchanged(self):
        """Verify postgresql:// URLs are not modified."""
        with patch("dazzle_back.runtime.device_registry.DeviceRegistry._init_db"):
            from dazzle_back.runtime.device_registry import DeviceRegistry

            reg = DeviceRegistry(database_url="postgresql://user:pass@host/db")
            assert reg._database_url == "postgresql://user:pass@host/db"


# =========================================================================
# PostgreSQL table init tests
# =========================================================================


class TestDeviceRegistryPostgresInit:
    """Tests for PostgreSQL table initialization."""

    def test_init_db_creates_table(self):
        """Verify _init_db creates devices table."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch("dazzle_back.runtime.device_registry.DeviceRegistry._init_db"):
            from dazzle_back.runtime.device_registry import DeviceRegistry

            reg = DeviceRegistry(database_url="postgresql://localhost/test")

        with patch.object(reg, "_get_connection", return_value=mock_conn):
            DeviceRegistry._init_db(reg)

        calls = mock_cursor.execute.call_args_list
        create_table = any("CREATE TABLE IF NOT EXISTS devices" in str(c) for c in calls)
        assert create_table, "devices table should be created"

    def test_init_db_uses_boolean_type(self):
        """Verify _init_db uses BOOLEAN DEFAULT TRUE for is_active."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch("dazzle_back.runtime.device_registry.DeviceRegistry._init_db"):
            from dazzle_back.runtime.device_registry import DeviceRegistry

            reg = DeviceRegistry(database_url="postgresql://localhost/test")

        with patch.object(reg, "_get_connection", return_value=mock_conn):
            DeviceRegistry._init_db(reg)

        calls = mock_cursor.execute.call_args_list
        create_sql = [str(c) for c in calls if "CREATE TABLE" in str(c)]
        assert any("BOOLEAN DEFAULT TRUE" in s for s in create_sql), (
            "Postgres should use BOOLEAN DEFAULT TRUE"
        )

    def test_init_db_creates_indexes(self):
        """Verify _init_db creates required indexes."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch("dazzle_back.runtime.device_registry.DeviceRegistry._init_db"):
            from dazzle_back.runtime.device_registry import DeviceRegistry

            reg = DeviceRegistry(database_url="postgresql://localhost/test")

        with patch.object(reg, "_get_connection", return_value=mock_conn):
            DeviceRegistry._init_db(reg)

        call_strs = [str(c) for c in mock_cursor.execute.call_args_list]
        assert any("idx_devices_user_id" in s for s in call_strs)
        assert any("idx_devices_platform" in s for s in call_strs)
        assert any("idx_devices_active" in s for s in call_strs)

    def test_init_db_commits_and_closes(self):
        """Verify _init_db commits and closes connection."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch("dazzle_back.runtime.device_registry.DeviceRegistry._init_db"):
            from dazzle_back.runtime.device_registry import DeviceRegistry

            reg = DeviceRegistry(database_url="postgresql://localhost/test")

        with patch.object(reg, "_get_connection", return_value=mock_conn):
            DeviceRegistry._init_db(reg)

        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()
