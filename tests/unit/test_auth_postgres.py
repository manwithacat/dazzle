"""
Unit tests for PostgreSQL-specific auth code paths.

These tests use mocks to test PostgreSQL-specific behavior without requiring
an actual PostgreSQL database. They cover:
- RealDictCursor row handling (the bug that was fixed)
- Placeholder conversion (? to %s)
- Boolean value conversion
- PostgreSQL table initialization
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest


class MockRealDictRow(dict):
    """
    Mock psycopg2.extras.RealDictRow.

    RealDictRow is dict-like but iterating yields keys (not values).
    The bug we fixed was assuming dict(row) worked correctly for these.
    """

    def __init__(self, data: dict):
        super().__init__(data)


class TestAuthStorePostgresInit:
    """Tests for PostgreSQL-specific initialization."""

    def test_uses_postgres_when_database_url_provided(self):
        """Verify _use_postgres is True when database_url is provided."""
        with patch("dazzle_back.runtime.auth.AuthStore._init_db"):
            from dazzle_back.runtime.auth import AuthStore

            store = AuthStore(database_url="postgresql://localhost/test")
            assert store._use_postgres is True

    def test_uses_sqlite_when_no_database_url(self, tmp_path):
        """Verify _use_postgres is False when only db_path is provided."""
        from dazzle_back.runtime.auth import AuthStore

        db_path = tmp_path / "auth.db"
        store = AuthStore(db_path=db_path)
        assert store._use_postgres is False

    def test_normalizes_heroku_postgres_url(self):
        """Verify postgres:// is normalized to postgresql://."""
        with patch("dazzle_back.runtime.auth.AuthStore._init_db"):
            from dazzle_back.runtime.auth import AuthStore

            store = AuthStore(database_url="postgres://user:pass@host/db")
            assert store._pg_url == "postgresql://user:pass@host/db"

    def test_postgresql_url_unchanged(self):
        """Verify postgresql:// URLs are not modified."""
        with patch("dazzle_back.runtime.auth.AuthStore._init_db"):
            from dazzle_back.runtime.auth import AuthStore

            store = AuthStore(database_url="postgresql://user:pass@host/db")
            assert store._pg_url == "postgresql://user:pass@host/db"


class TestAuthStorePostgresExecute:
    """Tests for PostgreSQL-specific _execute behavior."""

    @pytest.fixture
    def mock_postgres_store(self):
        """Create a mock PostgreSQL AuthStore."""
        with patch("dazzle_back.runtime.auth.AuthStore._init_db"):
            from dazzle_back.runtime.auth import AuthStore

            store = AuthStore(database_url="postgresql://localhost/test")
            return store

    def test_execute_with_realdictcursor_rows(self, mock_postgres_store):
        """Verify _execute handles RealDictRow objects correctly.

        RealDictRow is dict-like but requires explicit dict() conversion
        to work correctly with JSON serialization and Pydantic models.
        """
        # Create mock rows that behave like RealDictRow
        mock_rows = [
            MockRealDictRow({"id": "123", "email": "test@example.com", "username": "test"}),
            MockRealDictRow({"id": "456", "email": "other@example.com", "username": "other"}),
        ]

        mock_cursor = MagicMock()
        mock_cursor.description = [("id",), ("email",), ("username",)]
        mock_cursor.fetchall.return_value = mock_rows

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch.object(mock_postgres_store, "_get_connection", return_value=mock_conn):
            results = mock_postgres_store._execute("SELECT * FROM users")

        # Verify results are proper dicts (not RealDictRow)
        assert len(results) == 2
        assert results[0] == {"id": "123", "email": "test@example.com", "username": "test"}
        assert results[1] == {"id": "456", "email": "other@example.com", "username": "other"}

        # Verify they're actual dicts, not MockRealDictRow
        assert type(results[0]) is dict
        assert type(results[1]) is dict

    def test_execute_returns_dict_rows(self, mock_postgres_store):
        """Ensure rows are returned as dicts that can be JSON serialized."""
        import json

        mock_row = MockRealDictRow(
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

        # Should be serializable as JSON
        serialized = json.dumps(results)
        assert "uuid-123" in serialized
        assert "user@test.com" in serialized


class TestPlaceholderConversion:
    """Tests for SQL placeholder conversion."""

    @pytest.fixture
    def mock_postgres_store(self):
        """Create a mock PostgreSQL AuthStore."""
        with patch("dazzle_back.runtime.auth.AuthStore._init_db"):
            from dazzle_back.runtime.auth import AuthStore

            store = AuthStore(database_url="postgresql://localhost/test")
            return store

    def test_placeholder_conversion_single(self, mock_postgres_store):
        """Ensure single ? placeholder converts to %s for PostgreSQL."""
        mock_cursor = MagicMock()
        mock_cursor.description = None

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch.object(mock_postgres_store, "_get_connection", return_value=mock_conn):
            mock_postgres_store._execute("SELECT * FROM users WHERE id = ?", ("123",))

        # Check that the query was converted
        mock_cursor.execute.assert_called_once()
        called_query = mock_cursor.execute.call_args[0][0]
        assert "%s" in called_query
        assert "?" not in called_query

    def test_placeholder_conversion_multiple(self, mock_postgres_store):
        """Ensure multiple ? placeholders all convert to %s."""
        mock_cursor = MagicMock()
        mock_cursor.description = None

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch.object(mock_postgres_store, "_get_connection", return_value=mock_conn):
            mock_postgres_store._execute(
                "SELECT * FROM users WHERE email = ? AND is_active = ?",
                ("test@example.com", True),
            )

        called_query = mock_cursor.execute.call_args[0][0]
        assert called_query.count("%s") == 2
        assert "?" not in called_query


class TestBooleanConversion:
    """Tests for boolean value conversion."""

    @pytest.fixture
    def mock_postgres_store(self):
        """Create a mock PostgreSQL AuthStore."""
        with patch("dazzle_back.runtime.auth.AuthStore._init_db"):
            from dazzle_back.runtime.auth import AuthStore

            store = AuthStore(database_url="postgresql://localhost/test")
            return store

    @pytest.fixture
    def sqlite_store(self, tmp_path):
        """Create an actual SQLite AuthStore."""
        from dazzle_back.runtime.auth import AuthStore

        db_path = tmp_path / "auth.db"
        return AuthStore(db_path=db_path)

    def test_bool_to_db_postgres_true(self, mock_postgres_store):
        """Ensure True stays True for PostgreSQL."""
        result = mock_postgres_store._bool_to_db(True)
        assert result is True

    def test_bool_to_db_postgres_false(self, mock_postgres_store):
        """Ensure False stays False for PostgreSQL."""
        result = mock_postgres_store._bool_to_db(False)
        assert result is False

    def test_bool_to_db_sqlite_true(self, sqlite_store):
        """Ensure True becomes 1 for SQLite."""
        result = sqlite_store._bool_to_db(True)
        assert result == 1

    def test_bool_to_db_sqlite_false(self, sqlite_store):
        """Ensure False becomes 0 for SQLite."""
        result = sqlite_store._bool_to_db(False)
        assert result == 0


class TestPostgresTableInit:
    """Tests for PostgreSQL table initialization.

    These tests require mocking psycopg2 since it may not be installed.
    """

    @pytest.fixture
    def mock_psycopg2(self):
        """Mock psycopg2 module for tests."""
        import sys

        mock_psycopg2 = MagicMock()
        mock_extras = MagicMock()
        mock_psycopg2.extras = mock_extras

        # Store old modules if they exist
        old_psycopg2 = sys.modules.get("psycopg2")
        old_extras = sys.modules.get("psycopg2.extras")

        sys.modules["psycopg2"] = mock_psycopg2
        sys.modules["psycopg2.extras"] = mock_extras

        yield mock_psycopg2

        # Restore old modules
        if old_psycopg2:
            sys.modules["psycopg2"] = old_psycopg2
        else:
            del sys.modules["psycopg2"]

        if old_extras:
            sys.modules["psycopg2.extras"] = old_extras
        else:
            del sys.modules["psycopg2.extras"]

    def test_init_postgres_db_creates_users_table(self, mock_psycopg2):
        """Verify _init_postgres_db creates users table."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        with patch("dazzle_back.runtime.auth.AuthStore._init_db"):
            from dazzle_back.runtime.auth import AuthStore

            store = AuthStore(database_url="postgresql://localhost/test")
            # Manually call the method we're testing
            store._init_postgres_db()

        # Check that CREATE TABLE IF NOT EXISTS users was executed
        calls = mock_cursor.execute.call_args_list
        create_users = any("CREATE TABLE IF NOT EXISTS users" in str(call) for call in calls)
        assert create_users, "users table should be created"

    def test_init_postgres_db_creates_sessions_table(self, mock_psycopg2):
        """Verify _init_postgres_db creates sessions table."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        with patch("dazzle_back.runtime.auth.AuthStore._init_db"):
            from dazzle_back.runtime.auth import AuthStore

            store = AuthStore(database_url="postgresql://localhost/test")
            store._init_postgres_db()

        calls = mock_cursor.execute.call_args_list
        create_sessions = any("CREATE TABLE IF NOT EXISTS sessions" in str(call) for call in calls)
        assert create_sessions, "sessions table should be created"

    def test_init_postgres_db_creates_indexes(self, mock_psycopg2):
        """Verify _init_postgres_db creates required indexes."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg2.connect.return_value = mock_conn

        with patch("dazzle_back.runtime.auth.AuthStore._init_db"):
            from dazzle_back.runtime.auth import AuthStore

            store = AuthStore(database_url="postgresql://localhost/test")
            store._init_postgres_db()

        calls = mock_cursor.execute.call_args_list
        call_strs = [str(call) for call in calls]

        # Check for index creation
        has_users_email_idx = any("idx_users_email" in s for s in call_strs)
        has_sessions_user_idx = any("idx_sessions_user_id" in s for s in call_strs)
        has_sessions_expires_idx = any("idx_sessions_expires" in s for s in call_strs)

        assert has_users_email_idx, "idx_users_email index should be created"
        assert has_sessions_user_idx, "idx_sessions_user_id index should be created"
        assert has_sessions_expires_idx, "idx_sessions_expires index should be created"


class TestPostgresGetConnection:
    """Tests for PostgreSQL connection handling."""

    @pytest.fixture
    def mock_psycopg2(self):
        """Mock psycopg2 module for tests."""
        import sys

        mock_psycopg2 = MagicMock()
        mock_extras = MagicMock()
        mock_psycopg2.extras = mock_extras

        old_psycopg2 = sys.modules.get("psycopg2")
        old_extras = sys.modules.get("psycopg2.extras")

        sys.modules["psycopg2"] = mock_psycopg2
        sys.modules["psycopg2.extras"] = mock_extras

        yield mock_psycopg2, mock_extras

        if old_psycopg2:
            sys.modules["psycopg2"] = old_psycopg2
        else:
            del sys.modules["psycopg2"]

        if old_extras:
            sys.modules["psycopg2.extras"] = old_extras
        else:
            del sys.modules["psycopg2.extras"]

    def test_get_connection_sets_realdictcursor(self, mock_psycopg2):
        """Verify _get_connection sets RealDictCursor factory."""
        mock_pg, mock_extras = mock_psycopg2
        mock_conn = MagicMock()
        mock_pg.connect.return_value = mock_conn

        with patch("dazzle_back.runtime.auth.AuthStore._init_db"):
            from dazzle_back.runtime.auth import AuthStore

            store = AuthStore(database_url="postgresql://localhost/test")
            conn = store._get_connection()

        # Verify cursor_factory was set
        assert conn.cursor_factory == mock_extras.RealDictCursor


class TestPostgresPlaceholderMethod:
    """Tests for the _placeholder method."""

    def test_placeholder_returns_percent_s_for_postgres(self):
        """Verify _placeholder returns %s for PostgreSQL."""
        with patch("dazzle_back.runtime.auth.AuthStore._init_db"):
            from dazzle_back.runtime.auth import AuthStore

            store = AuthStore(database_url="postgresql://localhost/test")
            assert store._placeholder() == "%s"

    def test_placeholder_returns_question_mark_for_sqlite(self, tmp_path):
        """Verify _placeholder returns ? for SQLite."""
        from dazzle_back.runtime.auth import AuthStore

        db_path = tmp_path / "auth.db"
        store = AuthStore(db_path=db_path)
        assert store._placeholder() == "?"


class TestPostgresUserOperations:
    """Tests for user operations with PostgreSQL backend."""

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
            "is_active": True,  # PostgreSQL native boolean
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


class TestExecuteModifyPostgres:
    """Tests for _execute_modify with PostgreSQL."""

    @pytest.fixture
    def mock_postgres_store(self):
        """Create a mock PostgreSQL AuthStore."""
        with patch("dazzle_back.runtime.auth.AuthStore._init_db"):
            from dazzle_back.runtime.auth import AuthStore

            store = AuthStore(database_url="postgresql://localhost/test")
            return store

    def test_execute_modify_converts_placeholders(self, mock_postgres_store):
        """Verify _execute_modify converts ? to %s."""
        mock_cursor = MagicMock()
        mock_cursor.rowcount = 1

        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch.object(mock_postgres_store, "_get_connection", return_value=mock_conn):
            result = mock_postgres_store._execute_modify(
                "UPDATE users SET username = ? WHERE id = ?",
                ("newname", "123"),
            )

        called_query = mock_cursor.execute.call_args[0][0]
        assert called_query.count("%s") == 2
        assert "?" not in called_query
        assert result == 1

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
