"""
Unit tests for Dazzle Event-First Architecture.

Tests the core event infrastructure:
- EventEnvelope: Event schema and serialization
- DevBusMemory: In-memory bus for tests
- EventOutbox: Transactional event publishing
- EventInbox: Idempotent consumer deduplication
- OutboxPublisher: Background publishing
- IdempotentConsumer: Consumer wrapper
- EventFramework: Central orchestrator
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from dazzle_back.events import (
    ConsumerConfig,
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


def _mock_cursor(rows: list[Any] | None = None, one: Any = None) -> MagicMock:
    """Create a mock psycopg-style cursor."""
    cursor = MagicMock()
    cursor.fetchall = AsyncMock(return_value=rows if rows is not None else [])
    cursor.fetchone = AsyncMock(return_value=one)
    cursor.description = []
    cursor.rowcount = 0
    # Support async iteration (for inbox.get_stats etc.)
    cursor.__aiter__ = MagicMock(return_value=iter([]))
    cursor.__anext__ = AsyncMock(side_effect=StopAsyncIteration)
    return cursor


def _mock_pg_conn() -> Any:
    """Create a mock psycopg-style async connection for unit tests."""
    conn = AsyncMock()
    default_cursor = _mock_cursor()
    conn.execute = AsyncMock(return_value=default_cursor)
    conn.cursor.return_value.__aenter__ = AsyncMock(return_value=default_cursor)
    conn.cursor.return_value.__aexit__ = AsyncMock(return_value=None)
    conn.commit = AsyncMock()
    conn.close = AsyncMock()
    conn.rollback = AsyncMock()
    return conn


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
# EventOutbox Tests
# =============================================================================


class TestEventOutbox:
    """Tests for transactional outbox using mock connections."""

    @pytest.fixture
    def outbox(self) -> EventOutbox:
        """Create an outbox instance."""
        return EventOutbox()

    @pytest.mark.asyncio
    async def test_append_and_fetch(self, outbox: EventOutbox) -> None:
        """Test appending and fetching pending events via mock connection."""
        envelope = EventEnvelope.create(
            event_type="app.Order.created",
            key="order-123",
            payload={"amount": 100},
        )

        conn = _mock_pg_conn()

        # After append, fetch_pending should return the row we appended.
        # Build a fake row dict that _row_to_entry can parse.
        fake_row = {
            "id": str(envelope.event_id),
            "topic": "app.Order",
            "event_type": envelope.event_type,
            "key": envelope.key,
            "envelope_json": envelope.to_json(),
            "status": "pending",
            "created_at": datetime.now(UTC).isoformat(),
            "published_at": None,
            "attempts": 0,
            "last_error": None,
            "lock_token": None,
            "lock_expires_at": None,
        }

        fetch_cursor = MagicMock()
        fetch_cursor.fetchall = AsyncMock(return_value=[fake_row])

        # execute returns different cursors depending on call order:
        # first call → append (no return value used), second call → fetch
        conn.execute = AsyncMock(side_effect=[MagicMock(), fetch_cursor])

        await outbox.append(conn, envelope, "app.Order")
        pending = await outbox.fetch_pending(conn, limit=10)

        assert len(pending) == 1
        assert pending[0].topic == "app.Order"
        assert pending[0].status == OutboxStatus.PENDING

    @pytest.mark.asyncio
    async def test_mark_published(self, outbox: EventOutbox) -> None:
        """Test marking an event as published via mock connection."""
        envelope = EventEnvelope.create(
            event_type="app.Order.created",
            key="order-123",
            payload={},
        )
        entry_id = envelope.event_id

        conn = _mock_pg_conn()

        # fetch_pending returns one row; after mark_published returns nothing
        fake_row = {
            "id": str(entry_id),
            "topic": "app.Order",
            "event_type": envelope.event_type,
            "key": envelope.key,
            "envelope_json": envelope.to_json(),
            "status": "pending",
            "created_at": datetime.now(UTC).isoformat(),
            "published_at": None,
            "attempts": 0,
            "last_error": None,
            "lock_token": None,
            "lock_expires_at": None,
        }

        fetch_cursor = MagicMock()
        fetch_cursor.fetchall = AsyncMock(return_value=[fake_row])

        empty_cursor = MagicMock()
        empty_cursor.fetchall = AsyncMock(return_value=[])

        # calls: append, fetch_pending, mark_published (UPDATE), fetch_pending again
        conn.execute = AsyncMock(side_effect=[MagicMock(), fetch_cursor, MagicMock(), empty_cursor])

        await outbox.append(conn, envelope, "app.Order")
        pending = await outbox.fetch_pending(conn)
        await outbox.mark_published(conn, pending[0].id)
        pending_after = await outbox.fetch_pending(conn)

        assert len(pending_after) == 0

    @pytest.mark.asyncio
    async def test_mark_failed_with_retry(self, outbox: EventOutbox) -> None:
        """Test marking an event as failed with retry via mock connection."""
        envelope = EventEnvelope.create(
            event_type="app.Order.created",
            key="order-123",
            payload={},
        )
        entry_id = envelope.event_id

        conn = _mock_pg_conn()

        # fetch_pending returns one row
        fake_row = {
            "id": str(entry_id),
            "topic": "app.Order",
            "event_type": envelope.event_type,
            "key": envelope.key,
            "envelope_json": envelope.to_json(),
            "status": "pending",
            "created_at": datetime.now(UTC).isoformat(),
            "published_at": None,
            "attempts": 0,
            "last_error": None,
            "lock_token": None,
            "lock_expires_at": None,
        }

        fetch_cursor = MagicMock()
        fetch_cursor.fetchall = AsyncMock(return_value=[fake_row])

        # mark_failed does SELECT attempts then UPDATE
        attempts_cursor = MagicMock()
        attempts_cursor.fetchone = AsyncMock(return_value={"attempts": 0})

        # fetch_pending after mark_failed returns same row with attempts=1
        fake_row_after = {**fake_row, "attempts": 1}
        fetch_cursor2 = MagicMock()
        fetch_cursor2.fetchall = AsyncMock(return_value=[fake_row_after])

        conn.execute = AsyncMock(
            side_effect=[
                MagicMock(),  # append INSERT
                fetch_cursor,  # fetch_pending SELECT
                attempts_cursor,  # mark_failed SELECT attempts
                MagicMock(),  # mark_failed UPDATE
                fetch_cursor2,  # fetch_pending after mark_failed
            ]
        )

        await outbox.append(conn, envelope, "app.Order")
        pending = await outbox.fetch_pending(conn)
        entry_id_fetched = pending[0].id

        should_retry = await outbox.mark_failed(conn, entry_id_fetched, "Connection error")
        assert should_retry is True

        pending_after = await outbox.fetch_pending(conn)
        assert len(pending_after) == 1
        assert pending_after[0].attempts == 1

    @pytest.mark.asyncio
    async def test_get_stats(self, outbox: EventOutbox) -> None:
        """Test getting outbox statistics via mock connection."""
        conn = _mock_pg_conn()

        stats_cursor = MagicMock()
        stats_cursor.fetchall = AsyncMock(
            return_value=[
                {"status": "pending", "count": 3, "oldest": None, "newest": None},
            ]
        )
        conn.execute = AsyncMock(return_value=stats_cursor)

        stats = await outbox.get_stats(conn)
        assert stats["pending"] == 3


# =============================================================================
# EventInbox Tests
# =============================================================================


class TestEventInbox:
    """Tests for idempotent consumer inbox using mock connections."""

    @pytest.fixture
    def inbox(self) -> EventInbox:
        """Create an inbox instance."""
        return EventInbox()

    @pytest.mark.asyncio
    async def test_idempotency_check(self, inbox: EventInbox) -> None:
        """Test idempotency check prevents duplicate processing."""
        event_id = uuid4()
        conn = _mock_pg_conn()

        # First should_process: fetchone returns None (not yet processed)
        not_found_cursor = MagicMock()
        not_found_cursor.fetchone = AsyncMock(return_value=None)
        not_found_cursor.rowcount = 1

        # mark_processed INSERT cursor
        insert_cursor = MagicMock()
        insert_cursor.rowcount = 1

        # Second should_process: fetchone returns a row (already processed)
        found_cursor = MagicMock()
        found_cursor.fetchone = AsyncMock(return_value={"event_id": str(event_id)})

        conn.execute = AsyncMock(
            side_effect=[
                not_found_cursor,  # should_process (is_processed SELECT)
                insert_cursor,  # mark_processed INSERT
                found_cursor,  # should_process again (is_processed SELECT)
            ]
        )

        should_process = await inbox.should_process(conn, event_id, "test_consumer")
        assert should_process is True

        await inbox.mark_processed(conn, event_id, "test_consumer")

        should_process_again = await inbox.should_process(conn, event_id, "test_consumer")
        assert should_process_again is False

    @pytest.mark.asyncio
    async def test_different_consumers_independent(self, inbox: EventInbox) -> None:
        """Test that different consumers track independently."""
        event_id = uuid4()
        conn = _mock_pg_conn()

        # mark_processed for consumer1
        insert_cursor = MagicMock()
        insert_cursor.rowcount = 1

        # should_process for consumer2: not found
        not_found_cursor = MagicMock()
        not_found_cursor.fetchone = AsyncMock(return_value=None)

        conn.execute = AsyncMock(
            side_effect=[
                insert_cursor,  # mark_processed consumer1 INSERT
                not_found_cursor,  # should_process consumer2 SELECT
            ]
        )

        await inbox.mark_processed(conn, event_id, "consumer1")
        should_process = await inbox.should_process(conn, event_id, "consumer2")
        assert should_process is True

    @pytest.mark.asyncio
    async def test_mark_error_blocks_reprocessing(self, inbox: EventInbox) -> None:
        """Test that marking error still marks as processed (for DLQ handling)."""
        import json

        event_id = uuid4()
        conn = _mock_pg_conn()

        # mark_error calls mark_processed which calls INSERT
        insert_cursor = MagicMock()
        insert_cursor.rowcount = 1

        # get_entry returns the error row
        error_row = {
            "event_id": str(event_id),
            "consumer_name": "test_consumer",
            "processed_at": datetime.now(UTC).isoformat(),
            "result": "error",
            "result_data": json.dumps({"error": "Processing failed"}),
        }
        get_cursor = MagicMock()
        get_cursor.fetchone = AsyncMock(return_value=error_row)

        conn.execute = AsyncMock(
            side_effect=[
                insert_cursor,  # mark_error → mark_processed INSERT
                get_cursor,  # get_entry SELECT
            ]
        )

        await inbox.mark_error(conn, event_id, "test_consumer", "Processing failed")
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
    async def test_handler_decorator(self) -> None:
        """Test handler decorator for idempotent processing."""
        inbox = EventInbox()
        bus = DevBusMemory()

        mock_conn = _mock_pg_conn()

        # Connect calls create_table (3 executes for CREATE TABLE + 2 indexes)
        # Then: should_process (not found) → mark_processed (INSERT)
        # Then: should_process again (found) → skip
        not_found_cursor = MagicMock()
        not_found_cursor.fetchone = AsyncMock(return_value=None)
        not_found_cursor.rowcount = 0

        insert_cursor = MagicMock()
        insert_cursor.rowcount = 1

        found_cursor = MagicMock()
        found_cursor.fetchone = AsyncMock(return_value={"event_id": "x"})

        # create_table: 3 executes (CREATE TABLE + 2 indexes) → each returns a generic cursor
        create_cursors = [MagicMock() for _ in range(3)]

        mock_conn.execute = AsyncMock(
            side_effect=[
                *create_cursors,  # create_table
                not_found_cursor,  # first should_process
                insert_cursor,  # mark_processed
                found_cursor,  # second should_process (duplicate)
            ]
        )

        async def _connect() -> Any:
            return mock_conn

        consumer = IdempotentConsumer(
            inbox=inbox,
            config=ConsumerConfig(consumer_name="test_consumer"),
            bus=bus,
            connect=_connect,
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
    async def test_drain_outbox(self) -> None:
        """Test draining events from outbox."""
        bus = DevBusMemory()
        outbox = EventOutbox()

        # Build 3 envelopes that will appear in the outbox
        envelopes = [
            EventEnvelope.create(
                event_type="app.Order.created",
                key=f"order-{i}",
                payload={},
            )
            for i in range(3)
        ]

        mock_conn = _mock_pg_conn()

        # fetch_pending returns the 3 entries, then empty on second call
        fake_rows = [
            {
                "id": str(e.event_id),
                "topic": "app.Order",
                "event_type": e.event_type,
                "key": e.key,
                "envelope_json": e.to_json(),
                "status": "pending",
                "created_at": datetime.now(UTC).isoformat(),
                "published_at": None,
                "attempts": 0,
                "last_error": None,
                "lock_token": None,
                "lock_expires_at": None,
            }
            for e in envelopes
        ]

        # drain calls _process_batch which calls fetch_pending (with lock)
        # The lock path does 2 executes: UPDATE then SELECT
        first_update = MagicMock()  # UPDATE to lock
        first_fetch = MagicMock()
        first_fetch.fetchall = AsyncMock(return_value=fake_rows)

        # After publishing each entry mark_published is called (3 times)
        mark_cursors = [MagicMock() for _ in range(3)]

        # Second _process_batch: lock UPDATE then SELECT returns empty
        second_update = MagicMock()
        second_fetch = MagicMock()
        second_fetch.fetchall = AsyncMock(return_value=[])

        mock_conn.execute = AsyncMock(
            side_effect=[
                first_update,
                first_fetch,
                *mark_cursors,
                second_update,
                second_fetch,
            ]
        )

        async def _connect() -> Any:
            return mock_conn

        publisher = OutboxPublisher(
            bus=bus,
            outbox=outbox,
            config=PublisherConfig(poll_interval=0.1),
            connect=_connect,
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
    async def test_framework_lifecycle(self) -> None:
        """Test framework start and stop."""
        mock_conn = _mock_pg_conn()

        config = EventFrameworkConfig(
            database_url="postgresql://test:test@localhost/test",
            auto_start_publisher=False,
            auto_start_consumers=False,
        )

        framework = EventFramework(config)
        assert not framework.is_running

        with (
            patch("dazzle_back.events.tier.create_bus", return_value=DevBusMemory()),
            patch.object(
                framework, "_make_connect_fn", return_value=AsyncMock(return_value=mock_conn)
            ),
        ):
            await framework.start()
            assert framework.is_running

            await framework.stop()
            assert not framework.is_running

    @pytest.mark.asyncio
    async def test_framework_context_manager(self) -> None:
        """Test framework as context manager."""
        mock_conn = _mock_pg_conn()

        config = EventFrameworkConfig(
            database_url="postgresql://test:test@localhost/test",
            auto_start_publisher=False,
            auto_start_consumers=False,
        )

        framework = EventFramework(config)
        with (
            patch("dazzle_back.events.tier.create_bus", return_value=DevBusMemory()),
            patch.object(
                framework, "_make_connect_fn", return_value=AsyncMock(return_value=mock_conn)
            ),
        ):
            async with framework:
                assert framework.is_running
                assert framework.bus is not None

            assert not framework.is_running

    @pytest.mark.asyncio
    async def test_emit_event(self) -> None:
        """Test emitting events through framework."""
        mock_conn = _mock_pg_conn()

        config = EventFrameworkConfig(
            database_url="postgresql://test:test@localhost/test",
            auto_start_publisher=False,
            auto_start_consumers=False,
        )

        framework = EventFramework(config)

        with (
            patch("dazzle_back.events.tier.create_bus", return_value=DevBusMemory()),
            patch.object(
                framework, "_make_connect_fn", return_value=AsyncMock(return_value=mock_conn)
            ),
        ):
            await framework.start()

            # Emit event through framework using a separate mock connection
            envelope = EventEnvelope.create(
                event_type="app.Order.created",
                key="order-123",
                payload={"amount": 100},
            )
            emit_conn = _mock_pg_conn()
            await framework.emit_event(emit_conn, envelope, "app.Order")

            status = await framework.get_status()
            await framework.stop()

        assert status["events_published"] == 1

    @pytest.mark.asyncio
    async def test_handler_registration(self) -> None:
        """Test registering event handlers."""
        mock_conn = _mock_pg_conn()

        config = EventFrameworkConfig(
            database_url="postgresql://test:test@localhost/test",
            auto_start_publisher=False,
            auto_start_consumers=False,
        )

        framework = EventFramework(config)

        @framework.on("app.Order")
        async def handle_order(event: EventEnvelope) -> None:
            pass

        with (
            patch("dazzle_back.events.tier.create_bus", return_value=DevBusMemory()),
            patch.object(
                framework, "_make_connect_fn", return_value=AsyncMock(return_value=mock_conn)
            ),
        ):
            await framework.start()

            assert framework._stats.active_subscriptions == 1

            await framework.stop()


# =============================================================================
# ConnectFn Injection Tests
# =============================================================================


class TestConnectFnInjection:
    """Tests for ConnectFn-based connection injection in Publisher and Consumer."""

    @pytest.mark.asyncio
    async def test_publisher_with_connect_fn(self) -> None:
        """Verify OutboxPublisher works with connect= kwarg."""
        bus = DevBusMemory()
        outbox = EventOutbox()
        mock_conn = _mock_pg_conn()

        async def _connect() -> Any:
            return mock_conn

        publisher = OutboxPublisher(
            bus=bus,
            outbox=outbox,
            config=PublisherConfig(poll_interval=0.1),
            connect=_connect,
        )

        await publisher.start()
        assert publisher.is_running
        await publisher.stop()
        assert not publisher.is_running

    @pytest.mark.asyncio
    async def test_consumer_with_connect_fn(self) -> None:
        """Verify IdempotentConsumer works with connect= kwarg."""
        bus = DevBusMemory()
        inbox = EventInbox()
        mock_conn = _mock_pg_conn()

        async def _connect() -> Any:
            return mock_conn

        consumer = IdempotentConsumer(
            inbox=inbox,
            config=ConsumerConfig(consumer_name="test_consumer"),
            bus=bus,
            connect=_connect,
        )

        await consumer.connect()
        assert consumer._conn is not None
        await consumer.close()

    def test_publisher_requires_connect_or_db_path(self) -> None:
        """Verify OutboxPublisher raises if connect not provided."""
        bus = DevBusMemory()
        with pytest.raises(ValueError, match="connect is required"):
            OutboxPublisher(bus=bus)

    def test_consumer_requires_connect_or_db_path(self) -> None:
        """Verify IdempotentConsumer raises if connect not provided."""
        with pytest.raises(ValueError, match="connect is required"):
            IdempotentConsumer()

    @pytest.mark.asyncio
    async def test_framework_health_check(self) -> None:
        """Verify health_check() returns expected structure."""
        mock_conn = _mock_pg_conn()

        config = EventFrameworkConfig(
            database_url="postgresql://test:test@localhost/test",
            auto_start_publisher=False,
            auto_start_consumers=False,
        )

        framework = EventFramework(config)
        with (
            patch("dazzle_back.events.tier.create_bus", return_value=DevBusMemory()),
            patch.object(
                framework, "_make_connect_fn", return_value=AsyncMock(return_value=mock_conn)
            ),
        ):
            async with framework:
                health = await framework.health_check()

                assert health["tier"] in ("memory", "postgres", "redis")
                assert health["bus_type"] in ("DevBusMemory", "PostgresBus", "RedisBus")
                assert health["publisher_running"] is False
                assert health["consumer_count"] == 0
                assert "outbox_depth" in health
                assert "last_publish_at" in health
                assert "last_error" in health

    @pytest.mark.asyncio
    async def test_connect_fn_failure_logged(self) -> None:
        """Verify that when connect() raises, an error is logged (not swallowed)."""
        bus = DevBusMemory()
        outbox = EventOutbox()

        async def _failing_connect() -> Any:
            raise ConnectionError("test connection failure")

        publisher = OutboxPublisher(
            bus=bus,
            outbox=outbox,
            connect=_failing_connect,
        )

        with pytest.raises(ConnectionError, match="test connection failure"):
            await publisher.start()
        assert not publisher.is_running


# ---------------------------------------------------------------------------
# RedisBus.start_consumer_loop signature (#662)
# ---------------------------------------------------------------------------


class TestRedisBusSignature:
    """RedisBus.start_consumer_loop must accept poll_interval kwarg (#662)."""

    def test_start_consumer_loop_accepts_poll_interval(self) -> None:
        """RedisBus.start_consumer_loop signature includes poll_interval."""
        import inspect

        from dazzle_back.events.redis_bus import RedisBus

        sig = inspect.signature(RedisBus.start_consumer_loop)
        assert "poll_interval" in sig.parameters
