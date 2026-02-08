"""
Unit tests for TokenStore dual-backend (SQLite + PostgreSQL) support.

Tests verify:
- Constructor accepts database_url parameter
- SQLite mode still works (functional tests using tmp_path)
- Postgres mode sets correct flags (unit tests without actual Postgres)
- _ph returns correct placeholder per backend
- _bool_to_db works correctly per backend
- PostgreSQL table initialization
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

# =========================================================================
# Initialization tests
# =========================================================================


class TestTokenStoreInit:
    """Tests for dual-backend initialization."""

    def test_uses_postgres_when_database_url_provided(self):
        """Verify _use_postgres is True when database_url is provided."""
        with patch("dazzle_back.runtime.token_store.TokenStore._init_db"):
            from dazzle_back.runtime.token_store import TokenStore

            store = TokenStore(database_url="postgresql://localhost/test")
            assert store._use_postgres is True

    def test_uses_sqlite_when_no_database_url(self, tmp_path):
        """Verify _use_postgres is False when only db_path is provided."""
        from dazzle_back.runtime.token_store import TokenStore

        db_path = tmp_path / "tokens.db"
        store = TokenStore(db_path=db_path)
        assert store._use_postgres is False

    def test_normalizes_heroku_postgres_url(self):
        """Verify postgres:// is normalized to postgresql://."""
        with patch("dazzle_back.runtime.token_store.TokenStore._init_db"):
            from dazzle_back.runtime.token_store import TokenStore

            store = TokenStore(database_url="postgres://user:pass@host/db")
            assert store._pg_url == "postgresql://user:pass@host/db"

    def test_postgresql_url_unchanged(self):
        """Verify postgresql:// URLs are not modified."""
        with patch("dazzle_back.runtime.token_store.TokenStore._init_db"):
            from dazzle_back.runtime.token_store import TokenStore

            store = TokenStore(database_url="postgresql://user:pass@host/db")
            assert store._pg_url == "postgresql://user:pass@host/db"

    def test_default_token_lifetime(self, tmp_path):
        """Verify default token lifetime is 7 days."""
        from dazzle_back.runtime.token_store import TokenStore

        store = TokenStore(db_path=tmp_path / "tokens.db")
        assert store.token_lifetime_days == 7

    def test_custom_token_lifetime(self, tmp_path):
        """Verify custom token lifetime is respected."""
        from dazzle_back.runtime.token_store import TokenStore

        store = TokenStore(db_path=tmp_path / "tokens.db", token_lifetime_days=30)
        assert store.token_lifetime_days == 30


# =========================================================================
# Placeholder and boolean conversion tests
# =========================================================================


class TestTokenStorePlaceholders:
    """Tests for placeholder conversion."""

    def test_ph_returns_percent_s_for_postgres(self):
        """Verify _ph returns %s for PostgreSQL."""
        with patch("dazzle_back.runtime.token_store.TokenStore._init_db"):
            from dazzle_back.runtime.token_store import TokenStore

            store = TokenStore(database_url="postgresql://localhost/test")
            assert store._ph == "%s"

    def test_ph_returns_question_mark_for_sqlite(self, tmp_path):
        """Verify _ph returns ? for SQLite."""
        from dazzle_back.runtime.token_store import TokenStore

        store = TokenStore(db_path=tmp_path / "tokens.db")
        assert store._ph == "?"


class TestTokenStoreBoolConversion:
    """Tests for boolean value conversion."""

    def test_bool_to_db_postgres_true(self):
        """Ensure True stays True for PostgreSQL."""
        with patch("dazzle_back.runtime.token_store.TokenStore._init_db"):
            from dazzle_back.runtime.token_store import TokenStore

            store = TokenStore(database_url="postgresql://localhost/test")
            assert store._bool_to_db(True) is True

    def test_bool_to_db_postgres_false(self):
        """Ensure False stays False for PostgreSQL."""
        with patch("dazzle_back.runtime.token_store.TokenStore._init_db"):
            from dazzle_back.runtime.token_store import TokenStore

            store = TokenStore(database_url="postgresql://localhost/test")
            assert store._bool_to_db(False) is False

    def test_bool_to_db_sqlite_true(self, tmp_path):
        """Ensure True becomes 1 for SQLite."""
        from dazzle_back.runtime.token_store import TokenStore

        store = TokenStore(db_path=tmp_path / "tokens.db")
        assert store._bool_to_db(True) == 1

    def test_bool_to_db_sqlite_false(self, tmp_path):
        """Ensure False becomes 0 for SQLite."""
        from dazzle_back.runtime.token_store import TokenStore

        store = TokenStore(db_path=tmp_path / "tokens.db")
        assert store._bool_to_db(False) == 0


# =========================================================================
# Backend type tests
# =========================================================================


class TestTokenStoreBackendType:
    """Tests for backend_type property."""

    def test_backend_type_postgres(self):
        """Verify backend_type returns 'postgres' for PostgreSQL."""
        with patch("dazzle_back.runtime.token_store.TokenStore._init_db"):
            from dazzle_back.runtime.token_store import TokenStore

            store = TokenStore(database_url="postgresql://localhost/test")
            assert store.backend_type == "postgres"

    def test_backend_type_sqlite(self, tmp_path):
        """Verify backend_type returns 'sqlite' for SQLite."""
        from dazzle_back.runtime.token_store import TokenStore

        store = TokenStore(db_path=tmp_path / "tokens.db")
        assert store.backend_type == "sqlite"


# =========================================================================
# PostgreSQL table init tests
# =========================================================================


class TestTokenStorePostgresInit:
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
        """Verify _init_postgres_db creates refresh_tokens table."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        with patch("dazzle_back.runtime.token_store.TokenStore._init_db"):
            from dazzle_back.runtime.token_store import TokenStore

            store = TokenStore(database_url="postgresql://localhost/test")
            store._init_postgres_db()

        calls = mock_cursor.execute.call_args_list
        create_table = any("CREATE TABLE IF NOT EXISTS refresh_tokens" in str(c) for c in calls)
        assert create_table, "refresh_tokens table should be created"

    def test_init_postgres_db_creates_indexes(self, mock_psycopg):
        """Verify _init_postgres_db creates required indexes."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        with patch("dazzle_back.runtime.token_store.TokenStore._init_db"):
            from dazzle_back.runtime.token_store import TokenStore

            store = TokenStore(database_url="postgresql://localhost/test")
            store._init_postgres_db()

        call_strs = [str(c) for c in mock_cursor.execute.call_args_list]
        assert any("idx_refresh_tokens_user_id" in s for s in call_strs)
        assert any("idx_refresh_tokens_expires" in s for s in call_strs)
        assert any("idx_refresh_tokens_device" in s for s in call_strs)

    def test_init_postgres_db_commits_and_closes(self, mock_psycopg):
        """Verify _init_postgres_db commits and closes connection."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_psycopg.connect.return_value = mock_conn

        with patch("dazzle_back.runtime.token_store.TokenStore._init_db"):
            from dazzle_back.runtime.token_store import TokenStore

            store = TokenStore(database_url="postgresql://localhost/test")
            store._init_postgres_db()

        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()


# =========================================================================
# SQLite functional tests
# =========================================================================


class TestTokenStoreSQLiteFunctional:
    """Functional tests using actual SQLite backend."""

    @pytest.fixture
    def store(self, tmp_path):
        """Create a SQLite-backed TokenStore."""
        from dazzle_back.runtime.token_store import TokenStore

        return TokenStore(db_path=tmp_path / "tokens.db")

    @pytest.fixture
    def mock_user(self):
        """Create a mock user record."""
        user = MagicMock()
        user.id = uuid4()
        return user

    def test_create_and_validate_token(self, store, mock_user):
        """Token can be created and validated."""
        token = store.create_token(mock_user)
        assert isinstance(token, str)
        assert len(token) > 0

        record = store.validate_token(token)
        assert record is not None
        assert record.user_id == mock_user.id

    def test_validate_invalid_token(self, store):
        """Invalid token returns None."""
        result = store.validate_token("not-a-real-token")
        assert result is None

    def test_revoke_token(self, store, mock_user):
        """Revoked token becomes invalid."""
        token = store.create_token(mock_user)
        assert store.revoke_token(token) is True
        assert store.validate_token(token) is None

    def test_use_token(self, store, mock_user):
        """use_token updates last_used_at."""
        token = store.create_token(mock_user)
        assert store.use_token(token) is True

    def test_get_user_tokens(self, store, mock_user):
        """get_user_tokens returns active tokens."""
        store.create_token(mock_user)
        store.create_token(mock_user)
        tokens = store.get_user_tokens(mock_user.id)
        assert len(tokens) == 2

    def test_revoke_user_tokens(self, store, mock_user):
        """revoke_user_tokens revokes all user tokens."""
        store.create_token(mock_user)
        store.create_token(mock_user)
        count = store.revoke_user_tokens(mock_user.id)
        assert count == 2
        assert len(store.get_user_tokens(mock_user.id)) == 0

    def test_revoke_user_tokens_except(self, store, mock_user):
        """revoke_user_tokens with except_token keeps one."""
        token1 = store.create_token(mock_user)
        store.create_token(mock_user)
        count = store.revoke_user_tokens(mock_user.id, except_token=token1)
        assert count == 1
        remaining = store.get_user_tokens(mock_user.id)
        assert len(remaining) == 1

    def test_revoke_device_tokens(self, store, mock_user):
        """revoke_device_tokens revokes tokens for a specific device."""
        store.create_token(mock_user, device_id="device-1")
        store.create_token(mock_user, device_id="device-2")
        count = store.revoke_device_tokens(mock_user.id, "device-1")
        assert count == 1

    def test_cleanup_expired(self, store, mock_user):
        """cleanup_expired removes old tokens."""
        # Create a token that is already expired by manipulating the DB
        token = store.create_token(mock_user)
        token_hash = store._hash_token(token)

        # Set expires_at to the past
        past = (datetime.now(UTC) - timedelta(days=2)).isoformat()
        conn = store._get_connection()
        conn.execute(
            "UPDATE refresh_tokens SET expires_at = ? WHERE token_hash = ?",
            (past, token_hash),
        )
        conn.commit()
        conn.close()

        removed = store.cleanup_expired()
        assert removed == 1
