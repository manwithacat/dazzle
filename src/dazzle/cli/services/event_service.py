"""CLI-facing event service wrapping event bus operations."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any


class EventService:
    """Thin wrapper around DevBrokerSQLite + EventOutbox for CLI usage.

    Provides a clean async interface for event system CLI commands.
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    @asynccontextmanager
    async def _broker(self) -> AsyncIterator[Any]:
        """Get a DevBrokerSQLite context manager."""
        from dazzle_back.events import DevBrokerSQLite

        async with DevBrokerSQLite(self._db_path) as bus:
            yield bus

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

    async def outbox_status(self) -> dict[str, Any]:
        """Get outbox stats (pending, publishing, published, failed, oldest_pending)."""
        import aiosqlite

        from dazzle_back.events import EventOutbox

        outbox = EventOutbox()
        async with aiosqlite.connect(self._db_path) as conn:
            await outbox.create_table(conn)
            return await outbox.get_stats(conn)

    async def outbox_failed_entries(self, limit: int = 20) -> list[Any]:
        """List failed outbox entries."""
        import aiosqlite

        from dazzle_back.events import EventOutbox

        outbox = EventOutbox()
        async with aiosqlite.connect(self._db_path) as conn:
            return await outbox.get_failed_entries(conn, limit=limit)

    async def outbox_drain(self, timeout: float = 30.0) -> int:
        """Drain pending events from the outbox. Returns count drained."""
        from dazzle_back.events import EventOutbox, OutboxPublisher

        outbox = EventOutbox()
        async with self._broker() as bus:
            publisher = OutboxPublisher(self._db_path, bus, outbox)
            return await publisher.drain(timeout=timeout)
