"""Tests for EventOutbox PostgreSQL hardening."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dazzle_back.events.outbox import EventOutbox


class TestOutboxPostgresFlag:
    """Test that use_postgres flag controls backend selection."""

    def test_use_postgres_true(self) -> None:
        outbox = EventOutbox(use_postgres=True)
        assert outbox._use_postgres is True

    def test_use_postgres_false_default(self) -> None:
        outbox = EventOutbox()
        assert outbox._use_postgres is False

    def test_no_is_postgres_conn_method(self) -> None:
        """_is_postgres_conn should be removed."""
        outbox = EventOutbox()
        assert not hasattr(outbox, "_is_postgres_conn")


class TestOutboxCreateTableSQLite:
    """Test create_table with SQLite backend."""

    @pytest.mark.asyncio
    async def test_sqlite_uses_executescript(self) -> None:
        outbox = EventOutbox(use_postgres=False)
        conn = AsyncMock()
        await outbox.create_table(conn)

        conn.executescript.assert_called_once()
        conn.commit.assert_called_once()
        # Should NOT call conn.execute for table creation
        conn.execute.assert_not_called()


class TestOutboxCreateTablePostgres:
    """Test create_table with Postgres backend."""

    @pytest.mark.asyncio
    async def test_postgres_uses_execute(self) -> None:
        outbox = EventOutbox(use_postgres=True)
        conn = AsyncMock()
        await outbox.create_table(conn)

        # Should call execute for table + 3 indexes = 4 calls
        assert conn.execute.call_count == 4
        # Should NOT call executescript
        conn.executescript.assert_not_called()

    @pytest.mark.asyncio
    async def test_postgres_commits_after_ddl(self) -> None:
        """Postgres path must commit DDL so tables are visible to other connections."""
        outbox = EventOutbox(use_postgres=True)
        conn = AsyncMock()
        await outbox.create_table(conn)
        conn.commit.assert_called_once()


class TestOutboxAppendPostgres:
    """Test append uses correct placeholder style."""

    @pytest.mark.asyncio
    async def test_postgres_uses_percent_s_placeholders(self) -> None:
        outbox = EventOutbox(use_postgres=True)
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

    @pytest.mark.asyncio
    async def test_sqlite_uses_question_placeholders(self) -> None:
        outbox = EventOutbox(use_postgres=False)
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
        assert "?" in sql
        assert "$1" not in sql
