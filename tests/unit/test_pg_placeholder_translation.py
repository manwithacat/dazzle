"""
Tests for PostgreSQL backend compatibility.

Verifies that PgConnectionWrapper passes SQL through to cursor,
and that outbox/relation_loader use db.placeholder correctly.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from dazzle_back.runtime.pg_backend import PgConnectionWrapper

# =============================================================================
# PgConnectionWrapper Tests
# =============================================================================


class TestPgConnectionWrapper:
    """Tests for PgConnectionWrapper SQL pass-through."""

    def _make_wrapper(self) -> tuple[PgConnectionWrapper, MagicMock]:
        """Create a wrapper with a mock connection."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        wrapper = PgConnectionWrapper(mock_conn)
        return wrapper, mock_cursor

    def test_passes_sql_through_unchanged(self) -> None:
        """PgConnectionWrapper passes SQL to cursor unchanged."""
        wrapper, mock_cursor = self._make_wrapper()
        wrapper.execute("SELECT * FROM t WHERE id = %s AND name = %s", ("a", "b"))
        mock_cursor.execute.assert_called_once_with(
            "SELECT * FROM t WHERE id = %s AND name = %s", ("a", "b")
        )

    def test_no_params_query(self) -> None:
        """Queries without params pass through unchanged."""
        wrapper, mock_cursor = self._make_wrapper()
        wrapper.execute("SELECT * FROM t WHERE id = 1")
        mock_cursor.execute.assert_called_once_with("SELECT * FROM t WHERE id = 1", ())

    def test_in_clause(self) -> None:
        """IN (%s, %s, %s) passes through correctly."""
        wrapper, mock_cursor = self._make_wrapper()
        wrapper.execute("SELECT * FROM t WHERE id IN (%s, %s, %s)", (1, 2, 3))
        mock_cursor.execute.assert_called_once_with(
            "SELECT * FROM t WHERE id IN (%s, %s, %s)", (1, 2, 3)
        )

    def test_returns_cursor(self) -> None:
        """execute() returns the cursor for fetchone/fetchall."""
        wrapper, mock_cursor = self._make_wrapper()
        result = wrapper.execute("SELECT 1")
        assert result is mock_cursor

    def test_none_params_default_to_empty_tuple(self) -> None:
        """None params are passed as empty tuple."""
        wrapper, mock_cursor = self._make_wrapper()
        wrapper.execute("SELECT 1")
        mock_cursor.execute.assert_called_once_with("SELECT 1", ())


# =============================================================================
# Outbox Placeholder Tests
# =============================================================================


class TestOutboxPlaceholder:
    """Verify OutboxRepository uses db.placeholder, not hardcoded ?."""

    def test_outbox_create_uses_placeholder(self) -> None:
        """OutboxRepository.create() uses db.placeholder for INSERT."""
        from dazzle_back.channels.outbox import (
            OutboxRepository,
            create_outbox_message,
        )

        mock_db = MagicMock()
        mock_db.placeholder = "%s"
        mock_conn = MagicMock()
        mock_db.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.connection.return_value.__exit__ = MagicMock(return_value=False)

        repo = OutboxRepository.__new__(OutboxRepository)
        repo.db = mock_db
        repo.TABLE_NAME = "_dazzle_outbox"

        msg = create_outbox_message(
            channel_name="test",
            operation_name="send",
            message_type="TestMsg",
            payload={"key": "val"},
            recipient="user@test.com",
        )

        repo.create(msg)

        # Verify the SQL used %s, not ?
        call_args = mock_conn.execute.call_args
        sql = call_args[0][0]
        assert "?" not in sql
        assert "%s" in sql

    def test_outbox_get_uses_placeholder(self) -> None:
        """OutboxRepository.get() uses db.placeholder."""
        from dazzle_back.channels.outbox import OutboxRepository

        mock_db = MagicMock()
        mock_db.placeholder = "%s"
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.execute.return_value = mock_cursor
        mock_db.connection.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_db.connection.return_value.__exit__ = MagicMock(return_value=False)

        repo = OutboxRepository.__new__(OutboxRepository)
        repo.db = mock_db
        repo.TABLE_NAME = "_dazzle_outbox"

        repo.get("test-id")

        sql = mock_conn.execute.call_args[0][0]
        assert "?" not in sql
        assert "%s" in sql


# =============================================================================
# RelationLoader Placeholder Tests
# =============================================================================


class TestRelationLoaderPlaceholder:
    """Verify RelationLoader uses configurable placeholder."""

    def test_default_placeholder_is_percent_s(self) -> None:
        """Default placeholder is %s for PostgreSQL."""
        from dazzle_back.runtime.relation_loader import RelationLoader, RelationRegistry

        loader = RelationLoader(RelationRegistry(), [])
        assert loader._placeholder == "%s"

    def test_custom_placeholder(self) -> None:
        """Placeholder can be overridden."""
        from dazzle_back.runtime.relation_loader import RelationLoader, RelationRegistry

        loader = RelationLoader(RelationRegistry(), [], placeholder="$1")
        assert loader._placeholder == "$1"


# =============================================================================
# EventInbox Placeholder Tests
# =============================================================================


class TestEventInboxPlaceholder:
    """Verify EventInbox uses configurable placeholder."""

    def test_default_placeholder_is_question_mark(self) -> None:
        """Default placeholder is ? for SQLite compat."""
        from dazzle_back.events.inbox import EventInbox

        inbox = EventInbox()
        assert inbox._ph == "?"
        assert inbox._backend_type == "sqlite"

    def test_custom_placeholder_and_backend(self) -> None:
        """Placeholder and backend_type can be set for Postgres."""
        from dazzle_back.events.inbox import EventInbox

        inbox = EventInbox(placeholder="%s", backend_type="postgres")
        assert inbox._ph == "%s"
        assert inbox._backend_type == "postgres"
