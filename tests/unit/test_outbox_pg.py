"""Tests for EventOutbox (PostgreSQL-only)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.back.events.outbox import EventOutbox

pytestmark = pytest.mark.postgres


class TestOutboxCreateTable:
    """Test create_table with Postgres backend."""

    @pytest.mark.asyncio
    async def test_postgres_uses_execute(self) -> None:
        outbox = EventOutbox()
        conn = AsyncMock()
        await outbox.create_table(conn)

        # Should call execute for: CREATE TABLE (1) + SET lock_timeout (1)
        # + 3 CREATE INDEXes (3) + SET lock_timeout='0' reset (1) = 6 calls.
        # The lock_timeout pair was added in #1072 fix to prevent startup
        # from hanging when an orphan subprocess holds the outbox table.
        assert conn.execute.call_count == 6

    @pytest.mark.asyncio
    async def test_postgres_commits_after_ddl(self) -> None:
        """Postgres path must commit DDL so tables are visible to other connections."""
        outbox = EventOutbox()
        conn = AsyncMock()
        await outbox.create_table(conn)
        conn.commit.assert_called_once()


class TestOutboxAppend:
    """Test append uses correct placeholder style."""

    @pytest.mark.asyncio
    async def test_uses_percent_s_placeholders(self) -> None:
        outbox = EventOutbox()
        conn = AsyncMock()

        envelope = MagicMock()
        envelope.event_id = MagicMock()
        envelope.event_id.__str__ = lambda self: "test-id"
        envelope.topic = "test.topic"
        envelope.event_type = "TestEvent"
        envelope.key = "key-1"
        envelope.to_json.return_value = "{}"

        await outbox.append(conn, envelope)

        call_args = conn.execute.call_args
        sql = call_args[0][0]
        assert "%s" in sql
        assert "?" not in sql
