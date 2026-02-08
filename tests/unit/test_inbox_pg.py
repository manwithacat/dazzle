"""Tests for EventInbox PostgreSQL hardening."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from dazzle_back.events.inbox import EventInbox


class TestInboxBackendType:
    """Test backend_type flag controls behavior."""

    def test_backend_type_postgres(self) -> None:
        inbox = EventInbox(backend_type="postgres", placeholder="%s")
        assert inbox._backend_type == "postgres"

    def test_backend_type_sqlite_default(self) -> None:
        inbox = EventInbox()
        assert inbox._backend_type == "sqlite"

    def test_placeholder_stored(self) -> None:
        inbox = EventInbox(placeholder="%s", backend_type="postgres")
        assert inbox._ph == "%s"


class TestInboxCreateTableSQLite:
    """Test create_table with SQLite backend."""

    @pytest.mark.asyncio
    async def test_sqlite_uses_executescript(self) -> None:
        inbox = EventInbox(backend_type="sqlite")
        conn = AsyncMock()
        await inbox.create_table(conn)

        conn.executescript.assert_called_once()
        conn.commit.assert_called_once()
        conn.execute.assert_not_called()


class TestInboxCreateTablePostgres:
    """Test create_table with Postgres backend."""

    @pytest.mark.asyncio
    async def test_postgres_uses_execute(self) -> None:
        inbox = EventInbox(backend_type="postgres", placeholder="%s")
        conn = AsyncMock()
        await inbox.create_table(conn)

        # Should call execute for table + 2 indexes = 3 calls
        assert conn.execute.call_count == 3
        conn.executescript.assert_not_called()

    @pytest.mark.asyncio
    async def test_postgres_does_not_call_commit(self) -> None:
        """Postgres path should not call commit."""
        inbox = EventInbox(backend_type="postgres", placeholder="%s")
        conn = AsyncMock()
        await inbox.create_table(conn)
        conn.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_postgres_table_sql_uses_now(self) -> None:
        """Postgres CREATE TABLE should use now()::text, not datetime('now')."""
        from dazzle_back.events.inbox import CREATE_INBOX_TABLE_POSTGRES

        assert "now()::text" in CREATE_INBOX_TABLE_POSTGRES
        assert "datetime('now')" not in CREATE_INBOX_TABLE_POSTGRES


class TestInboxMarkProcessedPostgres:
    """Test mark_processed uses correct SQL for Postgres."""

    @pytest.mark.asyncio
    async def test_postgres_uses_on_conflict(self) -> None:
        inbox = EventInbox(backend_type="postgres", placeholder="%s")
        conn = AsyncMock()
        cursor_mock = AsyncMock()
        cursor_mock.rowcount = 1
        conn.execute.return_value = cursor_mock

        from uuid import uuid4

        result = await inbox.mark_processed(conn, uuid4(), "test-consumer")

        call_args = conn.execute.call_args
        sql = call_args[0][0]
        assert "ON CONFLICT DO NOTHING" in sql
        assert "INSERT OR IGNORE" not in sql
        assert result is True

    @pytest.mark.asyncio
    async def test_sqlite_uses_insert_or_ignore(self) -> None:
        inbox = EventInbox(backend_type="sqlite", placeholder="?")
        conn = AsyncMock()
        cursor_mock = AsyncMock()
        cursor_mock.rowcount = 1
        conn.execute.return_value = cursor_mock

        from uuid import uuid4

        await inbox.mark_processed(conn, uuid4(), "test-consumer")

        call_args = conn.execute.call_args
        sql = call_args[0][0]
        assert "INSERT OR IGNORE" in sql
        assert "ON CONFLICT DO NOTHING" not in sql
