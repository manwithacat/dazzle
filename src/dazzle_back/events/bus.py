"""
EventBus Abstract Interface for Dazzle Event-First Architecture.

This module defines the abstract interface that all event bus implementations
must follow. The interface is Kafka-shaped, supporting:
- Topic-based publish/subscribe
- Consumer groups with offset tracking
- Acknowledgment/rejection for at-least-once delivery
- Replay capability for recovery and debugging

Implementations:
- DevBusMemory: In-memory bus for unit tests
- DevBrokerSQLite: SQLite-backed broker for development
- (Future) KafkaBus: Production Kafka implementation
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID

from dazzle_back.events.envelope import EventEnvelope

# Type alias for event handlers
EventHandler = Callable[[EventEnvelope], Awaitable[None]]


@dataclass
class SubscriptionInfo:
    """Information about an active subscription."""

    topic: str
    group_id: str
    handler: EventHandler
    created_at: datetime = field(default_factory=lambda: datetime.now())


@dataclass
class ConsumerStatus:
    """Status information for a consumer group."""

    topic: str
    group_id: str
    last_offset: int
    pending_count: int
    last_processed_at: datetime | None = None


@dataclass
class NackReason:
    """Reason for rejecting an event."""

    code: str
    message: str
    retryable: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def transient_error(cls, message: str) -> NackReason:
        """Create a nack reason for transient errors (will retry)."""
        return cls(code="TRANSIENT_ERROR", message=message, retryable=True)

    @classmethod
    def permanent_error(cls, message: str) -> NackReason:
        """Create a nack reason for permanent errors (goes to DLQ)."""
        return cls(code="PERMANENT_ERROR", message=message, retryable=False)

    @classmethod
    def schema_error(cls, message: str) -> NackReason:
        """Create a nack reason for schema validation failures."""
        return cls(code="SCHEMA_ERROR", message=message, retryable=False)

    @classmethod
    def handler_error(cls, message: str, retryable: bool = True) -> NackReason:
        """Create a nack reason for handler exceptions."""
        return cls(code="HANDLER_ERROR", message=message, retryable=retryable)


class EventBus(ABC):
    """
    Abstract interface for event bus implementations.

    The EventBus follows Kafka-shaped semantics:
    - Topics contain ordered streams of events
    - Consumer groups track their position independently
    - Events are acknowledged or rejected per consumer
    - Replay allows re-processing from a point in time

    Implementations MUST be thread-safe for concurrent publish/subscribe.
    """

    @abstractmethod
    async def publish(
        self,
        topic: str,
        envelope: EventEnvelope,
        *,
        transactional: bool = False,
    ) -> None:
        """
        Publish an event to a topic.

        If transactional=True, the event is written to the outbox instead
        of directly to the bus. Use this when publishing as part of a
        database transaction.

        Args:
            topic: Target topic name
            envelope: Event envelope to publish
            transactional: If True, write to outbox for transactional delivery

        Raises:
            EventBusError: If publish fails
        """
        ...

    @abstractmethod
    async def subscribe(
        self,
        topic: str,
        group_id: str,
        handler: EventHandler,
    ) -> SubscriptionInfo:
        """
        Subscribe to events from a topic.

        Multiple consumers in the same group share the workload (competing
        consumers pattern). Different groups each receive all events.

        The handler is called for each event. If the handler raises an
        exception, the event is automatically nack'd with retryable=True.

        Args:
            topic: Topic to subscribe to
            group_id: Consumer group identifier
            handler: Async function to handle each event

        Returns:
            SubscriptionInfo with subscription details

        Raises:
            EventBusError: If subscription fails
        """
        ...

    @abstractmethod
    async def unsubscribe(
        self,
        topic: str,
        group_id: str,
    ) -> None:
        """
        Unsubscribe a consumer group from a topic.

        Args:
            topic: Topic to unsubscribe from
            group_id: Consumer group identifier

        Raises:
            EventBusError: If unsubscribe fails or subscription doesn't exist
        """
        ...

    @abstractmethod
    async def ack(
        self,
        topic: str,
        group_id: str,
        event_id: UUID,
    ) -> None:
        """
        Acknowledge successful processing of an event.

        Advances the consumer group's offset past this event.

        Args:
            topic: Topic the event was consumed from
            group_id: Consumer group that processed the event
            event_id: ID of the event to acknowledge

        Raises:
            EventBusError: If ack fails
        """
        ...

    @abstractmethod
    async def nack(
        self,
        topic: str,
        group_id: str,
        event_id: UUID,
        reason: NackReason,
    ) -> None:
        """
        Reject an event, indicating processing failed.

        If reason.retryable is True, the event will be redelivered after
        a backoff period. Otherwise, it's moved to the dead letter queue.

        Args:
            topic: Topic the event was consumed from
            group_id: Consumer group that failed to process
            event_id: ID of the event to reject
            reason: Why the event was rejected

        Raises:
            EventBusError: If nack fails
        """
        ...

    @abstractmethod
    def replay(
        self,
        topic: str,
        *,
        from_timestamp: datetime | None = None,
        to_timestamp: datetime | None = None,
        from_offset: int | None = None,
        to_offset: int | None = None,
        key_filter: str | None = None,
    ) -> AsyncIterator[EventEnvelope]:
        """
        Replay events from a topic.

        Events are yielded in order. Use either timestamp or offset range,
        not both. If neither specified, replays all events.

        IMPORTANT: Replay is read-only by default. The returned events
        should be processed through the normal consumer path with
        idempotency checks.

        Args:
            topic: Topic to replay from
            from_timestamp: Start of time range (inclusive)
            to_timestamp: End of time range (exclusive)
            from_offset: Start offset (inclusive)
            to_offset: End offset (exclusive)
            key_filter: Only replay events matching this partition key

        Yields:
            EventEnvelope for each event in range

        Raises:
            EventBusError: If replay fails
        """
        ...

    @abstractmethod
    async def get_consumer_status(
        self,
        topic: str,
        group_id: str,
    ) -> ConsumerStatus:
        """
        Get status information for a consumer group.

        Args:
            topic: Topic the consumer is subscribed to
            group_id: Consumer group identifier

        Returns:
            ConsumerStatus with offset and pending count

        Raises:
            EventBusError: If consumer doesn't exist
        """
        ...

    @abstractmethod
    async def list_topics(self) -> list[str]:
        """
        List all topics in the bus.

        Returns:
            List of topic names
        """
        ...

    @abstractmethod
    async def list_consumer_groups(self, topic: str) -> list[str]:
        """
        List all consumer groups for a topic.

        Args:
            topic: Topic to list consumers for

        Returns:
            List of group IDs
        """
        ...

    @abstractmethod
    async def get_topic_info(self, topic: str) -> dict[str, Any]:
        """
        Get information about a topic.

        Returns:
            Dict with keys: event_count, oldest_event, newest_event,
            consumer_groups, etc.
        """
        ...

    # Convenience methods (non-abstract, built on primitives)

    async def publish_envelope(self, envelope: EventEnvelope) -> None:
        """
        Publish an event, deriving topic from event_type.

        Convenience method that extracts the topic from the envelope's
        event_type (e.g., "app.Order.created" -> "app.Order").
        """
        await self.publish(envelope.topic, envelope)

    async def replay_all(self, topic: str) -> AsyncIterator[EventEnvelope]:
        """
        Replay all events from a topic.

        Convenience method that replays from the beginning.
        """
        async for event in self.replay(topic):
            yield event

    async def connect(self) -> None:
        """Connect to the event bus backend."""

    async def close(self) -> None:
        """Close the event bus and release resources."""


class EventBusError(Exception):
    """Base exception for EventBus errors."""

    pass


class TopicNotFoundError(EventBusError):
    """Raised when a topic doesn't exist."""

    def __init__(self, topic: str) -> None:
        self.topic = topic
        super().__init__(f"Topic not found: {topic}")


class ConsumerNotFoundError(EventBusError):
    """Raised when a consumer group doesn't exist."""

    def __init__(self, topic: str, group_id: str) -> None:
        self.topic = topic
        self.group_id = group_id
        super().__init__(f"Consumer not found: {group_id} on topic {topic}")


class EventNotFoundError(EventBusError):
    """Raised when an event doesn't exist."""

    def __init__(self, event_id: UUID) -> None:
        self.event_id = event_id
        super().__init__(f"Event not found: {event_id}")


class PublishError(EventBusError):
    """Raised when publishing an event fails."""

    def __init__(self, topic: str, reason: str) -> None:
        self.topic = topic
        self.reason = reason
        super().__init__(f"Failed to publish to {topic}: {reason}")


class SubscriptionError(EventBusError):
    """Raised when subscription management fails."""

    def __init__(self, topic: str, group_id: str, reason: str) -> None:
        self.topic = topic
        self.group_id = group_id
        self.reason = reason
        super().__init__(f"Subscription error for {group_id} on {topic}: {reason}")
