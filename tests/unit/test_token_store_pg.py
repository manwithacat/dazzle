"""
Unit tests for TokenStore PostgreSQL-only support.

Tests verify:
- Constructor accepts database_url parameter
- Heroku URL normalization
- PostgreSQL table initialization
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# =========================================================================
# Initialization tests
# =========================================================================


class TestTokenStoreInit:
    """Tests for initialization."""

    def test_normalizes_heroku_postgres_url(self):
        """Verify postgres:// is normalized to postgresql://."""
        with patch("dazzle_back.runtime.token_store.TokenStore._init_db"):
            from dazzle_back.runtime.token_store import TokenStore

            store = TokenStore(database_url="postgres://user:pass@host/db")
            assert store._database_url == "postgresql://user:pass@host/db"

    def test_postgresql_url_unchanged(self):
        """Verify postgresql:// URLs are not modified."""
        with patch("dazzle_back.runtime.token_store.TokenStore._init_db"):
            from dazzle_back.runtime.token_store import TokenStore

            store = TokenStore(database_url="postgresql://user:pass@host/db")
            assert store._database_url == "postgresql://user:pass@host/db"

    def test_default_token_lifetime(self):
        """Verify default token lifetime is 7 days."""
        with patch("dazzle_back.runtime.token_store.TokenStore._init_db"):
            from dazzle_back.runtime.token_store import TokenStore

            store = TokenStore(database_url="postgresql://localhost/test")
            assert store.token_lifetime_days == 7

    def test_custom_token_lifetime(self):
        """Verify custom token lifetime is respected."""
        with patch("dazzle_back.runtime.token_store.TokenStore._init_db"):
            from dazzle_back.runtime.token_store import TokenStore

            store = TokenStore(database_url="postgresql://localhost/test", token_lifetime_days=30)
            assert store.token_lifetime_days == 30


# =========================================================================
# PostgreSQL table init tests
# =========================================================================


class TestTokenStorePostgresInit:
    """Tests for PostgreSQL table initialization."""

    def test_init_db_creates_table(self):
        """Verify _init_db creates refresh_tokens table."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch("dazzle_back.runtime.token_store.TokenStore._init_db"):
            from dazzle_back.runtime.token_store import TokenStore

            store = TokenStore(database_url="postgresql://localhost/test")

        with patch.object(store, "_get_connection", return_value=mock_conn):
            # Call the real _init_db — it will use our mock connection
            TokenStore._init_db(store)

        calls = mock_cursor.execute.call_args_list
        create_table = any("CREATE TABLE IF NOT EXISTS refresh_tokens" in str(c) for c in calls)
        assert create_table, "refresh_tokens table should be created"

    def test_init_db_creates_indexes(self):
        """Verify _init_db creates required indexes."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch("dazzle_back.runtime.token_store.TokenStore._init_db"):
            from dazzle_back.runtime.token_store import TokenStore

            store = TokenStore(database_url="postgresql://localhost/test")

        with patch.object(store, "_get_connection", return_value=mock_conn):
            TokenStore._init_db(store)

        call_strs = [str(c) for c in mock_cursor.execute.call_args_list]
        assert any("idx_refresh_tokens_user_id" in s for s in call_strs)
        assert any("idx_refresh_tokens_expires" in s for s in call_strs)
        assert any("idx_refresh_tokens_device" in s for s in call_strs)

    def test_init_db_commits_and_closes(self):
        """Verify _init_db commits and closes connection."""
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        with patch("dazzle_back.runtime.token_store.TokenStore._init_db"):
            from dazzle_back.runtime.token_store import TokenStore

            store = TokenStore(database_url="postgresql://localhost/test")

        with patch.object(store, "_get_connection", return_value=mock_conn):
            TokenStore._init_db(store)

        mock_conn.commit.assert_called_once()
        mock_conn.close.assert_called_once()
