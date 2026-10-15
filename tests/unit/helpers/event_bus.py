"""A recording in-memory ``EventBus`` for unit tests of the kept event core.

The in-memory bus (``http/events/dev_memory.py``) was parked in flense ship AR
(DD-006); the outbox publisher, idempotent consumer and ``EventFramework`` tests
only need a bus that records what was published and accepts acks.
"""

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any
from uuid import UUID

from dazzle.http.events.bus import (
    ConsumerStatus,
    EventBus,
    EventHandler,
    NackReason,
    SubscriptionInfo,
)
from dazzle.http.events.envelope import EventEnvelope


class RecordingBus(EventBus):
    """Keeps every published envelope per topic; ack/nack are recorded."""

    def __init__(self) -> None:
        self.published: dict[str, list[EventEnvelope]] = {}
        self.subscriptions: dict[tuple[str, str], EventHandler] = {}
        self.acked: list[UUID] = []
        self.nacked: list[tuple[UUID, NackReason]] = []

    async def publish(
        self, topic: str, envelope: EventEnvelope, *, transactional: bool = False
    ) -> None:
        self.published.setdefault(topic, []).append(envelope)

    async def subscribe(self, topic: str, group_id: str, handler: EventHandler) -> SubscriptionInfo:
        self.subscriptions[(topic, group_id)] = handler
        return SubscriptionInfo(topic=topic, group_id=group_id, handler=handler)

    async def unsubscribe(self, topic: str, group_id: str) -> None:
        self.subscriptions.pop((topic, group_id), None)

    async def ack(self, topic: str, group_id: str, event_id: UUID) -> None:
        self.acked.append(event_id)

    async def nack(self, topic: str, group_id: str, event_id: UUID, reason: NackReason) -> None:
        self.nacked.append((event_id, reason))

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
        for envelope in self.published.get(topic, []):
            yield envelope

    async def get_consumer_status(self, topic: str, group_id: str) -> ConsumerStatus:
        return ConsumerStatus(topic=topic, group_id=group_id, last_offset=0, pending_count=0)

    async def list_topics(self) -> list[str]:
        return sorted(self.published)

    async def list_consumer_groups(self, topic: str) -> list[str]:
        return sorted(g for t, g in self.subscriptions if t == topic)

    async def get_topic_info(self, topic: str) -> dict[str, Any]:
        return {"event_count": len(self.published.get(topic, [])), "consumer_groups": []}

    async def start_consumer_loop(self, poll_interval: float | None = None) -> None:
        """Nothing to poll: delivery is not simulated."""
