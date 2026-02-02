"""
In-Memory Event Bus Implementation for Testing.

DevBusMemory provides a simple in-memory implementation of the EventBus
interface for use in unit tests. Events are stored in Python dicts with
no persistence.

Features:
- Fast, synchronous operations (no I/O)
- Full EventBus interface compliance
- Useful for testing consumer logic without infrastructure
- Automatically creates topics on first publish

NOT for production use - all data is lost on process exit.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from dazzle_back.events.bus import (
    ConsumerNotFoundError,
    ConsumerStatus,
    EventBus,
    EventHandler,
    EventNotFoundError,
    NackReason,
    SubscriptionInfo,
)
from dazzle_back.events.envelope import EventEnvelope


@dataclass
class StoredEvent:
    """An event stored in the memory bus."""

    envelope: EventEnvelope
    sequence_num: int
    topic: str


@dataclass
class ConsumerState:
    """State for a consumer group."""

    group_id: str
    handler: EventHandler
    last_offset: int = 0
    last_processed_at: datetime | None = None
    pending_events: list[UUID] = field(default_factory=list)
    nacked_events: dict[UUID, NackReason] = field(default_factory=dict)


class DevBusMemory(EventBus):
    """
    In-memory EventBus implementation for testing.

    Thread-safe through asyncio locks. All topics are auto-created on
    first publish.

    Example:
        bus = DevBusMemory()

        # Publish
        await bus.publish("app.Order", envelope)

        # Subscribe
        async def handler(event: EventEnvelope):
            print(f"Received: {event.event_type}")

        await bus.subscribe("app.Order", "test-consumer", handler)

        # Process pending (for tests)
        await bus.process_pending("app.Order", "test-consumer")
    """

    def __init__(self) -> None:
        # topic -> list of StoredEvent
        self._topics: dict[str, list[StoredEvent]] = defaultdict(list)
        # topic -> sequence counter
        self._sequences: dict[str, int] = defaultdict(int)
        # topic -> group_id -> ConsumerState
        self._consumers: dict[str, dict[str, ConsumerState]] = defaultdict(dict)
        # event_id -> StoredEvent (for quick lookup)
        self._events_by_id: dict[UUID, StoredEvent] = {}
        # Lock for thread safety
        self._lock = asyncio.Lock()
        # DLQ storage: topic -> list of (event, reason)
        self._dlq: dict[str, list[tuple[EventEnvelope, NackReason]]] = defaultdict(list)

    async def publish(
        self,
        topic: str,
        envelope: EventEnvelope,
        *,
        transactional: bool = False,
    ) -> None:
        """
        Publish an event to a topic.

        In DevBusMemory, transactional=True is ignored since there's no
        real outbox - events are stored directly.
        """
        async with self._lock:
            # Auto-increment sequence
            self._sequences[topic] += 1
            seq = self._sequences[topic]

            # Store event
            stored = StoredEvent(
                envelope=envelope,
                sequence_num=seq,
                topic=topic,
            )
            self._topics[topic].append(stored)
            self._events_by_id[envelope.event_id] = stored

            # Mark as pending for all consumers of this topic
            for consumer in self._consumers[topic].values():
                consumer.pending_events.append(envelope.event_id)

    async def subscribe(
        self,
        topic: str,
        group_id: str,
        handler: EventHandler,
    ) -> SubscriptionInfo:
        """Subscribe to events from a topic."""
        async with self._lock:
            # Create consumer state
            consumer = ConsumerState(
                group_id=group_id,
                handler=handler,
                last_offset=self._sequences[topic],  # Start from current position
            )
            self._consumers[topic][group_id] = consumer

            return SubscriptionInfo(
                topic=topic,
                group_id=group_id,
                handler=handler,
            )

    async def unsubscribe(
        self,
        topic: str,
        group_id: str,
    ) -> None:
        """Unsubscribe a consumer group from a topic."""
        async with self._lock:
            if topic not in self._consumers or group_id not in self._consumers[topic]:
                raise ConsumerNotFoundError(topic, group_id)
            del self._consumers[topic][group_id]

    async def ack(
        self,
        topic: str,
        group_id: str,
        event_id: UUID,
    ) -> None:
        """Acknowledge successful processing of an event."""
        async with self._lock:
            if topic not in self._consumers or group_id not in self._consumers[topic]:
                raise ConsumerNotFoundError(topic, group_id)

            consumer = self._consumers[topic][group_id]

            # Remove from pending
            if event_id in consumer.pending_events:
                consumer.pending_events.remove(event_id)

            # Remove from nacked if it was retried
            consumer.nacked_events.pop(event_id, None)

            # Update offset
            if event_id in self._events_by_id:
                stored = self._events_by_id[event_id]
                if stored.sequence_num > consumer.last_offset:
                    consumer.last_offset = stored.sequence_num

            consumer.last_processed_at = datetime.now(UTC)

    async def nack(
        self,
        topic: str,
        group_id: str,
        event_id: UUID,
        reason: NackReason,
    ) -> None:
        """Reject an event, indicating processing failed."""
        async with self._lock:
            if topic not in self._consumers or group_id not in self._consumers[topic]:
                raise ConsumerNotFoundError(topic, group_id)

            if event_id not in self._events_by_id:
                raise EventNotFoundError(event_id)

            consumer = self._consumers[topic][group_id]
            stored = self._events_by_id[event_id]

            if reason.retryable:
                # Keep in nacked for retry
                consumer.nacked_events[event_id] = reason
            else:
                # Move to DLQ
                self._dlq[topic].append((stored.envelope, reason))
                # Remove from pending
                if event_id in consumer.pending_events:
                    consumer.pending_events.remove(event_id)

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
        """Replay events from a topic."""
        async with self._lock:
            if topic not in self._topics:
                return

            events = self._topics[topic]

            for stored in events:
                # Filter by offset
                if from_offset is not None and stored.sequence_num < from_offset:
                    continue
                if to_offset is not None and stored.sequence_num >= to_offset:
                    continue

                # Filter by timestamp
                if from_timestamp is not None and stored.envelope.timestamp < from_timestamp:
                    continue
                if to_timestamp is not None and stored.envelope.timestamp >= to_timestamp:
                    continue

                # Filter by key
                if key_filter is not None and stored.envelope.key != key_filter:
                    continue

                yield stored.envelope

    async def get_consumer_status(
        self,
        topic: str,
        group_id: str,
    ) -> ConsumerStatus:
        """Get status information for a consumer group."""
        async with self._lock:
            if topic not in self._consumers or group_id not in self._consumers[topic]:
                raise ConsumerNotFoundError(topic, group_id)

            consumer = self._consumers[topic][group_id]
            return ConsumerStatus(
                topic=topic,
                group_id=group_id,
                last_offset=consumer.last_offset,
                pending_count=len(consumer.pending_events),
                last_processed_at=consumer.last_processed_at,
            )

    async def list_topics(self) -> list[str]:
        """List all topics in the bus."""
        async with self._lock:
            return list(self._topics.keys())

    async def list_consumer_groups(self, topic: str) -> list[str]:
        """List all consumer groups for a topic."""
        async with self._lock:
            return list(self._consumers.get(topic, {}).keys())

    async def get_topic_info(self, topic: str) -> dict[str, Any]:
        """Get information about a topic."""
        async with self._lock:
            events = self._topics.get(topic, [])
            consumers = self._consumers.get(topic, {})

            return {
                "topic": topic,
                "event_count": len(events),
                "oldest_event": events[0].envelope.timestamp.isoformat() if events else None,
                "newest_event": events[-1].envelope.timestamp.isoformat() if events else None,
                "current_sequence": self._sequences.get(topic, 0),
                "consumer_groups": list(consumers.keys()),
                "dlq_count": len(self._dlq.get(topic, [])),
            }

    # Test helper methods

    async def process_pending(
        self,
        topic: str,
        group_id: str,
        *,
        max_events: int | None = None,
    ) -> int:
        """
        Process pending events for a consumer (test helper).

        In production, this would be done by a consumer loop. For tests,
        this allows synchronous processing of published events.

        Args:
            topic: Topic to process
            group_id: Consumer group to process for
            max_events: Maximum events to process (None = all)

        Returns:
            Number of events processed
        """
        if topic not in self._consumers or group_id not in self._consumers[topic]:
            raise ConsumerNotFoundError(topic, group_id)

        consumer = self._consumers[topic][group_id]
        processed = 0

        # Process pending events
        pending_copy = list(consumer.pending_events)
        for event_id in pending_copy:
            if max_events is not None and processed >= max_events:
                break

            if event_id not in self._events_by_id:
                continue

            stored = self._events_by_id[event_id]

            try:
                await consumer.handler(stored.envelope)
                await self.ack(topic, group_id, event_id)
                processed += 1
            except Exception as e:
                await self.nack(
                    topic,
                    group_id,
                    event_id,
                    NackReason.handler_error(str(e)),
                )

        return processed

    async def get_dlq_events(self, topic: str) -> list[tuple[EventEnvelope, NackReason]]:
        """Get events in the dead letter queue (test helper)."""
        async with self._lock:
            return list(self._dlq.get(topic, []))

    async def clear(self) -> None:
        """Clear all data (test helper)."""
        async with self._lock:
            self._topics.clear()
            self._sequences.clear()
            self._consumers.clear()
            self._events_by_id.clear()
            self._dlq.clear()

    async def get_all_events(self, topic: str) -> list[EventEnvelope]:
        """Get all events for a topic (test helper)."""
        async with self._lock:
            return [s.envelope for s in self._topics.get(topic, [])]

    def event_count(self, topic: str) -> int:
        """Get event count for a topic (sync test helper)."""
        return len(self._topics.get(topic, []))
