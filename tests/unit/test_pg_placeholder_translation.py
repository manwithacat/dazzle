"""
Tests for PostgreSQL backend compatibility.

Verifies that PgConnectionWrapper passes SQL through to cursor,
and that outbox/relation_loader use db.placeholder correctly.
"""

from unittest.mock import MagicMock

import pytest

from dazzle.http.runtime.pg_backend import PgConnectionWrapper

pytestmark = pytest.mark.postgres


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

    @pytest.mark.parametrize(
        "sql,params,expected_sql,expected_params",
        [
            (
                "SELECT * FROM t WHERE id = %s AND name = %s",
                ("a", "b"),
                "SELECT * FROM t WHERE id = %s AND name = %s",
                ("a", "b"),
            ),
            ("SELECT * FROM t WHERE id = 1", None, "SELECT * FROM t WHERE id = 1", ()),
            (
                "SELECT * FROM t WHERE id IN (%s, %s, %s)",
                (1, 2, 3),
                "SELECT * FROM t WHERE id IN (%s, %s, %s)",
                (1, 2, 3),
            ),
        ],
        ids=[
            "test_passes_sql_through_unchanged",
            "test_no_params_query",
            "test_in_clause",
        ],
    )
    def test_sql_passes_through(
        self, sql: str, params: tuple | None, expected_sql: str, expected_params: tuple
    ) -> None:
        wrapper, mock_cursor = self._make_wrapper()
        if params is None:
            wrapper.execute(sql)
        else:
            wrapper.execute(sql, params)
        mock_cursor.execute.assert_called_once_with(expected_sql, expected_params)

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
        from dazzle.http.channels.outbox import (
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
        from dazzle.http.channels.outbox import OutboxRepository

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
        from dazzle.http.runtime.relation_loader import RelationLoader, RelationRegistry

        loader = RelationLoader(RelationRegistry(), [])
        assert loader._placeholder == "%s"

    def test_custom_placeholder(self) -> None:
        """Placeholder can be overridden."""
        from dazzle.http.runtime.relation_loader import RelationLoader, RelationRegistry

        loader = RelationLoader(RelationRegistry(), [], placeholder="$1")
        assert loader._placeholder == "$1"


# =============================================================================
# EventInbox Placeholder Tests
# =============================================================================


class TestEventInboxPlaceholder:
    """Verify EventInbox always uses %s placeholders (PostgreSQL-only)."""

    def test_inbox_sql_uses_percent_s(self) -> None:
        """EventInbox SQL statements use %s (PostgreSQL placeholder)."""
        from dazzle.http.events.inbox import EventInbox

        inbox = EventInbox()
        assert "%s" in inbox._sql_mark_processed
        assert "?" not in inbox._sql_mark_processed
