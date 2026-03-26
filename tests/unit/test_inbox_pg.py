"""Tests for EventInbox (PostgreSQL-only)."""

from unittest.mock import AsyncMock

import pytest

from dazzle_back.events.inbox import EventInbox

pytestmark = pytest.mark.postgres


class TestInboxCreateTable:
    """Test create_table with Postgres backend."""

    @pytest.mark.asyncio
    async def test_postgres_uses_execute(self) -> None:
        inbox = EventInbox()
        conn = AsyncMock()
        await inbox.create_table(conn)

        # Should call execute for table + 2 indexes = 3 calls
        assert conn.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_postgres_commits_after_ddl(self) -> None:
        """Postgres path must commit DDL so tables are visible to other connections."""
        inbox = EventInbox()
        conn = AsyncMock()
        await inbox.create_table(conn)
        conn.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_postgres_table_sql_uses_now(self) -> None:
        """Postgres CREATE TABLE should use now()::text, not datetime('now')."""
        from dazzle_back.events.inbox import CREATE_INBOX_TABLE

        assert "now()::text" in CREATE_INBOX_TABLE
        assert "datetime('now')" not in CREATE_INBOX_TABLE


class TestInboxMarkProcessed:
    """Test mark_processed uses correct SQL for Postgres."""

    @pytest.mark.asyncio
    async def test_uses_on_conflict(self) -> None:
        inbox = EventInbox()
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
