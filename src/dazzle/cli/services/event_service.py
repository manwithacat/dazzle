"""CLI-facing event service wrapping event bus operations."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any


class EventService:
    """Event service for CLI usage, using the tier system.

    Provides a clean async interface for event system CLI commands.
    Creates an event bus via the tier factory and connects to the
    appropriate database for outbox operations.
    """

    @asynccontextmanager
    async def _broker(self) -> AsyncIterator[Any]:
        """Get an event bus via the tier system."""
        from dazzle_back import create_bus

        bus = create_bus()
        if hasattr(bus, "connect"):
            await bus.connect()
        try:
            yield bus
        finally:
            await bus.close()

    # ----- Event tailing / replay -----

    async def replay(
        self,
        topic: str,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
        key_filter: str | None = None,
    ) -> AsyncIterator[Any]:
        """Replay events from a topic. Yields event objects."""
        async with self._broker() as bus:
            async for event in bus.replay(
                topic,
                from_timestamp=from_timestamp,
                to_timestamp=to_timestamp,
                key_filter=key_filter,
            ):
                yield event

    # ----- Topic info -----

    async def list_topics(self) -> list[str]:
        """List all topics in the event bus."""
        async with self._broker() as bus:
            result: list[str] = await bus.list_topics()
            return result

    async def get_topic_info(self, topic: str) -> dict[str, Any]:
        """Get info about a specific topic (event_count, consumer_groups, dlq_count)."""
        async with self._broker() as bus:
            result: dict[str, Any] = await bus.get_topic_info(topic)
            return result

    # ----- Dead Letter Queue -----

    async def get_dlq_events(
        self, topic: str | None = None, limit: int = 20
    ) -> list[dict[str, Any]]:
        """List dead letter queue events."""
        async with self._broker() as bus:
            result: list[dict[str, Any]] = await bus.get_dlq_events(topic=topic, limit=limit)
            return result

    async def replay_dlq_event(self, event_id: str, group: str) -> bool:
        """Replay a single event from the DLQ."""
        async with self._broker() as bus:
            result: bool = await bus.replay_dlq_event(event_id, group)
            return result

    async def clear_dlq(self, topic: str | None = None) -> int:
        """Clear events from the dead letter queue."""
        async with self._broker() as bus:
            result: int = await bus.clear_dlq(topic=topic)
            return result

    # ----- Outbox -----

    async def _get_outbox_connection(self) -> Any:
        """Get a database connection for outbox operations."""
        db_url = os.environ.get("DATABASE_URL")
        if db_url:
            import psycopg
            from psycopg.rows import dict_row

            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql://", 1)
            return await psycopg.AsyncConnection.connect(db_url, row_factory=dict_row)
        raise RuntimeError("DATABASE_URL not set. Outbox operations require a database connection.")

    async def outbox_status(self) -> dict[str, Any]:
        """Get outbox stats (pending, publishing, published, failed, oldest_pending)."""
        from dazzle_back.events import EventOutbox

        conn = await self._get_outbox_connection()
        try:
            outbox = EventOutbox()
            await outbox.create_table(conn)
            return await outbox.get_stats(conn)
        finally:
            await conn.close()

    async def outbox_failed_entries(self, limit: int = 20) -> list[Any]:
        """List failed outbox entries."""
        from dazzle_back.events import EventOutbox

        conn = await self._get_outbox_connection()
        try:
            outbox = EventOutbox()
            return await outbox.get_failed_entries(conn, limit=limit)
        finally:
            await conn.close()

    async def outbox_drain(self, timeout: float = 30.0) -> int:
        """Drain pending events from the outbox. Returns count drained."""
        from dazzle_back.events import EventOutbox, OutboxPublisher

        db_url = os.environ.get("DATABASE_URL")
        if not db_url:
            raise RuntimeError("DATABASE_URL not set. Cannot drain outbox.")

        outbox = EventOutbox()
        async with self._broker() as bus:
            import psycopg
            from psycopg.rows import dict_row

            if db_url.startswith("postgres://"):
                db_url = db_url.replace("postgres://", "postgresql://", 1)

            async def connect() -> psycopg.AsyncConnection[dict[str, Any]]:
                return await psycopg.AsyncConnection.connect(db_url, row_factory=dict_row)

            publisher = OutboxPublisher(bus=bus, outbox=outbox, connect=connect)
            return await publisher.drain(timeout=timeout)
