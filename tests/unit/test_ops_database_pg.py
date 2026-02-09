"""Tests for OpsDatabase PostgreSQL-only support."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from dazzle_back.runtime.ops_database import (
    OpsDatabase,
    RetentionConfig,
)

# ---------------------------------------------------------------------------
# Constructor / backend selection
# ---------------------------------------------------------------------------


class TestOpsDatabaseConstructor:
    """Tests for OpsDatabase constructor."""

    def test_database_url_accepted(self) -> None:
        """Constructor with database_url should initialize (without connecting)."""
        with patch.object(OpsDatabase, "_init_schema"):
            db = OpsDatabase(database_url="postgresql://localhost/test")
            assert db._database_url == "postgresql://localhost/test"

    def test_database_url_normalizes_heroku_prefix(self) -> None:
        with patch.object(OpsDatabase, "_init_schema"):
            db = OpsDatabase(database_url="postgres://localhost/test")
            assert db._database_url == "postgresql://localhost/test"

    def test_retention_config_stored(self) -> None:
        with patch.object(OpsDatabase, "_init_schema"):
            config = RetentionConfig(health_checks_days=7)
            db = OpsDatabase(database_url="postgresql://localhost/test", retention=config)
            assert db.retention.health_checks_days == 7


# ---------------------------------------------------------------------------
# INSERT OR REPLACE -> ON CONFLICT branching
# ---------------------------------------------------------------------------


class TestInsertOrReplaceBranching:
    """Verify that Postgres uses ON CONFLICT instead of INSERT OR REPLACE."""

    def test_create_credentials_uses_on_conflict(self) -> None:
        """Verify the Postgres branch generates ON CONFLICT SQL."""
        with patch.object(OpsDatabase, "_init_schema"):
            db = OpsDatabase(database_url="postgresql://localhost/test")

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.commit = MagicMock()
        mock_conn.rollback = MagicMock()
        mock_conn.close = MagicMock()

        with patch.object(
            db,
            "connection",
            return_value=MagicMock(
                __enter__=MagicMock(return_value=mock_conn),
                __exit__=MagicMock(return_value=False),
            ),
        ):
            db.create_credentials("admin", "secret")

        call_args = mock_cursor.execute.call_args
        sql = call_args[0][0]
        assert "ON CONFLICT" in sql
        assert "INSERT OR REPLACE" not in sql

    def test_set_retention_uses_on_conflict(self) -> None:
        with patch.object(OpsDatabase, "_init_schema"):
            db = OpsDatabase(database_url="postgresql://localhost/test")

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.commit = MagicMock()
        mock_conn.rollback = MagicMock()
        mock_conn.close = MagicMock()

        with patch.object(
            db,
            "connection",
            return_value=MagicMock(
                __enter__=MagicMock(return_value=mock_conn),
                __exit__=MagicMock(return_value=False),
            ),
        ):
            db.set_retention_config(RetentionConfig())

        for call in mock_cursor.execute.call_args_list:
            sql = call[0][0]
            if "INSERT" in sql:
                assert "ON CONFLICT" in sql
                assert "INSERT OR REPLACE" not in sql
