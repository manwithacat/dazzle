"""
HLESS Event Bus Conformance Tests.

Tests the event bus against HLESS (High-Level Event Semantics Specification)
requirements with novel DSL configurations:

1. RecordKind semantics (INTENT, FACT, OBSERVATION, DERIVATION)
2. Causality tracking (correlation_id, causation_id chains)
3. Idempotency strategies (per RecordKind defaults)
4. Multi-stream derivation lineage
5. Time semantics (t_event, t_log, t_process)

These tests verify that our internal Dazzle-native event vocabulary
works correctly before deploying to production Kafka.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from dazzle_back.events.bus import EventBus, NackReason
from dazzle_back.events.dev_memory import DevBusMemory
from dazzle_back.events.dev_sqlite import DevBrokerSQLite
from dazzle_back.events.envelope import EventEnvelope

# Check if Kafka is available for testing
try:
    from dazzle_back.events.kafka_bus import KAFKA_AVAILABLE, KafkaBus, KafkaConfig

    KAFKA_TEST_ENABLED = KAFKA_AVAILABLE and os.getenv("KAFKA_BOOTSTRAP_SERVERS")
except ImportError:
    KAFKA_TEST_ENABLED = False
    KafkaBus = None  # type: ignore
    KafkaConfig = None  # type: ignore


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
async def memory_bus() -> AsyncGenerator[DevBusMemory, None]:
    """Create a DevBusMemory instance."""
    bus = DevBusMemory()
    yield bus


@pytest.fixture
async def sqlite_bus() -> AsyncGenerator[DevBrokerSQLite, None]:
    """Create a DevBrokerSQLite instance."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "hless_test.db"
        async with DevBrokerSQLite(db_path) as bus:
            yield bus


# Dynamic params - only include available implementations (no skip noise)
_BUS_PARAMS = [
    pytest.param("memory", id="memory"),
    pytest.param("sqlite", id="sqlite"),
]
if KAFKA_TEST_ENABLED:
    _BUS_PARAMS.append(pytest.param("kafka", id="kafka"))


@pytest.fixture(params=_BUS_PARAMS)
async def any_bus(
    request: pytest.FixtureRequest,
    memory_bus: DevBusMemory,
    sqlite_bus: DevBrokerSQLite,
) -> AsyncGenerator[EventBus, None]:
    """Parametrized fixture for all available bus implementations."""
    if request.param == "memory":
        yield memory_bus
    elif request.param == "sqlite":
        yield sqlite_bus
    elif request.param == "kafka":
        config = KafkaConfig.from_env()  # type: ignore
        async with KafkaBus(config) as bus:  # type: ignore
            yield bus


async def dispatch_events(bus: EventBus, topic: str, group_id: str) -> None:
    """Dispatch pending events to subscribers."""
    if isinstance(bus, DevBusMemory):
        await bus.process_pending(topic, group_id)
    elif isinstance(bus, DevBrokerSQLite):
        await bus.poll_and_process(topic, group_id)


# =============================================================================
# HLESS RecordKind Tests
# =============================================================================


class TestHLESSRecordKinds:
    """Tests for proper handling of HLESS RecordKind semantics."""

    @pytest.mark.asyncio
    async def test_intent_flow_with_expected_outcomes(self, any_bus: EventBus) -> None:
        """
        Test INTENT → FACT flow with expected outcomes.

        INTENT: OrderPlacementRequested (may lead to OrderPlaced or OrderRejected)
        FACT: OrderPlaced (permanent truth)

        This tests the core intent/fact separation in event-first architecture.
        """
        intent_received: list[EventEnvelope] = []
        fact_received: list[EventEnvelope] = []

        async def intent_handler(event: EventEnvelope) -> None:
            intent_received.append(event)

        async def fact_handler(event: EventEnvelope) -> None:
            fact_received.append(event)

        # Subscribe to intent and fact topics
        await any_bus.subscribe("orders.intent", "order-processor", intent_handler)
        await any_bus.subscribe("orders.fact", "order-projector", fact_handler)

        # Publish INTENT
        correlation_id = uuid4()
        intent = EventEnvelope.create(
            event_type="orders.intent.OrderPlacementRequested",
            key="order-123",
            payload={
                "order_id": "order-123",
                "customer_id": "cust-456",
                "amount": 99.99,
                "request_id": str(uuid4()),  # Idempotency key
            },
            correlation_id=correlation_id,
            headers={"record_kind": "INTENT"},
        )
        await any_bus.publish("orders.intent", intent)

        # Process INTENT
        await dispatch_events(any_bus, "orders.intent", "order-processor")
        assert len(intent_received) == 1
        assert intent_received[0].action == "OrderPlacementRequested"

        # Publish FACT (caused by the intent)
        fact = EventEnvelope.create(
            event_type="orders.fact.OrderPlaced",
            key="order-123",
            payload={
                "order_id": "order-123",
                "customer_id": "cust-456",
                "amount": 99.99,
                "t_event": datetime.now(UTC).isoformat(),
            },
            headers={"record_kind": "FACT"},
        ).caused_by(intent)

        await any_bus.publish("orders.fact", fact)

        # Process FACT
        await dispatch_events(any_bus, "orders.fact", "order-projector")
        assert len(fact_received) == 1
        assert fact_received[0].action == "OrderPlaced"
        assert fact_received[0].causation_id == intent.event_id

    @pytest.mark.asyncio
    async def test_observation_deduplication_window(self, any_bus: EventBus) -> None:
        """
        Test OBSERVATION handling with time-windowed deduplication.

        OBSERVATION records may be duplicated, arrive late, or out of order.
        The system should handle this gracefully with dedup windows.
        """
        observations: list[EventEnvelope] = []

        async def obs_handler(event: EventEnvelope) -> None:
            observations.append(event)

        await any_bus.subscribe("metrics.observation", "metrics-collector", obs_handler)

        # Create observation with fingerprint for deduplication
        observation_fingerprint = str(uuid4())[:8]

        for i in range(3):
            obs = EventEnvelope.create(
                event_type="metrics.observation.TemperatureMeasured",
                key="sensor-001",
                payload={
                    "sensor_id": "sensor-001",
                    "temperature_c": 23.5 + i * 0.1,
                    "observation_fingerprint": observation_fingerprint,
                    "t_event": datetime.now(UTC).isoformat(),
                },
                headers={
                    "record_kind": "OBSERVATION",
                    "source_system": "iot-gateway",
                },
            )
            await any_bus.publish("metrics.observation", obs)

        # All observations should be received (bus doesn't dedupe)
        await dispatch_events(any_bus, "metrics.observation", "metrics-collector")

        # Consumer should receive all 3 (dedup is consumer responsibility)
        assert len(observations) == 3

        # But they all have same fingerprint for app-level deduplication
        fingerprints = {o.payload.get("observation_fingerprint") for o in observations}
        assert len(fingerprints) == 1

    @pytest.mark.asyncio
    async def test_derivation_with_lineage_tracking(self, any_bus: EventBus) -> None:
        """
        Test DERIVATION records with source stream lineage.

        DERIVATION: DailyOrderTotal computed from orders.fact stream.
        Must carry lineage to source records for reproducibility.
        """
        derivations: list[EventEnvelope] = []

        async def deriv_handler(event: EventEnvelope) -> None:
            derivations.append(event)

        await any_bus.subscribe("analytics.derivation", "reporting", deriv_handler)

        # Simulate source facts (these would normally be in orders.fact)
        source_fact_ids = [str(uuid4()) for _ in range(5)]

        # Create DERIVATION with lineage
        derivation = EventEnvelope.create(
            event_type="analytics.derivation.DailyOrderTotal",
            key="2025-01-02",  # Partition by date
            payload={
                "date": "2025-01-02",
                "total_orders": 5,
                "total_revenue": 499.95,
                "source_streams": ["orders.fact"],
                "source_record_ids": source_fact_ids,
                "derivation_function": "sum(amount) where date = '2025-01-02'",
                "t_process": datetime.now(UTC).isoformat(),
            },
            headers={
                "record_kind": "DERIVATION",
                "rebuild_strategy": "full_replay",
            },
        )

        await any_bus.publish("analytics.derivation", derivation)
        await dispatch_events(any_bus, "analytics.derivation", "reporting")

        assert len(derivations) == 1
        assert derivations[0].action == "DailyOrderTotal"
        assert len(derivations[0].payload["source_record_ids"]) == 5


# =============================================================================
# Causality Chain Tests
# =============================================================================


class TestCausalityChains:
    """Tests for proper causality tracking across event chains."""

    @pytest.mark.asyncio
    async def test_three_level_causality_chain(self, any_bus: EventBus) -> None:
        """
        Test a three-level causality chain:
        1. OrderPlaced (FACT) causes
        2. PaymentRequested (INTENT) causes
        3. PaymentProcessed (FACT)

        All should share the same correlation_id.
        """
        events: list[EventEnvelope] = []

        async def collector(event: EventEnvelope) -> None:
            events.append(event)

        await any_bus.subscribe("orders", "chain-test", collector)
        await any_bus.subscribe("payments.intent", "chain-test", collector)
        await any_bus.subscribe("payments.fact", "chain-test", collector)

        # Level 1: OrderPlaced (root of the chain)
        order_placed = EventEnvelope.create(
            event_type="orders.OrderPlaced",
            key="order-chain-001",
            payload={"order_id": "order-chain-001", "amount": 150.00},
        )
        # Correlation is the order_placed event_id (root)
        order_placed = order_placed.with_correlation(order_placed.event_id)

        await any_bus.publish("orders", order_placed)
        await dispatch_events(any_bus, "orders", "chain-test")

        # Level 2: PaymentRequested (caused by OrderPlaced)
        payment_requested = EventEnvelope.create(
            event_type="payments.intent.PaymentRequested",
            key="order-chain-001",
            payload={
                "order_id": "order-chain-001",
                "amount": 150.00,
                "request_id": str(uuid4()),
            },
        ).caused_by(order_placed)

        await any_bus.publish("payments.intent", payment_requested)
        await dispatch_events(any_bus, "payments.intent", "chain-test")

        # Level 3: PaymentProcessed (caused by PaymentRequested)
        payment_processed = EventEnvelope.create(
            event_type="payments.fact.PaymentProcessed",
            key="order-chain-001",
            payload={
                "order_id": "order-chain-001",
                "payment_id": "pay-789",
                "amount": 150.00,
            },
        ).caused_by(payment_requested)

        await any_bus.publish("payments.fact", payment_processed)
        await dispatch_events(any_bus, "payments.fact", "chain-test")

        # Verify chain
        assert len(events) == 3

        # All should share root's correlation_id
        root_correlation = order_placed.event_id
        for event in events:
            assert event.correlation_id == root_correlation

        # Verify causation chain
        assert events[0].causation_id is None  # Root has no cause
        assert events[1].causation_id == events[0].event_id  # Caused by root
        assert events[2].causation_id == events[1].event_id  # Caused by level 2

    @pytest.mark.asyncio
    async def test_fan_out_causality(self, any_bus: EventBus) -> None:
        """
        Test fan-out causality: one event causes multiple downstream events.

        OrderPlaced causes:
        - InventoryReserved
        - EmailQueued
        - PaymentRequested

        All should have same correlation_id and causation_id pointing to OrderPlaced.
        """
        downstream: list[EventEnvelope] = []

        async def collector(event: EventEnvelope) -> None:
            downstream.append(event)

        await any_bus.subscribe("inventory", "fanout", collector)
        await any_bus.subscribe("email", "fanout", collector)
        await any_bus.subscribe("payments", "fanout", collector)

        # Root event
        order_placed = EventEnvelope.create(
            event_type="orders.OrderPlaced",
            key="fanout-order-001",
            payload={"order_id": "fanout-order-001"},
        ).with_correlation(uuid4())

        # Create fan-out events
        inventory = EventEnvelope.create(
            event_type="inventory.InventoryReserved",
            key="fanout-order-001",
            payload={"order_id": "fanout-order-001", "sku": "ITEM-001"},
        ).caused_by(order_placed)

        email = EventEnvelope.create(
            event_type="email.EmailQueued",
            key="fanout-order-001",
            payload={"order_id": "fanout-order-001", "template": "order_confirmation"},
        ).caused_by(order_placed)

        payment = EventEnvelope.create(
            event_type="payments.PaymentRequested",
            key="fanout-order-001",
            payload={"order_id": "fanout-order-001", "amount": 99.99},
        ).caused_by(order_placed)

        await any_bus.publish("inventory", inventory)
        await any_bus.publish("email", email)
        await any_bus.publish("payments", payment)

        await dispatch_events(any_bus, "inventory", "fanout")
        await dispatch_events(any_bus, "email", "fanout")
        await dispatch_events(any_bus, "payments", "fanout")

        assert len(downstream) == 3

        # All should have same correlation
        correlations = {str(e.correlation_id) for e in downstream}
        assert len(correlations) == 1
        assert correlations.pop() == str(order_placed.correlation_id)

        # All should be caused by root
        causations = {str(e.causation_id) for e in downstream}
        assert len(causations) == 1
        assert causations.pop() == str(order_placed.event_id)


# =============================================================================
# Idempotency Tests
# =============================================================================


class TestIdempotencyStrategies:
    """Tests for HLESS idempotency strategies by RecordKind."""

    @pytest.mark.asyncio
    async def test_intent_deterministic_id(self, sqlite_bus: DevBrokerSQLite) -> None:
        """
        Test INTENT idempotency: deterministic ID from request_id.

        Resubmitting the same request_id should not create duplicates
        (consumer responsibility via inbox pattern).
        """
        received: list[EventEnvelope] = []

        async def handler(event: EventEnvelope) -> None:
            received.append(event)

        await sqlite_bus.subscribe("orders.intent", "order-service", handler)

        # Same request_id should be deduplicated at consumer level
        request_id = str(uuid4())

        for _ in range(3):
            intent = EventEnvelope.create(
                event_type="orders.intent.OrderPlacementRequested",
                key="order-idem-001",
                payload={"order_id": "order-idem-001", "request_id": request_id},
            )
            await sqlite_bus.publish("orders.intent", intent)

        # All 3 delivered (dedup is consumer's job)
        for _ in range(3):
            await sqlite_bus.poll_and_process("orders.intent", "order-service")

        # Bus delivers all, consumer should dedupe
        assert len(received) == 3

        # All have same request_id for consumer-level dedup
        request_ids = {r.payload["request_id"] for r in received}
        assert len(request_ids) == 1

    @pytest.mark.asyncio
    async def test_fact_natural_key_idempotency(self, any_bus: EventBus) -> None:
        """
        Test FACT idempotency: natural key + t_event.

        Facts are immutable. Same order_id + t_event = same fact.
        """
        facts: list[EventEnvelope] = []

        async def collector(event: EventEnvelope) -> None:
            facts.append(event)

        await any_bus.subscribe("orders.fact", "projector", collector)

        # Create facts with deterministic IDs
        t_event = datetime.now(UTC)
        order_id = "order-fact-001"

        for _ in range(2):
            fact = EventEnvelope.create(
                event_type="orders.fact.OrderPlaced",
                key=order_id,
                payload={
                    "order_id": order_id,
                    "t_event": t_event.isoformat(),
                    "amount": 50.00,
                    # Deterministic record_id from natural key
                    "record_id": f"hash({order_id},{t_event.isoformat()})",
                },
            )
            await any_bus.publish("orders.fact", fact)

        await dispatch_events(any_bus, "orders.fact", "projector")

        # Both delivered, consumer uses record_id for dedup
        assert len(facts) == 2
        record_ids = {f.payload["record_id"] for f in facts}
        assert len(record_ids) == 1  # Same deterministic ID


# =============================================================================
# Multi-Consumer Group Tests
# =============================================================================


class TestMultiConsumerGroups:
    """Tests for multiple consumer groups receiving same events."""

    @pytest.mark.asyncio
    async def test_broadcast_to_multiple_groups(self, any_bus: EventBus) -> None:
        """
        Test that different consumer groups each receive all events.

        Simulates:
        - Projector: Updates read model
        - Notifier: Sends notifications
        - Auditor: Writes audit log
        """
        projector_events: list[EventEnvelope] = []
        notifier_events: list[EventEnvelope] = []
        auditor_events: list[EventEnvelope] = []

        async def projector(event: EventEnvelope) -> None:
            projector_events.append(event)

        async def notifier(event: EventEnvelope) -> None:
            notifier_events.append(event)

        async def auditor(event: EventEnvelope) -> None:
            auditor_events.append(event)

        # Three consumer groups for same topic
        await any_bus.subscribe("orders.fact", "projector-group", projector)
        await any_bus.subscribe("orders.fact", "notifier-group", notifier)
        await any_bus.subscribe("orders.fact", "auditor-group", auditor)

        # Publish events
        for i in range(5):
            event = EventEnvelope.create(
                event_type="orders.fact.OrderPlaced",
                key=f"order-broadcast-{i}",
                payload={"order_id": f"order-broadcast-{i}", "sequence": i},
            )
            await any_bus.publish("orders.fact", event)

        # Dispatch to all groups
        await dispatch_events(any_bus, "orders.fact", "projector-group")
        await dispatch_events(any_bus, "orders.fact", "notifier-group")
        await dispatch_events(any_bus, "orders.fact", "auditor-group")

        # Each group should receive all 5 events
        assert len(projector_events) == 5
        assert len(notifier_events) == 5
        assert len(auditor_events) == 5


# =============================================================================
# Replay and Recovery Tests
# =============================================================================


class TestReplayAndRecovery:
    """Tests for event replay and recovery scenarios."""

    @pytest.mark.asyncio
    async def test_replay_all_events(self, any_bus: EventBus) -> None:
        """
        Test replaying all events from a topic.

        Essential for rebuilding projections and derivations.
        """
        # Publish some events
        for i in range(10):
            event = EventEnvelope.create(
                event_type="orders.fact.OrderPlaced",
                key=f"order-replay-{i}",
                payload={"order_id": f"order-replay-{i}", "sequence": i},
            )
            await any_bus.publish("orders.fact", event)

        # Replay all
        replayed: list[EventEnvelope] = []
        async for event in any_bus.replay("orders.fact"):
            replayed.append(event)

        assert len(replayed) == 10

        # Should be in order
        sequences = [e.payload["sequence"] for e in replayed]
        assert sequences == list(range(10))

    @pytest.mark.asyncio
    async def test_replay_from_offset(self, sqlite_bus: DevBrokerSQLite) -> None:
        """Test replaying events from a specific offset."""
        # Publish events
        for i in range(10):
            event = EventEnvelope.create(
                event_type="orders.fact.OrderPlaced",
                key=f"order-offset-{i}",
                payload={"sequence": i},
            )
            await sqlite_bus.publish("orders.fact", event)

        # Replay from offset 6 (1-indexed, so 6th event onwards = sequences 5-9)
        replayed: list[EventEnvelope] = []
        async for event in sqlite_bus.replay("orders.fact", from_offset=6):
            replayed.append(event)

        # Should get events 6-10 (1-indexed), which are sequences 5-9
        assert len(replayed) == 5
        sequences = [e.payload["sequence"] for e in replayed]
        assert sequences == [5, 6, 7, 8, 9]


# =============================================================================
# Error Handling Tests
# =============================================================================


class TestErrorHandling:
    """Tests for error handling and DLQ routing."""

    @pytest.mark.asyncio
    async def test_transient_error_redelivery(self, sqlite_bus: DevBrokerSQLite) -> None:
        """
        Test that transient errors cause redelivery.

        Simulates: Database connection timeout, should retry.
        """
        attempts = 0
        processed: list[EventEnvelope] = []

        async def flaky_handler(event: EventEnvelope) -> None:
            nonlocal attempts
            attempts += 1
            if attempts < 2:
                raise ConnectionError("Database timeout")
            processed.append(event)

        await sqlite_bus.subscribe("orders.fact", "flaky-consumer", flaky_handler)

        event = EventEnvelope.create(
            event_type="orders.fact.OrderPlaced",
            key="order-flaky-001",
            payload={"order_id": "order-flaky-001"},
        )
        await sqlite_bus.publish("orders.fact", event)

        # First attempt fails
        await sqlite_bus.poll_and_process("orders.fact", "flaky-consumer")

        # Second attempt succeeds
        await sqlite_bus.poll_and_process("orders.fact", "flaky-consumer")

        assert len(processed) >= 1

    @pytest.mark.asyncio
    async def test_permanent_error_to_dlq(self, sqlite_bus: DevBrokerSQLite) -> None:
        """
        Test that permanent errors route to DLQ.

        Simulates: Schema validation failure, should not retry.
        """
        processed: list[EventEnvelope] = []

        async def validating_handler(event: EventEnvelope) -> None:
            # Check for required field
            if "required_field" not in event.payload:
                # Nack as permanent (non-retryable)
                await sqlite_bus.nack(
                    "orders.fact",
                    "validating-consumer",
                    event.event_id,
                    NackReason.permanent_error("Missing required_field"),
                )
                return
            processed.append(event)

        await sqlite_bus.subscribe("orders.fact", "validating-consumer", validating_handler)

        # Publish invalid event (missing required_field)
        invalid_event = EventEnvelope.create(
            event_type="orders.fact.OrderPlaced",
            key="order-invalid-001",
            payload={"order_id": "order-invalid-001"},  # Missing required_field
        )
        await sqlite_bus.publish("orders.fact", invalid_event)

        await sqlite_bus.poll_and_process("orders.fact", "validating-consumer")

        # Should not be in processed
        assert len(processed) == 0

        # Should be in DLQ
        if hasattr(sqlite_bus, "get_dlq_count"):
            dlq_count = await sqlite_bus.get_dlq_count("orders.fact")
            assert dlq_count >= 1


# =============================================================================
# Time Semantics Tests
# =============================================================================


class TestTimeSemantics:
    """Tests for HLESS time semantics: t_event, t_log, t_process."""

    @pytest.mark.asyncio
    async def test_t_event_preserved_through_bus(self, any_bus: EventBus) -> None:
        """
        Test that t_event (domain occurrence time) is preserved.

        t_event is when the thing occurred in the domain.
        """
        received: list[EventEnvelope] = []

        async def handler(event: EventEnvelope) -> None:
            received.append(event)

        await any_bus.subscribe("orders.fact", "time-test", handler)

        # Set specific t_event (could be in the past)
        t_event = datetime(2025, 1, 1, 12, 0, 0, tzinfo=UTC)

        event = EventEnvelope.create(
            event_type="orders.fact.OrderPlaced",
            key="order-time-001",
            payload={
                "order_id": "order-time-001",
                "t_event": t_event.isoformat(),
            },
        )
        await any_bus.publish("orders.fact", event)
        await dispatch_events(any_bus, "orders.fact", "time-test")

        assert len(received) == 1
        assert received[0].payload["t_event"] == t_event.isoformat()

    @pytest.mark.asyncio
    async def test_t_log_set_on_publish(self, any_bus: EventBus) -> None:
        """
        Test that t_log (append time) is set near publish time.

        t_log is auto-populated when record appended to log.
        """
        before = datetime.now(UTC)

        event = EventEnvelope.create(
            event_type="orders.fact.OrderPlaced",
            key="order-tlog-001",
            payload={"order_id": "order-tlog-001"},
        )
        await any_bus.publish("orders.fact", event)

        after = datetime.now(UTC)

        # Replay to get the stored event
        replayed: list[EventEnvelope] = []
        async for e in any_bus.replay("orders.fact"):
            replayed.append(e)

        assert len(replayed) >= 1

        # Timestamp should be between before and after
        event_ts = replayed[0].timestamp
        assert before <= event_ts <= after

    @pytest.mark.asyncio
    async def test_derivation_t_process(self, any_bus: EventBus) -> None:
        """
        Test that DERIVATION records have t_process.

        t_process is when the derivation was computed.
        """
        received: list[EventEnvelope] = []

        async def handler(event: EventEnvelope) -> None:
            received.append(event)

        await any_bus.subscribe("analytics.derivation", "deriv-test", handler)

        t_process = datetime.now(UTC)

        derivation = EventEnvelope.create(
            event_type="analytics.derivation.DailyTotal",
            key="2025-01-02",
            payload={
                "date": "2025-01-02",
                "total": 1000.00,
                "t_process": t_process.isoformat(),
                "source_streams": ["orders.fact"],
            },
            headers={"record_kind": "DERIVATION"},
        )
        await any_bus.publish("analytics.derivation", derivation)
        await dispatch_events(any_bus, "analytics.derivation", "deriv-test")

        assert len(received) == 1
        assert "t_process" in received[0].payload


# =============================================================================
# Schema Evolution Tests
# =============================================================================


class TestSchemaEvolution:
    """Tests for handling schema evolution in event streams."""

    @pytest.mark.asyncio
    async def test_additive_schema_change(self, any_bus: EventBus) -> None:
        """
        Test handling additive schema change (new field).

        V1: {order_id, amount}
        V2: {order_id, amount, currency}  # New optional field
        """
        received: list[EventEnvelope] = []

        async def handler(event: EventEnvelope) -> None:
            received.append(event)

        await any_bus.subscribe("orders.fact", "schema-test", handler)

        # V1 event
        v1_event = EventEnvelope.create(
            event_type="orders.fact.OrderPlaced",
            key="order-v1",
            payload={"order_id": "order-v1", "amount": 100.00},
            headers={"schema_version": "v1"},
        )
        await any_bus.publish("orders.fact", v1_event)

        # V2 event (with new field)
        v2_event = EventEnvelope.create(
            event_type="orders.fact.OrderPlaced",
            key="order-v2",
            payload={"order_id": "order-v2", "amount": 100.00, "currency": "USD"},
            headers={"schema_version": "v2"},
        )
        await any_bus.publish("orders.fact", v2_event)

        await dispatch_events(any_bus, "orders.fact", "schema-test")

        assert len(received) == 2

        # Both should be processable
        for event in received:
            assert "order_id" in event.payload
            assert "amount" in event.payload

        # V2 has currency
        v2 = next(e for e in received if e.headers.get("schema_version") == "v2")
        assert v2.payload["currency"] == "USD"

    @pytest.mark.asyncio
    async def test_multiple_schemas_same_stream(self, any_bus: EventBus) -> None:
        """
        Test multiple schemas in same stream.

        orders.fact contains: OrderPlaced, OrderRejected, OrderCancelled
        """
        received: list[EventEnvelope] = []

        async def handler(event: EventEnvelope) -> None:
            received.append(event)

        await any_bus.subscribe("orders.fact", "multi-schema", handler)

        # OrderPlaced
        placed = EventEnvelope.create(
            event_type="orders.fact.OrderPlaced",
            key="order-multi-001",
            payload={"order_id": "order-multi-001", "amount": 100.00},
        )
        await any_bus.publish("orders.fact", placed)

        # OrderRejected
        rejected = EventEnvelope.create(
            event_type="orders.fact.OrderRejected",
            key="order-multi-002",
            payload={"order_id": "order-multi-002", "reason": "Insufficient funds"},
        )
        await any_bus.publish("orders.fact", rejected)

        # OrderCancelled
        cancelled = EventEnvelope.create(
            event_type="orders.fact.OrderCancelled",
            key="order-multi-003",
            payload={"order_id": "order-multi-003", "cancelled_by": "customer"},
        )
        await any_bus.publish("orders.fact", cancelled)

        await dispatch_events(any_bus, "orders.fact", "multi-schema")

        assert len(received) == 3

        actions = {e.action for e in received}
        assert actions == {"OrderPlaced", "OrderRejected", "OrderCancelled"}
