"""
Unit tests for DeviceRegistry dual-backend (SQLite + PostgreSQL) support.

Tests verify:
- Constructor accepts database_url parameter
- SQLite mode still works (functional tests using tmp_path)
- Postgres mode sets correct flags (unit tests without actual Postgres)
- _ph returns correct placeholder per backend
- _bool_to_db works correctly per backend
- PostgreSQL table initialization with BOOLEAN type
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

# =========================================================================
# Initialization tests
# =========================================================================


class TestDeviceRegistryInit:
    """Tests for dual-backend initialization."""

    def test_uses_postgres_when_database_url_provided(self):
        """Verify _use_postgres is True when database_url is provided."""
        with patch("dazzle_back.runtime.device_registry.DeviceRegistry._init_db"):
            from dazzle_back.runtime.device_registry import DeviceRegistry

            reg = DeviceRegistry(database_url="postgresql://localhost/test")
            assert reg._use_postgres is True

    def test_uses_sqlite_when_no_database_url(self, tmp_path):
        """Verify _use_postgres is False when only db_path is provided."""
        from dazzle_back.runtime.device_registry import DeviceRegistry

        reg = DeviceRegistry(db_path=tmp_path / "devices.db")
        assert reg._use_postgres is False

    def test_normalizes_heroku_postgres_url(self):
        """Verify postgres:// is normalized to postgresql://."""
        with patch("dazzle_back.runtime.device_registry.DeviceRegistry._init_db"):
            from dazzle_back.runtime.device_registry import DeviceRegistry

            reg = DeviceRegistry(database_url="postgres://user:pass@host/db")
            assert reg._pg_url == "postgresql://user:pass@host/db"

    def test_postgresql_url_unchanged(self):
        """Verify postgresql:// URLs are not modified."""
        with patch("dazzle_back.runtime.device_registry.DeviceRegistry._init_db"):
            from dazzle_back.runtime.device_registry import DeviceRegistry

            reg = DeviceRegistry(database_url="postgresql://user:pass@host/db")
            assert reg._pg_url == "postgresql://user:pass@host/db"


# =========================================================================
# Placeholder and boolean conversion tests
# =========================================================================


class TestDeviceRegistryPlaceholders:
    """Tests for placeholder conversion."""

    def test_ph_returns_percent_s_for_postgres(self):
        """Verify _ph returns %s for PostgreSQL."""
        with patch("dazzle_back.runtime.device_registry.DeviceRegistry._init_db"):
            from dazzle_back.runtime.device_registry import DeviceRegistry

            reg = DeviceRegistry(database_url="postgresql://localhost/test")
            assert reg._ph == "%s"

    def test_ph_returns_question_mark_for_sqlite(self, tmp_path):
        """Verify _ph returns ? for SQLite."""
        from dazzle_back.runtime.device_registry import DeviceRegistry

        reg = DeviceRegistry(db_path=tmp_path / "devices.db")
        assert reg._ph == "?"


class TestDeviceRegistryBoolConversion:
    """Tests for boolean value conversion."""

    def test_bool_to_db_postgres_true(self):
        """Ensure True stays True for PostgreSQL."""
        with patch("dazzle_back.runtime.device_registry.DeviceRegistry._init_db"):
            from dazzle_back.runtime.device_registry import DeviceRegistry

            reg = DeviceRegistry(database_url="postgresql://localhost/test")
            assert reg._bool_to_db(True) is True

    def test_bool_to_db_postgres_false(self):
        """Ensure False stays False for PostgreSQL."""
        with patch("dazzle_back.runtime.device_registry.DeviceRegistry._init_db"):
            from dazzle_back.runtime.device_registry import DeviceRegistry

            reg = DeviceRegistry(database_url="postgresql://localhost/test")
            assert reg._bool_to_db(False) is False

    def test_bool_to_db_sqlite_true(self, tmp_path):
        """Ensure True becomes 1 for SQLite."""
        from dazzle_back.runtime.device_registry import DeviceRegistry

        reg = DeviceRegistry(db_path=tmp_path / "devices.db")
        assert reg._bool_to_db(True) == 1

    def test_bool_to_db_sqlite_false(self, tmp_path):
        """Ensure False becomes 0 for SQLite."""
        from dazzle_back.runtime.device_registry import DeviceRegistry

        reg = DeviceRegistry(db_path=tmp_path / "devices.db")
        assert reg._bool_to_db(False) == 0


# =========================================================================
# Backend type tests
# =========================================================================


class TestDeviceRegistryBackendType:
    """Tests for backend_type property."""

    def test_backend_type_postgres(self):
        """Verify backend_type returns 'postgres' for PostgreSQL."""
        with patch("dazzle_back.runtime.device_registry.DeviceRegistry._init_db"):
            from dazzle_back.runtime.device_registry import DeviceRegistry

            reg = DeviceRegistry(database_url="postgresql://localhost/test")
            assert reg.backend_type == "postgres"

    def test_backend_type_sqlite(self, tmp_path):
        """Verify backend_type returns 'sqlite' for SQLite."""
        from dazzle_back.runtime.device_registry import DeviceRegistry

        reg = DeviceRegistry(db_path=tmp_path / "devices.db")
        assert reg.backend_type == "sqlite"


# =========================================================================
# PostgreSQL table init tests
# =========================================================================


class TestDeviceRegistryPostgresInit:
    """Tests for PostgreSQL table initialization."""

    @pytest.fixture
    def mock_psycopg(self):
        """Mock psycopg module for tests."""
        import sys

        mock_pg = MagicMock()
        mock_rows = MagicMock()
        mock_rows.dict_row = MagicMock()

        old_pg = sys.modules.get("psycopg")
        old_rows = sys.modules.get("psycopg.rows")

        sys.modules["psycopg"] = mock_pg
        sys.modules["psycopg.rows"] = mock_rows

        yield mock_pg

        if old_pg:
            sys.modules["psycopg"] = old_pg
        else:
            sys.modules.pop("psycopg", None)

        if old_rows:
            sys.modules["psycopg.rows"] = old_rows
        else:
            sys.modules.pop("psycopg.rows", None)

    def test_init_postgres_db_creates_table(self, mock_psycopg):
        """Verify _init_postgres_db creates devices table."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        with patch("dazzle_back.runtime.device_registry.DeviceRegistry._init_db"):
            from dazzle_back.runtime.device_registry import DeviceRegistry

            reg = DeviceRegistry(database_url="postgresql://localhost/test")
            reg._init_postgres_db()

        calls = mock_cursor.execute.call_args_list
        create_table = any("CREATE TABLE IF NOT EXISTS devices" in str(c) for c in calls)
        assert create_table, "devices table should be created"

    def test_init_postgres_db_uses_boolean_type(self, mock_psycopg):
        """Verify _init_postgres_db uses BOOLEAN DEFAULT TRUE for is_active."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        with patch("dazzle_back.runtime.device_registry.DeviceRegistry._init_db"):
            from dazzle_back.runtime.device_registry import DeviceRegistry

            reg = DeviceRegistry(database_url="postgresql://localhost/test")
            reg._init_postgres_db()

        calls = mock_cursor.execute.call_args_list
        create_sql = [str(c) for c in calls if "CREATE TABLE" in str(c)]
        assert any("BOOLEAN DEFAULT TRUE" in s for s in create_sql), (
            "Postgres should use BOOLEAN DEFAULT TRUE"
        )

    def test_init_postgres_db_creates_indexes(self, mock_psycopg):
        """Verify _init_postgres_db creates required indexes."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        with patch("dazzle_back.runtime.device_registry.DeviceRegistry._init_db"):
            from dazzle_back.runtime.device_registry import DeviceRegistry

            reg = DeviceRegistry(database_url="postgresql://localhost/test")
            reg._init_postgres_db()

        call_strs = [str(c) for c in mock_cursor.execute.call_args_list]
        assert any("idx_devices_user_id" in s for s in call_strs)
        assert any("idx_devices_platform" in s for s in call_strs)
        assert any("idx_devices_active" in s for s in call_strs)

    def test_init_postgres_db_commits_and_closes(self, mock_psycopg):
        """Verify _init_postgres_db commits and closes connection."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        with patch("dazzle_back.runtime.device_registry.DeviceRegistry._init_db"):
            from dazzle_back.runtime.device_registry import DeviceRegistry

            reg = DeviceRegistry(database_url="postgresql://localhost/test")
            reg._init_postgres_db()

        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()


# =========================================================================
# SQLite functional tests
# =========================================================================


class TestDeviceRegistrySQLiteFunctional:
    """Functional tests using actual SQLite backend."""

    @pytest.fixture
    def registry(self, tmp_path):
        """Create a SQLite-backed DeviceRegistry."""
        from dazzle_back.runtime.device_registry import DeviceRegistry

        return DeviceRegistry(db_path=tmp_path / "devices.db")

    def test_register_device(self, registry):
        """Device can be registered."""
        from dazzle_back.runtime.device_registry import DevicePlatform

        user_id = uuid4()
        device = registry.register_device(
            user_id=user_id,
            platform=DevicePlatform.IOS,
            push_token="token-abc",
            device_name="iPhone 15",
        )
        assert device.user_id == user_id
        assert device.platform == DevicePlatform.IOS
        assert device.push_token == "token-abc"
        assert device.device_name == "iPhone 15"
        assert device.is_active is True

    def test_register_device_updates_existing(self, registry):
        """Re-registering same push token updates existing record."""
        from dazzle_back.runtime.device_registry import DevicePlatform

        user_id = uuid4()
        d1 = registry.register_device(
            user_id=user_id,
            platform=DevicePlatform.IOS,
            push_token="token-abc",
            device_name="Old Name",
        )
        d2 = registry.register_device(
            user_id=user_id,
            platform=DevicePlatform.IOS,
            push_token="token-abc",
            device_name="New Name",
        )
        assert d2.id == d1.id
        assert d2.device_name == "New Name"

    def test_get_user_devices(self, registry):
        """get_user_devices returns active devices for user."""
        from dazzle_back.runtime.device_registry import DevicePlatform

        user_id = uuid4()
        registry.register_device(
            user_id=user_id,
            platform=DevicePlatform.IOS,
            push_token="token-1",
        )
        registry.register_device(
            user_id=user_id,
            platform=DevicePlatform.ANDROID,
            push_token="token-2",
        )
        devices = registry.get_user_devices(user_id)
        assert len(devices) == 2

    def test_get_user_devices_platform_filter(self, registry):
        """get_user_devices can filter by platform."""
        from dazzle_back.runtime.device_registry import DevicePlatform

        user_id = uuid4()
        registry.register_device(user_id=user_id, platform=DevicePlatform.IOS, push_token="token-1")
        registry.register_device(
            user_id=user_id, platform=DevicePlatform.ANDROID, push_token="token-2"
        )
        ios_devices = registry.get_user_devices(user_id, platform=DevicePlatform.IOS)
        assert len(ios_devices) == 1
        assert ios_devices[0].platform == DevicePlatform.IOS

    def test_get_device(self, registry):
        """get_device retrieves a specific device by ID."""
        from dazzle_back.runtime.device_registry import DevicePlatform

        user_id = uuid4()
        device = registry.register_device(
            user_id=user_id, platform=DevicePlatform.WEB, push_token="token-web"
        )
        fetched = registry.get_device(device.id)
        assert fetched is not None
        assert fetched.id == device.id
        assert fetched.push_token == "token-web"

    def test_get_device_not_found(self, registry):
        """get_device returns None for unknown ID."""
        assert registry.get_device("nonexistent") is None

    def test_unregister_device(self, registry):
        """unregister_device marks device as inactive."""
        from dazzle_back.runtime.device_registry import DevicePlatform

        user_id = uuid4()
        device = registry.register_device(
            user_id=user_id, platform=DevicePlatform.IOS, push_token="token-1"
        )
        assert registry.unregister_device(device.id, user_id) is True
        # Should not appear in active devices
        assert len(registry.get_user_devices(user_id)) == 0

    def test_unregister_device_wrong_user(self, registry):
        """unregister_device fails with wrong user_id."""
        from dazzle_back.runtime.device_registry import DevicePlatform

        user_id = uuid4()
        other_user = uuid4()
        device = registry.register_device(
            user_id=user_id, platform=DevicePlatform.IOS, push_token="token-1"
        )
        assert registry.unregister_device(device.id, other_user) is False

    def test_mark_device_used(self, registry):
        """mark_device_used updates last_used_at."""
        from dazzle_back.runtime.device_registry import DevicePlatform

        user_id = uuid4()
        device = registry.register_device(
            user_id=user_id, platform=DevicePlatform.IOS, push_token="token-1"
        )
        assert registry.mark_device_used(device.id) is True

    def test_invalidate_token(self, registry):
        """invalidate_token marks devices with that token as inactive."""
        from dazzle_back.runtime.device_registry import DevicePlatform

        user_id = uuid4()
        registry.register_device(
            user_id=user_id, platform=DevicePlatform.IOS, push_token="bad-token"
        )
        count = registry.invalidate_token("bad-token")
        assert count == 1
        assert len(registry.get_user_devices(user_id)) == 0

    def test_cleanup_inactive(self, registry):
        """cleanup_inactive removes old inactive devices."""
        from dazzle_back.runtime.device_registry import DevicePlatform

        user_id = uuid4()
        device = registry.register_device(
            user_id=user_id, platform=DevicePlatform.IOS, push_token="token-1"
        )
        # Unregister and backdate created_at
        registry.unregister_device(device.id)
        past = (datetime.now(UTC) - timedelta(days=100)).isoformat()
        conn = registry._get_connection()
        conn.execute(
            "UPDATE devices SET created_at = ? WHERE id = ?",
            (past, device.id),
        )
        conn.commit()
        conn.close()

        removed = registry.cleanup_inactive(older_than_days=90)
        assert removed == 1
