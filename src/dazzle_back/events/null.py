"""
No-op event system implementations.

Provides NullBus and NullEventFramework for use when the full event system
dependencies (aiosqlite, etc.) are not installed. These implementations
silently accept all operations, allowing application code to use the event
API without conditional checks.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from uuid import UUID

from dazzle_back.events.bus import (
    ConsumerStatus,
    EventBus,
    EventHandler,
    NackReason,
    SubscriptionInfo,
)
from dazzle_back.events.envelope import EventEnvelope

# Probe for aiosqlite — the canary dependency for the full event system.
try:
    import aiosqlite  # noqa: F401

    EVENTS_AVAILABLE: bool = True
except ImportError:
    EVENTS_AVAILABLE = False


class NullBus(EventBus):
    """Event bus that silently discards all operations."""

    async def publish(
        self,
        topic: str,
        envelope: EventEnvelope,
        *,
        transactional: bool = False,
    ) -> None:
        pass

    async def subscribe(
        self,
        topic: str,
        group_id: str,
        handler: EventHandler,
    ) -> SubscriptionInfo:
        return SubscriptionInfo(
            topic=topic,
            group_id=group_id,
            handler=handler,
        )

    async def unsubscribe(self, topic: str, group_id: str) -> None:
        pass

    async def ack(self, topic: str, group_id: str, event_id: UUID) -> None:
        pass

    async def nack(self, topic: str, group_id: str, event_id: UUID, reason: NackReason) -> None:
        pass

    async def replay(
        self,
        topic: str,
        *,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
        from_offset: int | None = None,
        to_offset: int | None = None,
        key_filter: str | None = None,
    ) -> AsyncIterator[EventEnvelope]:
        return
        yield  # pragma: no cover — makes this an async generator

    async def get_consumer_status(self, topic: str, group_id: str) -> ConsumerStatus:
        return ConsumerStatus(
            topic=topic,
            group_id=group_id,
            last_offset=0,
            pending_count=0,
        )

    async def list_topics(self) -> list[str]:
        return []

    async def list_consumer_groups(self, topic: str) -> list[str]:
        return []

    async def get_topic_info(self, topic: str) -> dict[str, Any]:
        return {"event_count": 0, "consumer_groups": []}


class NullEventFramework:
    """
    Duck-typed stand-in for EventFramework when the full event system is unavailable.

    Implements the same public interface so callers don't need conditional checks.
    """

    @property
    def bus(self) -> NullBus:
        return NullBus()

    @property
    def is_running(self) -> bool:
        return False

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def emit_event(
        self,
        conn: Any,
        envelope: EventEnvelope,
        topic: str | None = None,
    ) -> None:
        pass

    async def health_check(self) -> dict[str, Any]:
        return {
            "tier": "null",
            "bus_type": "NullBus",
            "publisher_running": False,
            "consumer_count": 0,
            "outbox_depth": 0,
            "last_publish_at": None,
            "last_error": None,
        }

    async def get_status(self) -> dict[str, Any]:
        return {
            "is_running": False,
            "started_at": None,
            "events_published": 0,
            "events_consumed": 0,
            "active_subscriptions": 0,
            "active_consumers": 0,
            "publisher": {},
            "outbox": {},
            "bus": {"topics": [], "topic_count": 0},
        }

    async def get_outbox_stats(self) -> dict[str, Any]:
        return {"pending": 0, "publishing": 0, "published": 0, "failed": 0}

    async def get_recent_outbox_entries(self, limit: int = 10) -> list[Any]:
        return []

    async def __aenter__(self) -> NullEventFramework:
        await self.start()
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.stop()
