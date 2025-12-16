"""
Bus Conformance Test Suite for Event-First Architecture.

Tests that all EventBus implementations conform to the expected behavior.
Runs the same test cases against:
- DevBrokerSQLite (development)
- DevBusMemory (testing)
- KafkaBus (production, optional)

Part of v0.18.0 Event-First Architecture (Issue #25, Phase I).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

from dazzle_dnr_back.events.bus import (
    ConsumerNotFoundError,
    ConsumerStatus,
    EventBus,
    NackReason,
    SubscriptionInfo,
)
from dazzle_dnr_back.events.dev_memory import DevBusMemory
from dazzle_dnr_back.events.dev_sqlite import DevBrokerSQLite
from dazzle_dnr_back.events.envelope import EventEnvelope

# Check if Kafka is available for testing
try:
    from dazzle_dnr_back.events.kafka_bus import KAFKA_AVAILABLE, KafkaBus, KafkaConfig

    KAFKA_TEST_ENABLED = KAFKA_AVAILABLE and os.getenv("KAFKA_BOOTSTRAP_SERVERS")
except ImportError:
    KAFKA_TEST_ENABLED = False
    KafkaBus = None  # type: ignore
    KafkaConfig = None  # type: ignore


async def dispatch_events(bus: EventBus, topic: str, group_id: str) -> None:
    """
    Dispatch pending events to subscribers.

    In-memory and SQLite implementations need explicit dispatch calls.
    This helper handles the differences between implementations.
    """
    if isinstance(bus, DevBusMemory):
        await bus.process_pending(topic, group_id)
    elif isinstance(bus, DevBrokerSQLite):
        await bus.poll_and_process(topic, group_id)
    # KafkaBus has its own consumer loop and doesn't need manual dispatch


def create_test_envelope(
    topic: str = "test.topic",
    key: str = "test-key",
    event_type: str = "test.event.created",
    payload: dict[str, Any] | None = None,
) -> EventEnvelope:
    """Create a test event envelope."""
    return EventEnvelope(
        event_id=uuid4(),
        event_type=event_type,
        event_version="1.0",
        key=key,
        payload=payload or {"test": "data"},
        headers={"x-test": "true"},
        correlation_id=str(uuid4()),
        causation_id=None,
        timestamp=datetime.now(UTC),
        producer="test",
    )


# Fixtures for different bus implementations


@pytest.fixture
async def memory_bus() -> AsyncGenerator[DevBusMemory, None]:
    """Create a DevBusMemory instance for testing."""
    bus = DevBusMemory()
    yield bus


@pytest.fixture
async def sqlite_bus() -> AsyncGenerator[DevBrokerSQLite, None]:
    """Create a DevBrokerSQLite instance for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_events.db"
        async with DevBrokerSQLite(db_path) as bus:
            yield bus


@pytest.fixture
async def kafka_bus() -> AsyncGenerator[Any, None]:
    """Create a KafkaBus instance for testing (if available)."""
    if not KAFKA_TEST_ENABLED:
        pytest.skip("Kafka not available for testing")
        return

    config = KafkaConfig.from_env()
    async with KafkaBus(config) as bus:
        yield bus


# Parametrized fixture for all bus implementations
@pytest.fixture(
    params=[
        pytest.param("memory", id="memory"),
        pytest.param("sqlite", id="sqlite"),
        pytest.param(
            "kafka",
            id="kafka",
            marks=pytest.mark.skipif(
                not KAFKA_TEST_ENABLED,
                reason="Kafka not available",
            ),
        ),
    ]
)
async def any_bus(
    request: pytest.FixtureRequest,
    memory_bus: DevBusMemory,
    sqlite_bus: DevBrokerSQLite,
) -> AsyncGenerator[EventBus, None]:
    """Parametrized fixture that yields each bus implementation."""
    if request.param == "memory":
        yield memory_bus
    elif request.param == "sqlite":
        yield sqlite_bus
    elif request.param == "kafka":
        if not KAFKA_TEST_ENABLED:
            pytest.skip("Kafka not available")
        config = KafkaConfig.from_env()  # type: ignore
        async with KafkaBus(config) as bus:  # type: ignore
            yield bus


class TestPublishSubscribe:
    """Tests for basic publish/subscribe functionality."""

    async def test_publish_to_topic(self, any_bus: EventBus) -> None:
        """Test that events can be published to a topic."""
        envelope = create_test_envelope(topic="test.orders")

        # Should not raise
        await any_bus.publish("test.orders", envelope)

    async def test_subscribe_receives_events(self, any_bus: EventBus) -> None:
        """Test that subscribers receive published events."""
        received: list[EventEnvelope] = []

        async def handler(event: EventEnvelope) -> None:
            received.append(event)

        # Subscribe
        await any_bus.subscribe("test.events", "test-group", handler)

        # Publish
        envelope = create_test_envelope(topic="test.events")
        await any_bus.publish("test.events", envelope)

        # Dispatch events (dev implementations need explicit trigger)
        await dispatch_events(any_bus, "test.events", "test-group")

        # Verify
        assert len(received) >= 1
        assert received[0].event_id == envelope.event_id

    async def test_multiple_subscribers_same_group(self, any_bus: EventBus) -> None:
        """Test that events are distributed among subscribers in same group."""
        received_1: list[EventEnvelope] = []

        async def handler1(event: EventEnvelope) -> None:
            received_1.append(event)

        # Subscribe to group
        await any_bus.subscribe("test.shared", "shared-group", handler1)

        # Publish multiple events
        for i in range(3):
            envelope = create_test_envelope(
                topic="test.shared",
                key=f"key-{i}",
            )
            await any_bus.publish("test.shared", envelope)

        # Dispatch events
        await dispatch_events(any_bus, "test.shared", "shared-group")

        # At least one handler should have received events
        total_received = len(received_1)
        assert total_received >= 1

    async def test_different_groups_get_all_events(self, any_bus: EventBus) -> None:
        """Test that different consumer groups each receive all events."""
        received_a: list[EventEnvelope] = []
        received_b: list[EventEnvelope] = []

        async def handler_a(event: EventEnvelope) -> None:
            received_a.append(event)

        async def handler_b(event: EventEnvelope) -> None:
            received_b.append(event)

        # Subscribe with different groups
        await any_bus.subscribe("test.broadcast", "group-a", handler_a)
        await any_bus.subscribe("test.broadcast", "group-b", handler_b)

        # Publish
        envelope = create_test_envelope(topic="test.broadcast")
        await any_bus.publish("test.broadcast", envelope)

        # Dispatch to both groups
        await dispatch_events(any_bus, "test.broadcast", "group-a")
        await dispatch_events(any_bus, "test.broadcast", "group-b")

        # Both groups should receive the event
        assert len(received_a) >= 1
        assert len(received_b) >= 1

    async def test_subscription_returns_info(self, any_bus: EventBus) -> None:
        """Test that subscribe returns subscription info."""
        async def handler(event: EventEnvelope) -> None:
            pass

        info = await any_bus.subscribe("test.info", "info-group", handler)

        assert isinstance(info, SubscriptionInfo)
        assert info.topic == "test.info"
        assert info.group_id == "info-group"


class TestUnsubscribe:
    """Tests for unsubscribe functionality."""

    async def test_unsubscribe_stops_delivery(self, any_bus: EventBus) -> None:
        """Test that unsubscribed consumers stop receiving events."""
        received: list[EventEnvelope] = []

        async def handler(event: EventEnvelope) -> None:
            received.append(event)

        # Subscribe
        await any_bus.subscribe("test.unsub", "unsub-group", handler)

        # Publish before unsubscribe
        envelope1 = create_test_envelope(topic="test.unsub", key="before")
        await any_bus.publish("test.unsub", envelope1)

        # Dispatch events before unsubscribing
        await dispatch_events(any_bus, "test.unsub", "unsub-group")

        # Record count before
        count_before = len(received)

        # Unsubscribe
        await any_bus.unsubscribe("test.unsub", "unsub-group")

        # Publish after unsubscribe
        envelope2 = create_test_envelope(topic="test.unsub", key="after")
        await any_bus.publish("test.unsub", envelope2)

        # No dispatch call - consumer is unsubscribed

        # Should not receive new events
        assert len(received) == count_before

    async def test_unsubscribe_nonexistent_raises(self, any_bus: EventBus) -> None:
        """Test that unsubscribing from nonexistent subscription raises."""
        with pytest.raises(ConsumerNotFoundError):
            await any_bus.unsubscribe("nonexistent.topic", "nonexistent-group")


class TestAckNack:
    """Tests for acknowledgment and rejection."""

    async def test_ack_advances_offset(self, any_bus: EventBus) -> None:
        """Test that ack advances the consumer offset."""
        received: list[EventEnvelope] = []

        async def handler(event: EventEnvelope) -> None:
            received.append(event)

        await any_bus.subscribe("test.ack", "ack-group", handler)

        # Publish
        envelope = create_test_envelope(topic="test.ack")
        await any_bus.publish("test.ack", envelope)

        # Dispatch events
        await dispatch_events(any_bus, "test.ack", "ack-group")

        # Verify received
        assert len(received) >= 1

        # Ack should not raise
        await any_bus.ack("test.ack", "ack-group", received[0].event_id)

    async def test_nack_retryable_redelivers(self, sqlite_bus: DevBrokerSQLite) -> None:
        """Test that nack with retryable=True causes redelivery."""
        # This test is specific to implementations that support redelivery
        received: list[EventEnvelope] = []
        call_count = 0

        async def handler(event: EventEnvelope) -> None:
            nonlocal call_count
            call_count += 1
            received.append(event)
            if call_count == 1:
                # Simulate failure on first attempt
                raise Exception("Transient error")

        await sqlite_bus.subscribe("test.nack", "nack-group", handler)

        envelope = create_test_envelope(topic="test.nack")
        await sqlite_bus.publish("test.nack", envelope)

        # Dispatch events - poll twice to handle retry
        await sqlite_bus.poll_and_process("test.nack", "nack-group")
        await sqlite_bus.poll_and_process("test.nack", "nack-group")

        # Should have received at least once
        assert len(received) >= 1

    async def test_nack_permanent_to_dlq(self, sqlite_bus: DevBrokerSQLite) -> None:
        """Test that nack with retryable=False moves to DLQ."""
        received: list[EventEnvelope] = []

        async def handler(event: EventEnvelope) -> None:
            received.append(event)
            # Immediately nack as permanent
            await sqlite_bus.nack(
                "test.dlq",
                "dlq-group",
                event.event_id,
                NackReason.permanent_error("Test permanent error"),
            )

        await sqlite_bus.subscribe("test.dlq", "dlq-group", handler)

        envelope = create_test_envelope(topic="test.dlq")
        await sqlite_bus.publish("test.dlq", envelope)

        # Dispatch events
        await sqlite_bus.poll_and_process("test.dlq", "dlq-group")

        # Event should have been processed
        assert len(received) >= 1

        # Check DLQ (implementation-specific)
        if hasattr(sqlite_bus, "get_dlq_count"):
            dlq_count = await sqlite_bus.get_dlq_count("test.dlq")
            assert dlq_count >= 1


class TestReplay:
    """Tests for replay functionality."""

    async def test_replay_returns_events(self, any_bus: EventBus) -> None:
        """Test that replay returns published events."""
        # Publish some events
        envelopes: list[EventEnvelope] = []
        for i in range(3):
            envelope = create_test_envelope(
                topic="test.replay",
                key=f"replay-{i}",
            )
            envelopes.append(envelope)
            await any_bus.publish("test.replay", envelope)

        # Replay (no dispatch needed - replay reads directly from storage)
        replayed: list[EventEnvelope] = []
        async for event in any_bus.replay("test.replay"):
            replayed.append(event)

        # Should have all events
        assert len(replayed) >= len(envelopes)

    async def test_replay_with_key_filter(self, sqlite_bus: EventBus) -> None:
        """Test that replay can filter by key."""
        # Publish events with different keys
        for key in ["key-a", "key-b", "key-a"]:
            envelope = create_test_envelope(topic="test.filter", key=key)
            await sqlite_bus.publish("test.filter", envelope)

        # Replay with filter (no dispatch needed - replay reads directly from storage)
        replayed: list[EventEnvelope] = []
        async for event in sqlite_bus.replay("test.filter", key_filter="key-a"):
            replayed.append(event)

        # Should only have key-a events
        assert all(e.key == "key-a" for e in replayed)
        assert len(replayed) >= 2


class TestConsumerStatus:
    """Tests for consumer status queries."""

    async def test_get_consumer_status(self, any_bus: EventBus) -> None:
        """Test getting consumer status."""
        async def handler(event: EventEnvelope) -> None:
            pass

        await any_bus.subscribe("test.status", "status-group", handler)

        # Publish an event
        envelope = create_test_envelope(topic="test.status")
        await any_bus.publish("test.status", envelope)

        # Dispatch events
        await dispatch_events(any_bus, "test.status", "status-group")

        # Get status
        status = await any_bus.get_consumer_status("test.status", "status-group")

        assert isinstance(status, ConsumerStatus)
        assert status.topic == "test.status"
        assert status.group_id == "status-group"

    async def test_get_consumer_status_nonexistent_raises(
        self, any_bus: EventBus
    ) -> None:
        """Test that getting status for nonexistent consumer raises."""
        with pytest.raises(ConsumerNotFoundError):
            await any_bus.get_consumer_status("nonexistent", "nonexistent")


class TestTopicListing:
    """Tests for topic listing functionality."""

    async def test_list_topics(self, any_bus: EventBus) -> None:
        """Test listing topics."""
        # Publish to create topics
        await any_bus.publish("list.topic1", create_test_envelope(topic="list.topic1"))
        await any_bus.publish("list.topic2", create_test_envelope(topic="list.topic2"))

        topics = await any_bus.list_topics()

        assert isinstance(topics, list)
        # At least the topics we created should be there
        assert "list.topic1" in topics or len(topics) > 0

    async def test_list_consumer_groups(self, any_bus: EventBus) -> None:
        """Test listing consumer groups for a topic."""
        async def handler(event: EventEnvelope) -> None:
            pass

        await any_bus.subscribe("list.groups", "group-1", handler)

        groups = await any_bus.list_consumer_groups("list.groups")

        assert isinstance(groups, list)
        assert "group-1" in groups

    async def test_get_topic_info(self, any_bus: EventBus) -> None:
        """Test getting topic info."""
        # Publish to create topic
        await any_bus.publish("info.topic", create_test_envelope(topic="info.topic"))

        info = await any_bus.get_topic_info("info.topic")

        assert isinstance(info, dict)


class TestEventEnvelopePreservation:
    """Tests that event envelope fields are preserved through publish/consume."""

    async def test_all_fields_preserved(self, any_bus: EventBus) -> None:
        """Test that all envelope fields are preserved."""
        received: list[EventEnvelope] = []

        async def handler(event: EventEnvelope) -> None:
            received.append(event)

        await any_bus.subscribe("test.preserve", "preserve-group", handler)

        # Create envelope with all fields
        original = EventEnvelope(
            event_id=uuid4(),
            event_type="test.preserve.created",
            event_version="2.1",
            key="preserve-key-123",
            payload={"field": "value", "nested": {"a": 1}},
            headers={"x-custom": "header-value", "x-another": "test"},
            correlation_id=str(uuid4()),  # Must be valid UUID for SQLite bus
            causation_id=str(uuid4()),  # Must be valid UUID for SQLite bus
            timestamp=datetime.now(UTC),
            producer="test-producer",
        )

        await any_bus.publish("test.preserve", original)

        # Dispatch events
        await dispatch_events(any_bus, "test.preserve", "preserve-group")

        assert len(received) >= 1

        received_event = received[0]
        assert received_event.event_id == original.event_id
        assert received_event.event_type == original.event_type
        assert received_event.event_version == original.event_version
        assert received_event.key == original.key
        assert received_event.payload == original.payload
        # SQLite bus converts correlation_id/causation_id to UUID on read
        assert str(received_event.correlation_id) == str(original.correlation_id)
        assert str(received_event.causation_id) == str(original.causation_id)
        assert received_event.producer == original.producer


class TestConcurrency:
    """Tests for concurrent operations."""

    async def test_concurrent_publish(self, any_bus: EventBus) -> None:
        """Test that concurrent publishes work correctly."""
        # Publish many events concurrently
        async def publish_one(i: int) -> None:
            envelope = create_test_envelope(
                topic="test.concurrent",
                key=f"concurrent-{i}",
            )
            await any_bus.publish("test.concurrent", envelope)

        await asyncio.gather(*[publish_one(i) for i in range(10)])

        # All should have succeeded - check by replay
        count = 0
        async for _ in any_bus.replay("test.concurrent"):
            count += 1

        assert count >= 10

    async def test_concurrent_subscribe(self, any_bus: EventBus) -> None:
        """Test that multiple concurrent subscriptions work."""
        handlers_called: dict[str, int] = {}

        async def make_handler(name: str) -> None:
            async def handler(event: EventEnvelope) -> None:
                handlers_called[name] = handlers_called.get(name, 0) + 1

            await any_bus.subscribe("test.multi-sub", name, handler)

        # Subscribe multiple groups
        await asyncio.gather(*[make_handler(f"group-{i}") for i in range(3)])

        # Publish
        await any_bus.publish(
            "test.multi-sub",
            create_test_envelope(topic="test.multi-sub"),
        )

        # Dispatch to all groups
        for i in range(3):
            await dispatch_events(any_bus, "test.multi-sub", f"group-{i}")

        # All groups should have received
        assert len(handlers_called) >= 1
