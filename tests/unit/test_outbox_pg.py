"""Tests for EventOutbox (PostgreSQL-only)."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle.http.events.outbox import EventOutbox

pytestmark = pytest.mark.postgres


def _conn(*, indexes_exist: bool) -> AsyncMock:
    """Mock Postgres connection whose `pg_indexes` probe reports every
    outbox index as present (`indexes_exist=True`) or absent."""
    conn = AsyncMock()
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(return_value=(1,) if indexes_exist else None)
    conn.execute = AsyncMock(return_value=cursor)
    return conn


class TestOutboxCreateTable:
    """Test create_table with Postgres backend."""

    @pytest.mark.asyncio
    async def test_creates_indexes_when_absent(self) -> None:
        """First boot: each index missing → probe then CREATE INDEX."""
        outbox = EventOutbox()
        conn = _conn(indexes_exist=False)
        await outbox.create_table(conn)

        # CREATE TABLE (1) + SET lock_timeout (1) + per index: probe +
        # CREATE INDEX (2×3) + SET lock_timeout='0' reset (1) = 9 calls.
        assert conn.execute.call_count == 9
        executed = [call.args[0] for call in conn.execute.call_args_list]
        assert sum("CREATE INDEX" in sql for sql in executed) == 3
        assert sum("pg_indexes" in sql for sql in executed) == 3

    @pytest.mark.asyncio
    async def test_skips_index_ddl_when_already_present(self) -> None:
        """Re-boot: indexes exist → probe only, no `CREATE INDEX` DDL.

        `CREATE INDEX` takes a schema lock that queues behind a
        concurrent poller's row locks (#1161); skipping it on re-boot
        eliminates the multi-second startup stall.
        """
        outbox = EventOutbox()
        conn = _conn(indexes_exist=True)
        await outbox.create_table(conn)

        # CREATE TABLE (1) + SET lock_timeout (1) + 3 probes (3) +
        # SET lock_timeout='0' reset (1) = 6 calls, zero CREATE INDEX.
        assert conn.execute.call_count == 6
        executed = [call.args[0] for call in conn.execute.call_args_list]
        assert not any("CREATE INDEX" in sql for sql in executed)

    @pytest.mark.asyncio
    async def test_postgres_commits_after_ddl(self) -> None:
        """Postgres path must commit DDL so tables are visible to other connections."""
        outbox = EventOutbox()
        conn = _conn(indexes_exist=False)
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
