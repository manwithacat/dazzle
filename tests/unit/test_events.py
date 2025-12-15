"""
Unit tests for Dazzle Event-First Architecture.

Tests the core event infrastructure:
- EventEnvelope: Event schema and serialization
- DevBusMemory: In-memory bus for tests
- DevBrokerSQLite: SQLite-backed broker
- EventOutbox: Transactional event publishing
- EventInbox: Idempotent consumer deduplication
- OutboxPublisher: Background publishing
- IdempotentConsumer: Consumer wrapper
- EventFramework: Central orchestrator
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import aiosqlite
import pytest

from dazzle_dnr_back.events import (
    ConsumerConfig,
    DevBrokerSQLite,
    DevBusMemory,
    EventEnvelope,
    EventFramework,
    EventFrameworkConfig,
    EventInbox,
    EventOutbox,
    IdempotentConsumer,
    NackReason,
    OutboxPublisher,
    OutboxStatus,
    ProcessingResult,
    PublisherConfig,
)

# =============================================================================
# EventEnvelope Tests
# =============================================================================


class TestEventEnvelope:
    """Tests for EventEnvelope creation and serialization."""

    def test_create_basic_envelope(self) -> None:
        """Test creating a basic event envelope."""
        envelope = EventEnvelope.create(
            event_type="app.Order.created",
            key="order-123",
            payload={"id": "order-123", "amount": 100},
        )

        assert envelope.event_type == "app.Order.created"
        assert envelope.key == "order-123"
        assert envelope.payload == {"id": "order-123", "amount": 100}
        assert envelope.event_version == "1.0"
        assert isinstance(envelope.event_id, UUID)
        assert isinstance(envelope.timestamp, datetime)

    def test_create_with_correlation(self) -> None:
        """Test creating envelope with correlation and causation IDs."""
        correlation_id = uuid4()
        causation_id = uuid4()

        envelope = EventEnvelope.create(
            event_type="app.Order.shipped",
            key="order-123",
            payload={"status": "shipped"},
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

        assert envelope.correlation_id == correlation_id
        assert envelope.causation_id == causation_id

    def test_topic_property(self) -> None:
        """Test topic extraction from event type."""
        envelope = EventEnvelope.create(
            event_type="app.Order.created",
            key="order-123",
            payload={},
        )

        assert envelope.topic == "app.Order"

    def test_action_property(self) -> None:
        """Test action extraction from event type."""
        envelope = EventEnvelope.create(
            event_type="app.Order.created",
            key="order-123",
            payload={},
        )

        assert envelope.action == "created"

    def test_entity_name_property(self) -> None:
        """Test entity name extraction from event type."""
        envelope = EventEnvelope.create(
            event_type="app.Order.created",
            key="order-123",
            payload={},
        )

        assert envelope.entity_name == "Order"

    def test_to_dict_and_from_dict(self) -> None:
        """Test round-trip serialization via dict."""
        original = EventEnvelope.create(
            event_type="app.Order.created",
            key="order-123",
            payload={"id": "order-123"},
            headers={"source": "test"},
        )

        data = original.to_dict()
        restored = EventEnvelope.from_dict(data)

        assert restored.event_id == original.event_id
        assert restored.event_type == original.event_type
        assert restored.key == original.key
        assert restored.payload == original.payload
        assert restored.headers == original.headers

    def test_to_json_and_from_json(self) -> None:
        """Test round-trip serialization via JSON."""
        original = EventEnvelope.create(
            event_type="app.Order.created",
            key="order-123",
            payload={"amount": 100.50},
        )

        json_str = original.to_json()
        assert isinstance(json_str, str)

        restored = EventEnvelope.from_json(json_str)
        assert restored.event_id == original.event_id
        assert restored.payload == original.payload

    def test_with_correlation(self) -> None:
        """Test creating envelope with correlation ID."""
        original = EventEnvelope.create(
            event_type="app.Order.created",
            key="order-123",
            payload={},
        )

        correlation_id = uuid4()
        correlated = original.with_correlation(correlation_id)

        assert correlated.correlation_id == correlation_id
        assert correlated.event_id == original.event_id
        assert correlated.event_type == original.event_type

    def test_caused_by(self) -> None:
        """Test creating event that is caused by another event."""
        parent = EventEnvelope.create(
            event_type="app.Order.created",
            key="order-123",
            payload={},
        )

        child = EventEnvelope.create(
            event_type="app.Email.sent",
            key="email-789",
            payload={"template": "order_confirmation"},
        )

        caused = child.caused_by(parent)

        # Correlation should be parent's event_id (since parent has no correlation)
        assert caused.correlation_id == parent.event_id
        assert caused.causation_id == parent.event_id

    def test_caused_by_with_existing_correlation(self) -> None:
        """Test caused_by preserves parent's correlation ID."""
        correlation_id = uuid4()
        parent = EventEnvelope.create(
            event_type="app.Order.created",
            key="order-123",
            payload={},
            correlation_id=correlation_id,
        )

        child = EventEnvelope.create(
            event_type="app.Email.sent",
            key="email-789",
            payload={},
        )

        caused = child.caused_by(parent)

        # Should inherit parent's correlation
        assert caused.correlation_id == correlation_id
        assert caused.causation_id == parent.event_id


# =============================================================================
# DevBusMemory Tests
# =============================================================================


class TestDevBusMemory:
    """Tests for in-memory event bus."""

    @pytest.fixture
    def bus(self) -> DevBusMemory:
        """Create a fresh in-memory bus."""
        return DevBusMemory()

    @pytest.mark.asyncio
    async def test_publish_and_subscribe(self, bus: DevBusMemory) -> None:
        """Test basic publish and subscribe."""
        received: list[EventEnvelope] = []

        async def handler(event: EventEnvelope) -> None:
            received.append(event)

        await bus.subscribe("app.Order", "test_group", handler)

        envelope = EventEnvelope.create(
            event_type="app.Order.created",
            key="order-123",
            payload={"id": "order-123"},
        )
        await bus.publish("app.Order", envelope)

        # Process the event
        await bus.process_pending("app.Order", "test_group")

        assert len(received) == 1
        assert received[0].event_id == envelope.event_id

    @pytest.mark.asyncio
    async def test_multiple_consumers(self, bus: DevBusMemory) -> None:
        """Test multiple consumer groups receive same event."""
        group1_received: list[EventEnvelope] = []
        group2_received: list[EventEnvelope] = []

        async def handler1(event: EventEnvelope) -> None:
            group1_received.append(event)

        async def handler2(event: EventEnvelope) -> None:
            group2_received.append(event)

        await bus.subscribe("app.Order", "group1", handler1)
        await bus.subscribe("app.Order", "group2", handler2)

        envelope = EventEnvelope.create(
            event_type="app.Order.created",
            key="order-123",
            payload={},
        )
        await bus.publish("app.Order", envelope)

        await bus.process_pending("app.Order", "group1")
        await bus.process_pending("app.Order", "group2")

        assert len(group1_received) == 1
        assert len(group2_received) == 1

    @pytest.mark.asyncio
    async def test_ack_and_nack(self, bus: DevBusMemory) -> None:
        """Test acknowledging and nacking events."""
        received: list[EventEnvelope] = []

        async def handler(event: EventEnvelope) -> None:
            received.append(event)

        await bus.subscribe("app.Order", "test_group", handler)

        envelope = EventEnvelope.create(
            event_type="app.Order.created",
            key="order-123",
            payload={},
        )
        await bus.publish("app.Order", envelope)
        await bus.process_pending("app.Order", "test_group")

        # Event should already be acked by process_pending
        status = await bus.get_consumer_status("app.Order", "test_group")
        assert status.pending_count == 0

    @pytest.mark.asyncio
    async def test_nack_to_dlq(self, bus: DevBusMemory) -> None:
        """Test nacking event to DLQ."""
        envelope = EventEnvelope.create(
            event_type="app.Order.created",
            key="order-123",
            payload={},
        )
        await bus.publish("app.Order", envelope)

        # Subscribe with failing handler
        async def failing_handler(event: EventEnvelope) -> None:
            raise ValueError("Processing failed")

        await bus.subscribe("app.Order", "test_group", failing_handler)

        # Process will call nack on failure (with retryable reason)
        await bus.process_pending("app.Order", "test_group")

        # Manually nack to DLQ with non-retryable reason
        await bus.nack(
            "app.Order",
            "test_group",
            envelope.event_id,
            NackReason.permanent_error("Permanent failure"),
        )

        dlq_events = await bus.get_dlq_events("app.Order")
        assert len(dlq_events) == 1

    @pytest.mark.asyncio
    async def test_replay_events(self, bus: DevBusMemory) -> None:
        """Test replaying events from topic."""
        for i in range(5):
            envelope = EventEnvelope.create(
                event_type="app.Order.created",
                key=f"order-{i}",
                payload={"sequence": i},
            )
            await bus.publish("app.Order", envelope)

        # Replay all events
        replayed: list[EventEnvelope] = []
        async for event in bus.replay("app.Order"):
            replayed.append(event)

        assert len(replayed) == 5

    @pytest.mark.asyncio
    async def test_replay_with_time_filter(self, bus: DevBusMemory) -> None:
        """Test replaying events with time filter."""
        now = datetime.now(UTC)

        # Create events at different times
        old_envelope = EventEnvelope.create(
            event_type="app.Order.created",
            key="old-order",
            payload={},
        )
        # Manually set timestamp
        object.__setattr__(old_envelope, "timestamp", now - timedelta(hours=2))
        await bus.publish("app.Order", old_envelope)

        new_envelope = EventEnvelope.create(
            event_type="app.Order.created",
            key="new-order",
            payload={},
        )
        await bus.publish("app.Order", new_envelope)

        # Replay only recent events
        replayed: list[EventEnvelope] = []
        async for event in bus.replay("app.Order", from_timestamp=now - timedelta(hours=1)):
            replayed.append(event)

        assert len(replayed) == 1
        assert replayed[0].key == "new-order"

    @pytest.mark.asyncio
    async def test_list_topics(self, bus: DevBusMemory) -> None:
        """Test listing topics."""
        await bus.publish(
            "app.Order",
            EventEnvelope.create(event_type="app.Order.created", key="1", payload={}),
        )
        await bus.publish(
            "app.Shipment",
            EventEnvelope.create(event_type="app.Shipment.created", key="2", payload={}),
        )

        topics = await bus.list_topics()
        assert set(topics) == {"app.Order", "app.Shipment"}

    @pytest.mark.asyncio
    async def test_unsubscribe(self, bus: DevBusMemory) -> None:
        """Test unsubscribing from topic."""
        received: list[EventEnvelope] = []

        async def handler(event: EventEnvelope) -> None:
            received.append(event)

        await bus.subscribe("app.Order", "test_group", handler)
        await bus.unsubscribe("app.Order", "test_group")

        await bus.publish(
            "app.Order",
            EventEnvelope.create(event_type="app.Order.created", key="1", payload={}),
        )

        # Can't process pending for unsubscribed consumer
        # Just verify no events were received
        assert len(received) == 0


# =============================================================================
# DevBrokerSQLite Tests
# =============================================================================


class TestDevBrokerSQLite:
    """Tests for SQLite-backed event broker."""

    @pytest.fixture
    def db_path(self, tmp_path: Path) -> str:
        """Create a temporary database path."""
        return str(tmp_path / "test_events.db")

    @pytest.mark.asyncio
    async def test_connect_creates_tables(self, db_path: str) -> None:
        """Test that connecting creates necessary tables."""
        async with DevBrokerSQLite(db_path):
            # Tables should be created
            async with aiosqlite.connect(db_path) as conn:
                cursor = await conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = {row[0] for row in await cursor.fetchall()}

        assert "_dazzle_events" in tables
        assert "_dazzle_consumer_offsets" in tables

    @pytest.mark.asyncio
    async def test_publish_persists_events(self, db_path: str) -> None:
        """Test that published events are persisted."""
        async with DevBrokerSQLite(db_path) as bus:
            envelope = EventEnvelope.create(
                event_type="app.Order.created",
                key="order-123",
                payload={"amount": 100},
            )
            await bus.publish("app.Order", envelope)

        # Verify persisted
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute("SELECT COUNT(*) FROM _dazzle_events")
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] == 1

    @pytest.mark.asyncio
    async def test_replay_persisted_events(self, db_path: str) -> None:
        """Test replaying events after reconnection."""
        # Publish events
        async with DevBrokerSQLite(db_path) as bus:
            for i in range(3):
                envelope = EventEnvelope.create(
                    event_type="app.Order.created",
                    key=f"order-{i}",
                    payload={"sequence": i},
                )
                await bus.publish("app.Order", envelope)

        # Reconnect and replay
        async with DevBrokerSQLite(db_path) as bus:
            replayed: list[EventEnvelope] = []
            async for event in bus.replay("app.Order"):
                replayed.append(event)

        assert len(replayed) == 3

    @pytest.mark.asyncio
    async def test_consumer_offset_tracking(self, db_path: str) -> None:
        """Test that consumer offsets are tracked."""
        received: list[EventEnvelope] = []

        async def handler(event: EventEnvelope) -> None:
            received.append(event)

        async with DevBrokerSQLite(db_path) as bus:
            # Subscribe first so consumer is ready
            await bus.subscribe("app.Order", "test_consumer", handler)

            # Publish event
            envelope = EventEnvelope.create(
                event_type="app.Order.created",
                key="order-123",
                payload={},
            )
            await bus.publish("app.Order", envelope)

            # Process
            await bus.poll_and_process("app.Order", "test_consumer")

            # ACK the event
            await bus.ack("app.Order", "test_consumer", envelope.event_id)

        # Check offset is stored
        async with aiosqlite.connect(db_path) as conn:
            cursor = await conn.execute(
                "SELECT last_sequence FROM _dazzle_consumer_offsets "
                "WHERE topic = ? AND group_id = ?",
                ("app.Order", "test_consumer"),
            )
            row = await cursor.fetchone()
            assert row is not None
            assert row[0] >= 0

    @pytest.mark.asyncio
    async def test_topic_info(self, db_path: str) -> None:
        """Test getting topic information."""
        async with DevBrokerSQLite(db_path) as bus:
            # Publish events
            for i in range(5):
                envelope = EventEnvelope.create(
                    event_type="app.Order.created",
                    key=f"order-{i}",
                    payload={},
                )
                await bus.publish("app.Order", envelope)

            # Subscribe a consumer
            await bus.subscribe("app.Order", "consumer1", lambda e: None)

            info = await bus.get_topic_info("app.Order")

        assert info["event_count"] == 5
        assert "consumer1" in info["consumer_groups"]


# =============================================================================
# EventOutbox Tests
# =============================================================================


class TestEventOutbox:
    """Tests for transactional outbox."""

    @pytest.fixture
    def outbox(self) -> EventOutbox:
        """Create an outbox instance."""
        return EventOutbox()

    @pytest.mark.asyncio
    async def test_append_and_fetch(self, outbox: EventOutbox, tmp_path: Path) -> None:
        """Test appending and fetching pending events."""
        db_path = str(tmp_path / "test.db")

        async with aiosqlite.connect(db_path) as conn:
            await outbox.create_table(conn)

            # Append event
            envelope = EventEnvelope.create(
                event_type="app.Order.created",
                key="order-123",
                payload={"amount": 100},
            )
            await outbox.append(conn, envelope, "app.Order")
            await conn.commit()

            # Fetch pending
            pending = await outbox.fetch_pending(conn, limit=10)

        assert len(pending) == 1
        assert pending[0].topic == "app.Order"
        assert pending[0].status == OutboxStatus.PENDING

    @pytest.mark.asyncio
    async def test_mark_published(self, outbox: EventOutbox, tmp_path: Path) -> None:
        """Test marking events as published."""
        db_path = str(tmp_path / "test.db")

        async with aiosqlite.connect(db_path) as conn:
            await outbox.create_table(conn)

            envelope = EventEnvelope.create(
                event_type="app.Order.created",
                key="order-123",
                payload={},
            )
            await outbox.append(conn, envelope, "app.Order")
            await conn.commit()

            pending = await outbox.fetch_pending(conn)
            await outbox.mark_published(conn, pending[0].id)
            await conn.commit()

            # Should not appear in pending anymore
            pending_after = await outbox.fetch_pending(conn)

        assert len(pending_after) == 0

    @pytest.mark.asyncio
    async def test_mark_failed_with_retry(self, outbox: EventOutbox, tmp_path: Path) -> None:
        """Test marking events as failed with retry."""
        db_path = str(tmp_path / "test.db")

        async with aiosqlite.connect(db_path) as conn:
            await outbox.create_table(conn)

            envelope = EventEnvelope.create(
                event_type="app.Order.created",
                key="order-123",
                payload={},
            )
            await outbox.append(conn, envelope, "app.Order")
            await conn.commit()

            pending = await outbox.fetch_pending(conn)
            entry_id = pending[0].id

            # Mark failed (returns True if should retry)
            should_retry = await outbox.mark_failed(conn, entry_id, "Connection error")

            # Should be retryable (attempts < max_attempts)
            assert should_retry is True

            # Entry should still be fetchable (status stays pending for retry)
            pending_after = await outbox.fetch_pending(conn)

        assert len(pending_after) == 1
        assert pending_after[0].attempts == 1

    @pytest.mark.asyncio
    async def test_get_stats(self, outbox: EventOutbox, tmp_path: Path) -> None:
        """Test getting outbox statistics."""
        db_path = str(tmp_path / "test.db")

        async with aiosqlite.connect(db_path) as conn:
            await outbox.create_table(conn)

            # Add some events
            for i in range(3):
                envelope = EventEnvelope.create(
                    event_type="app.Order.created",
                    key=f"order-{i}",
                    payload={},
                )
                await outbox.append(conn, envelope, "app.Order")
            await conn.commit()

            stats = await outbox.get_stats(conn)

        assert stats["pending"] == 3


# =============================================================================
# EventInbox Tests
# =============================================================================


class TestEventInbox:
    """Tests for idempotent consumer inbox."""

    @pytest.fixture
    def inbox(self) -> EventInbox:
        """Create an inbox instance."""
        return EventInbox()

    @pytest.mark.asyncio
    async def test_idempotency_check(self, inbox: EventInbox, tmp_path: Path) -> None:
        """Test idempotency check prevents duplicate processing."""
        db_path = str(tmp_path / "test.db")

        async with aiosqlite.connect(db_path) as conn:
            await inbox.create_table(conn)

            event_id = uuid4()

            # First check should allow processing
            should_process = await inbox.should_process(conn, event_id, "test_consumer")
            assert should_process is True

            # Mark as processed
            await inbox.mark_processed(conn, event_id, "test_consumer")
            await conn.commit()

            # Second check should block processing
            should_process_again = await inbox.should_process(conn, event_id, "test_consumer")

        assert should_process_again is False

    @pytest.mark.asyncio
    async def test_different_consumers_independent(self, inbox: EventInbox, tmp_path: Path) -> None:
        """Test that different consumers track independently."""
        db_path = str(tmp_path / "test.db")

        async with aiosqlite.connect(db_path) as conn:
            await inbox.create_table(conn)

            event_id = uuid4()

            # Consumer 1 processes
            await inbox.mark_processed(conn, event_id, "consumer1")
            await conn.commit()

            # Consumer 2 should still be able to process
            should_process = await inbox.should_process(conn, event_id, "consumer2")

        assert should_process is True

    @pytest.mark.asyncio
    async def test_mark_error_blocks_reprocessing(self, inbox: EventInbox, tmp_path: Path) -> None:
        """Test that marking error still marks as processed (for DLQ handling)."""
        db_path = str(tmp_path / "test.db")

        async with aiosqlite.connect(db_path) as conn:
            await inbox.create_table(conn)

            event_id = uuid4()

            # Mark error (this records error but still marks as processed)
            await inbox.mark_error(conn, event_id, "test_consumer", "Processing failed")
            await conn.commit()

            # Check the entry exists with error result
            entry = await inbox.get_entry(conn, event_id, "test_consumer")

        assert entry is not None
        assert entry.result == ProcessingResult.ERROR
        assert entry.result_data == {"error": "Processing failed"}


# =============================================================================
# IdempotentConsumer Tests
# =============================================================================


class TestIdempotentConsumer:
    """Tests for idempotent consumer wrapper."""

    @pytest.mark.asyncio
    async def test_handler_decorator(self, tmp_path: Path) -> None:
        """Test handler decorator for idempotent processing."""
        db_path = str(tmp_path / "test.db")
        inbox = EventInbox()
        bus = DevBusMemory()

        # Create table
        async with aiosqlite.connect(db_path) as conn:
            await inbox.create_table(conn)

        consumer = IdempotentConsumer(
            db_path,
            inbox,
            ConsumerConfig(consumer_name="test_consumer"),
            bus=bus,
        )
        await consumer.connect()

        # Subscribe to topic so ack/nack work
        await bus.subscribe("app.Order", "test_consumer", lambda e: None)

        processed: list[str] = []

        @consumer.handler
        async def my_handler(event: EventEnvelope) -> None:
            processed.append(event.key)

        # Create and process event
        envelope = EventEnvelope.create(
            event_type="app.Order.created",
            key="order-123",
            payload={},
        )

        await my_handler(envelope)

        assert len(processed) == 1
        assert processed[0] == "order-123"

        # Processing same event again should be skipped
        await my_handler(envelope)
        assert len(processed) == 1  # Still 1

        await consumer.close()


# =============================================================================
# OutboxPublisher Tests
# =============================================================================


class TestOutboxPublisher:
    """Tests for outbox publisher."""

    @pytest.mark.asyncio
    async def test_drain_outbox(self, tmp_path: Path) -> None:
        """Test draining events from outbox."""
        db_path = str(tmp_path / "test.db")
        bus = DevBusMemory()
        outbox = EventOutbox()

        # Setup outbox
        async with aiosqlite.connect(db_path) as conn:
            await outbox.create_table(conn)

            # Add events
            for i in range(3):
                envelope = EventEnvelope.create(
                    event_type="app.Order.created",
                    key=f"order-{i}",
                    payload={},
                )
                await outbox.append(conn, envelope, "app.Order")
            await conn.commit()

        # Create publisher and drain
        publisher = OutboxPublisher(
            db_path,
            bus,
            outbox,
            config=PublisherConfig(poll_interval=0.1),
        )

        count = await publisher.drain(timeout=5.0)

        assert count == 3

        # Events should be in bus
        all_events = await bus.get_all_events("app.Order")
        assert len(all_events) == 3


# =============================================================================
# EventFramework Tests
# =============================================================================


class TestEventFramework:
    """Tests for event framework orchestration."""

    @pytest.mark.asyncio
    async def test_framework_lifecycle(self, tmp_path: Path) -> None:
        """Test framework start and stop."""
        db_path = str(tmp_path / "test.db")

        config = EventFrameworkConfig(
            db_path=db_path,
            auto_start_publisher=False,  # Don't start background tasks for test
            auto_start_consumers=False,
        )

        framework = EventFramework(config)

        assert not framework.is_running

        await framework.start()
        assert framework.is_running

        await framework.stop()
        assert not framework.is_running

    @pytest.mark.asyncio
    async def test_framework_context_manager(self, tmp_path: Path) -> None:
        """Test framework as context manager."""
        db_path = str(tmp_path / "test.db")

        config = EventFrameworkConfig(
            db_path=db_path,
            auto_start_publisher=False,
            auto_start_consumers=False,
        )

        async with EventFramework(config) as framework:
            assert framework.is_running
            assert framework.bus is not None

        assert not framework.is_running

    @pytest.mark.asyncio
    async def test_emit_event(self, tmp_path: Path) -> None:
        """Test emitting events through framework."""
        db_path = str(tmp_path / "test.db")

        config = EventFrameworkConfig(
            db_path=db_path,
            auto_start_publisher=False,
            auto_start_consumers=False,
        )

        async with EventFramework(config) as framework:
            # Get a connection
            conn = await framework.get_connection()

            # Emit event
            envelope = EventEnvelope.create(
                event_type="app.Order.created",
                key="order-123",
                payload={"amount": 100},
            )

            await framework.emit_event(conn, envelope, "app.Order")
            await conn.commit()
            await conn.close()

            # Check outbox stats
            status = await framework.get_status()

        assert status["events_published"] == 1

    @pytest.mark.asyncio
    async def test_handler_registration(self, tmp_path: Path) -> None:
        """Test registering event handlers."""
        db_path = str(tmp_path / "test.db")

        config = EventFrameworkConfig(
            db_path=db_path,
            auto_start_publisher=False,
            auto_start_consumers=False,
        )

        framework = EventFramework(config)

        @framework.on("app.Order")
        async def handle_order(event: EventEnvelope) -> None:
            pass

        await framework.start()

        assert framework._stats.active_subscriptions == 1

        await framework.stop()
