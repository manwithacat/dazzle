"""
Unit tests for PostgreSQL-specific auth code paths.

These tests use mocks to test PostgreSQL-specific behavior without requiring
an actual PostgreSQL database. They cover:
- dict_row row handling
- PostgreSQL table initialization
- Connection handling
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest


class MockDictRow(dict):
    """
    Mock psycopg dict_row result.

    With psycopg v3 and row_factory=dict_row, rows are returned as plain dicts.
    """

    def __init__(self, data: dict):
        super().__init__(data)


class TestAuthStoreInit:
    """Tests for AuthStore initialization."""

    def test_normalizes_heroku_postgres_url(self):
        """Verify postgres:// is normalized to postgresql://."""
        with patch("dazzle_back.runtime.auth.AuthStore._init_db"):
            from dazzle_back.runtime.auth import AuthStore

            store = AuthStore(database_url="postgres://user:pass@host/db")
            assert store._database_url == "postgresql://user:pass@host/db"

    def test_postgresql_url_unchanged(self):
        """Verify postgresql:// URLs are not modified."""
        with patch("dazzle_back.runtime.auth.AuthStore._init_db"):
            from dazzle_back.runtime.auth import AuthStore

            store = AuthStore(database_url="postgresql://user:pass@host/db")
            assert store._database_url == "postgresql://user:pass@host/db"


class TestAuthStoreExecute:
    """Tests for _execute behavior."""

    @pytest.fixture
    def mock_postgres_store(self):
        """Create a mock PostgreSQL AuthStore."""
        with patch("dazzle_back.runtime.auth.AuthStore._init_db"):
            from dazzle_back.runtime.auth import AuthStore

            store = AuthStore(database_url="postgresql://localhost/test")
            return store

    def test_execute_with_dict_rows(self, mock_postgres_store):
        """Verify _execute handles dict_row results correctly."""
        mock_rows = [
            MockDictRow({"id": "123", "email": "test@example.com", "username": "test"}),
            MockDictRow({"id": "456", "email": "other@example.com", "username": "other"}),
        ]

        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("email",), ("username",)]
        mock_cursor.fetchall.return_value = mock_rows

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch.object(mock_postgres_store, "_get_connection", return_value=mock_conn):
            results = mock_postgres_store._execute("SELECT * FROM users")

        assert len(results) == 2
        assert results[0] == {"id": "123", "email": "test@example.com", "username": "test"}
        assert results[1] == {"id": "456", "email": "other@example.com", "username": "other"}

        assert type(results[0]) is dict
        assert type(results[1]) is dict

    def test_execute_returns_dict_rows(self, mock_postgres_store):
        """Ensure rows are returned as dicts that can be JSON serialized."""
        import json

        mock_row = MockDictRow(
            {
                "id": "uuid-123",
                "email": "user@test.com",
                "is_active": True,
            }
        )

        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("email",), ("is_active",)]
        mock_cursor.fetchall.return_value = [mock_row]

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch.object(mock_postgres_store, "_get_connection", return_value=mock_conn):
            results = mock_postgres_store._execute(
                "SELECT * FROM users WHERE id = %s", ("uuid-123",)
            )

        serialized = json.dumps(results)
        assert "uuid-123" in serialized
        assert "user@test.com" in serialized


class TestPostgresTableInit:
    """Tests for PostgreSQL table initialization."""

    @pytest.fixture
    def mock_psycopg(self):
        """Mock psycopg module for tests."""
        import sys

        mock_psycopg = MagicMock()
        mock_rows = MagicMock()
        mock_rows.dict_row = MagicMock()

        old_psycopg = sys.modules.get("psycopg")
        old_rows = sys.modules.get("psycopg.rows")

        sys.modules["psycopg"] = mock_psycopg
        sys.modules["psycopg.rows"] = mock_rows

        yield mock_psycopg

        if old_psycopg:
            sys.modules["psycopg"] = old_psycopg
        else:
            del sys.modules["psycopg"]

        if old_rows:
            sys.modules["psycopg.rows"] = old_rows
        else:
            del sys.modules["psycopg.rows"]

    def _make_store_with_mock_conn(self, mock_cursor):
        """Create an AuthStore with a mocked connection."""
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch("dazzle_back.runtime.auth.AuthStore._init_db"):
            from dazzle_back.runtime.auth import AuthStore

            store = AuthStore(database_url="postgresql://mock/test")

        # Call the real _init_db with a mocked _get_connection
        with patch.object(store, "_get_connection", return_value=mock_conn):
            AuthStore._init_db(store)

        return store

    def test_init_db_creates_users_table(self, mock_psycopg):
        """Verify _init_db creates users table."""
        mock_cursor = MagicMock()
        self._make_store_with_mock_conn(mock_cursor)

        calls = mock_cursor.execute.call_args_list
        create_users = any("CREATE TABLE IF NOT EXISTS users" in str(call) for call in calls)
        assert create_users, "users table should be created"

    def test_init_db_creates_sessions_table(self, mock_psycopg):
        """Verify _init_db creates sessions table."""
        mock_cursor = MagicMock()
        self._make_store_with_mock_conn(mock_cursor)

        calls = mock_cursor.execute.call_args_list
        create_sessions = any("CREATE TABLE IF NOT EXISTS sessions" in str(call) for call in calls)
        assert create_sessions, "sessions table should be created"

    def test_init_db_creates_indexes(self, mock_psycopg):
        """Verify _init_db creates required indexes."""
        mock_cursor = MagicMock()
        self._make_store_with_mock_conn(mock_cursor)

        calls = mock_cursor.execute.call_args_list
        call_strs = [str(call) for call in calls]

        has_users_email_idx = any("idx_users_email" in s for s in call_strs)
        has_sessions_user_idx = any("idx_sessions_user_id" in s for s in call_strs)
        has_sessions_expires_idx = any("idx_sessions_expires" in s for s in call_strs)

        assert has_users_email_idx, "idx_users_email index should be created"
        assert has_sessions_user_idx, "idx_sessions_user_id index should be created"
        assert has_sessions_expires_idx, "idx_sessions_expires index should be created"


class TestPostgresGetConnection:
    """Tests for PostgreSQL connection handling."""

    @pytest.fixture
    def mock_psycopg(self):
        """Mock psycopg module for tests."""
        import sys

        mock_psycopg = MagicMock()
        mock_rows = MagicMock()
        mock_rows.dict_row = MagicMock()

        old_psycopg = sys.modules.get("psycopg")
        old_rows = sys.modules.get("psycopg.rows")

        sys.modules["psycopg"] = mock_psycopg
        sys.modules["psycopg.rows"] = mock_rows

        yield mock_psycopg, mock_rows

        if old_psycopg:
            sys.modules["psycopg"] = old_psycopg
        else:
            del sys.modules["psycopg"]

        if old_rows:
            sys.modules["psycopg.rows"] = old_rows
        else:
            del sys.modules["psycopg.rows"]

    def test_get_connection_passes_row_factory(self, mock_psycopg):
        """Verify _get_connection passes row_factory=dict_row to connect()."""
        mock_pg, mock_rows = mock_psycopg
        mock_conn = MagicMock()

        with patch("dazzle_back.runtime.auth.AuthStore._init_db"):
            from dazzle_back.runtime.auth import AuthStore

            store = AuthStore(database_url="postgresql://localhost/test")

        with patch("dazzle_back.runtime.auth.store.psycopg") as patched_pg:
            patched_pg.connect.return_value = mock_conn
            from dazzle_back.runtime.auth.store import dict_row

            store._get_connection()

            patched_pg.connect.assert_called_once_with(
                "postgresql://localhost/test", row_factory=dict_row
            )


class TestPostgresUserOperations:
    """Tests for user operations."""

    @pytest.fixture
    def mock_postgres_store(self):
        """Create a mock PostgreSQL AuthStore."""
        with patch("dazzle_back.runtime.auth.AuthStore._init_db"):
            from dazzle_back.runtime.auth import AuthStore

            store = AuthStore(database_url="postgresql://localhost/test")
            return store

    def test_row_to_user_handles_postgres_row(self, mock_postgres_store):
        """Verify _row_to_user correctly converts PostgreSQL rows."""
        from dazzle_back.runtime.auth import UserRecord

        now = datetime.now(UTC)
        row = {
            "id": "550e8400-e29b-41d4-a716-446655440000",
            "email": "test@example.com",
            "password_hash": "salt$hash",
            "username": "testuser",
            "is_active": True,
            "is_superuser": False,
            "roles": '["admin", "user"]',
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        user = mock_postgres_store._row_to_user(row)

        assert isinstance(user, UserRecord)
        assert str(user.id) == "550e8400-e29b-41d4-a716-446655440000"
        assert user.email == "test@example.com"
        assert user.username == "testuser"
        assert user.is_active is True
        assert user.is_superuser is False
        assert user.roles == ["admin", "user"]


class TestExecuteModify:
    """Tests for _execute_modify."""

    @pytest.fixture
    def mock_postgres_store(self):
        """Create a mock PostgreSQL AuthStore."""
        with patch("dazzle_back.runtime.auth.AuthStore._init_db"):
            from dazzle_back.runtime.auth import AuthStore

            store = AuthStore(database_url="postgresql://localhost/test")
            return store

    def test_execute_modify_returns_rowcount(self, mock_postgres_store):
        """Verify _execute_modify returns correct rowcount."""
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 5

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch.object(mock_postgres_store, "_get_connection", return_value=mock_conn):
            result = mock_postgres_store._execute_modify(
                "DELETE FROM sessions WHERE expires_at < %s",
                (datetime.now(UTC).isoformat(),),
            )

        assert result == 5
        mock_conn.commit.assert_called_once()
