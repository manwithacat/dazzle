"""
Test consumers for PRA stress testing.

Provides configurable consumers that simulate various processing behaviors:
- Normal: Process events at full speed
- Slow: Introduce artificial latency (backpressure testing)
- Failing: Randomly fail events (DLQ testing)
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from dazzle_back.events.envelope import EventEnvelope
from dazzle_back.metrics import MetricsCollector

logger = logging.getLogger(__name__)


# Type for processed event handler
ProcessedHandler = Callable[[str, EventEnvelope, float], Any]


@dataclass
class ConsumerStats:
    """Statistics for a test consumer."""

    consumer_name: str
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    events_processed: int = 0
    events_failed: int = 0
    events_dlq: int = 0
    total_processing_ms: float = 0.0

    @property
    def avg_processing_ms(self) -> float:
        if self.events_processed == 0:
            return 0.0
        return self.total_processing_ms / self.events_processed


class TestConsumer(ABC):
    """
    Abstract base class for test consumers.

    Consumers process events from the event bus with configurable behavior.
    """

    def __init__(
        self,
        name: str,
        topics: list[str],
        metrics: MetricsCollector | None = None,
        on_processed: ProcessedHandler | None = None,
    ) -> None:
        """
        Initialize the test consumer.

        Args:
            name: Consumer name for tracking
            topics: Topics to subscribe to
            metrics: Optional metrics collector
            on_processed: Callback when event is processed (topic, envelope, latency_ms)
        """
        self.name = name
        self.topics = topics
        self.metrics = metrics
        self.on_processed = on_processed
        self._stats = ConsumerStats(consumer_name=name)
        self._running = False

    @property
    def stats(self) -> ConsumerStats:
        """Get current consumer statistics."""
        return self._stats

    async def process(self, topic: str, envelope: EventEnvelope) -> bool:
        """
        Process an incoming event.

        Args:
            topic: Source topic
            envelope: Event envelope

        Returns:
            True if processed successfully, False if failed
        """
        start_time = time.monotonic()

        try:
            success = await self._do_process(topic, envelope)

            processing_ms = (time.monotonic() - start_time) * 1000

            if success:
                self._stats.events_processed += 1
                self._stats.total_processing_ms += processing_ms

                if self.metrics:
                    self.metrics.record_latency(f"consumer.{self.name}", processing_ms)
                    self.metrics.record_throughput(f"consumer.{self.name}")

                if self.on_processed:
                    self.on_processed(topic, envelope, processing_ms)
            else:
                self._stats.events_failed += 1
                if self.metrics:
                    self.metrics.record_error("processing_failed")

            return success

        except Exception as e:
            processing_ms = (time.monotonic() - start_time) * 1000
            logger.error(f"Consumer {self.name} error processing event: {e}")
            self._stats.events_failed += 1

            if self.metrics:
                self.metrics.record_error("consumer_exception")

            return False

    @abstractmethod
    async def _do_process(self, topic: str, envelope: EventEnvelope) -> bool:
        """
        Subclass implementation of event processing.

        Args:
            topic: Source topic
            envelope: Event envelope

        Returns:
            True if processed successfully
        """
        ...


class NormalConsumer(TestConsumer):
    """
    Normal consumer that processes events at full speed.

    Used as baseline for performance comparison.
    """

    async def _do_process(self, topic: str, envelope: EventEnvelope) -> bool:
        """Process event immediately."""
        # Simulate minimal work
        return True


class SlowConsumer(TestConsumer):
    """
    Slow consumer that introduces artificial latency.

    Used for backpressure testing.
    """

    def __init__(
        self,
        name: str,
        topics: list[str],
        delay_ms: float = 100.0,
        delay_variance_ms: float = 20.0,
        metrics: MetricsCollector | None = None,
        on_processed: ProcessedHandler | None = None,
    ) -> None:
        """
        Initialize slow consumer.

        Args:
            name: Consumer name
            topics: Topics to subscribe to
            delay_ms: Base processing delay in milliseconds
            delay_variance_ms: Random variance to add
            metrics: Optional metrics collector
            on_processed: Callback when event is processed
        """
        super().__init__(name, topics, metrics, on_processed)
        self.delay_ms = delay_ms
        self.delay_variance_ms = delay_variance_ms

    async def _do_process(self, topic: str, envelope: EventEnvelope) -> bool:
        """Process with artificial delay."""
        delay = self.delay_ms + random.uniform(-self.delay_variance_ms, self.delay_variance_ms)
        delay = max(0, delay)

        await asyncio.sleep(delay / 1000.0)

        return True


class FailingConsumer(TestConsumer):
    """
    Consumer that randomly fails events.

    Used for DLQ and retry testing.
    """

    def __init__(
        self,
        name: str,
        topics: list[str],
        failure_probability: float = 0.1,
        permanent_failure_probability: float = 0.02,
        metrics: MetricsCollector | None = None,
        on_processed: ProcessedHandler | None = None,
    ) -> None:
        """
        Initialize failing consumer.

        Args:
            name: Consumer name
            topics: Topics to subscribe to
            failure_probability: Probability of transient failure
            permanent_failure_probability: Probability of permanent failure (goes to DLQ)
            metrics: Optional metrics collector
            on_processed: Callback when event is processed
        """
        super().__init__(name, topics, metrics, on_processed)
        self.failure_probability = failure_probability
        self.permanent_failure_probability = permanent_failure_probability

    async def _do_process(self, topic: str, envelope: EventEnvelope) -> bool:
        """Process with random failures."""
        r = random.random()

        if r < self.permanent_failure_probability:
            # Permanent failure - goes to DLQ
            self._stats.events_dlq += 1
            if self.metrics:
                self.metrics.record_error("dlq")
            raise ValueError(f"Permanent failure for event {envelope.event_id}")

        if r < self.permanent_failure_probability + self.failure_probability:
            # Transient failure - can be retried
            return False

        return True


class ProjectionConsumer(TestConsumer):
    """
    Consumer that simulates projection updates.

    Tracks multiple entities and their states.
    """

    def __init__(
        self,
        name: str,
        topics: list[str],
        entity_key_field: str = "order_id",
        processing_time_ms: float = 5.0,
        metrics: MetricsCollector | None = None,
        on_processed: ProcessedHandler | None = None,
    ) -> None:
        """
        Initialize projection consumer.

        Args:
            name: Consumer name
            topics: Topics to subscribe to
            entity_key_field: Field to use as entity key
            processing_time_ms: Simulated processing time
            metrics: Optional metrics collector
            on_processed: Callback when event is processed
        """
        super().__init__(name, topics, metrics, on_processed)
        self.entity_key_field = entity_key_field
        self.processing_time_ms = processing_time_ms
        self._projections: dict[str, dict[str, Any]] = {}

    @property
    def projections(self) -> dict[str, dict[str, Any]]:
        """Get current projection state."""
        return self._projections

    async def _do_process(self, topic: str, envelope: EventEnvelope) -> bool:
        """Update projection from event."""
        # Simulate processing time
        await asyncio.sleep(self.processing_time_ms / 1000.0)

        # Extract entity key from payload
        key = envelope.payload.get(self.entity_key_field)
        if key:
            key_str = str(key)
            # Upsert projection
            if key_str not in self._projections:
                self._projections[key_str] = {}

            self._projections[key_str].update(envelope.payload)
            self._projections[key_str]["_last_event_id"] = str(envelope.event_id)
            self._projections[key_str]["_last_event_type"] = envelope.event_type

        return True


class DerivationConsumer(TestConsumer):
    """
    Consumer that simulates derivation rebuilds.

    Tracks sequence numbers for rebuild verification.
    """

    def __init__(
        self,
        name: str,
        topics: list[str],
        processing_time_ms: float = 10.0,
        metrics: MetricsCollector | None = None,
        on_processed: ProcessedHandler | None = None,
    ) -> None:
        """
        Initialize derivation consumer.

        Args:
            name: Consumer name
            topics: Topics to subscribe to
            processing_time_ms: Simulated processing time
            metrics: Optional metrics collector
            on_processed: Callback when event is processed
        """
        super().__init__(name, topics, metrics, on_processed)
        self.processing_time_ms = processing_time_ms
        self._sequence: int = 0
        self._rebuild_start: float | None = None
        self._rebuild_complete: float | None = None

    @property
    def sequence(self) -> int:
        """Get current sequence number."""
        return self._sequence

    @property
    def rebuild_time_ms(self) -> float | None:
        """Get rebuild time if complete."""
        if self._rebuild_start and self._rebuild_complete:
            return (self._rebuild_complete - self._rebuild_start) * 1000
        return None

    def start_rebuild(self) -> None:
        """Mark rebuild start."""
        self._rebuild_start = time.monotonic()
        self._rebuild_complete = None
        self._sequence = 0

    def complete_rebuild(self) -> None:
        """Mark rebuild complete."""
        self._rebuild_complete = time.monotonic()
        if self.metrics and self.rebuild_time_ms:
            # record_recovery_time expects (derivation_name, seconds)
            self.metrics.record_recovery_time(self.name, self.rebuild_time_ms / 1000.0)

    async def _do_process(self, topic: str, envelope: EventEnvelope) -> bool:
        """Process for derivation rebuild."""
        # Simulate processing time
        await asyncio.sleep(self.processing_time_ms / 1000.0)

        self._sequence += 1

        return True


@dataclass
class ConsumerGroup:
    """
    A group of consumers for coordinated testing.

    Allows running multiple consumers with different behaviors.
    """

    name: str
    consumers: list[TestConsumer] = field(default_factory=list)

    def add(self, consumer: TestConsumer) -> None:
        """Add a consumer to the group."""
        self.consumers.append(consumer)

    def get_stats(self) -> dict[str, ConsumerStats]:
        """Get stats for all consumers."""
        return {c.name: c.stats for c in self.consumers}

    def total_processed(self) -> int:
        """Get total events processed across all consumers."""
        return sum(c.stats.events_processed for c in self.consumers)

    def total_failed(self) -> int:
        """Get total failures across all consumers."""
        return sum(c.stats.events_failed for c in self.consumers)

    def total_dlq(self) -> int:
        """Get total DLQ events across all consumers."""
        return sum(c.stats.events_dlq for c in self.consumers)


def create_backpressure_test_consumers(
    metrics: MetricsCollector | None = None,
) -> ConsumerGroup:
    """
    Create a consumer group for backpressure testing.

    Includes:
    - 1 normal consumer (fast)
    - 1 slow consumer (introduces backpressure)
    """
    group = ConsumerGroup(name="backpressure_test")

    group.add(
        NormalConsumer(
            name="fast_consumer",
            topics=["orders_fact"],
            metrics=metrics,
        )
    )

    group.add(
        SlowConsumer(
            name="slow_consumer",
            topics=["orders_fact"],
            delay_ms=200,
            delay_variance_ms=50,
            metrics=metrics,
        )
    )

    return group


def create_dlq_test_consumers(
    metrics: MetricsCollector | None = None,
) -> ConsumerGroup:
    """
    Create a consumer group for DLQ testing.

    Includes:
    - 1 normal consumer
    - 1 failing consumer (transient + permanent failures)
    """
    group = ConsumerGroup(name="dlq_test")

    group.add(
        NormalConsumer(
            name="normal_consumer",
            topics=["orders_intent"],
            metrics=metrics,
        )
    )

    group.add(
        FailingConsumer(
            name="failing_consumer",
            topics=["orders_intent"],
            failure_probability=0.1,
            permanent_failure_probability=0.02,
            metrics=metrics,
        )
    )

    return group


def create_projection_test_consumers(
    metrics: MetricsCollector | None = None,
) -> ConsumerGroup:
    """
    Create a consumer group for projection testing.

    Includes projections for orders and accounts.
    """
    group = ConsumerGroup(name="projection_test")

    group.add(
        ProjectionConsumer(
            name="order_projection",
            topics=["orders_fact"],
            entity_key_field="order_id",
            processing_time_ms=5,
            metrics=metrics,
        )
    )

    group.add(
        ProjectionConsumer(
            name="account_projection",
            topics=["ledger_fact"],
            entity_key_field="account_id",
            processing_time_ms=5,
            metrics=metrics,
        )
    )

    return group


def create_full_test_consumers(
    metrics: MetricsCollector | None = None,
) -> ConsumerGroup:
    """
    Create a comprehensive consumer group for full testing.

    Includes all consumer types.
    """
    group = ConsumerGroup(name="full_test")

    # Fast consumer
    group.add(
        NormalConsumer(
            name="fast_intent_consumer",
            topics=["orders_intent", "payments_intent"],
            metrics=metrics,
        )
    )

    # Slow consumer for backpressure
    group.add(
        SlowConsumer(
            name="slow_fact_consumer",
            topics=["orders_fact", "payments_fact"],
            delay_ms=50,
            metrics=metrics,
        )
    )

    # Failing consumer for DLQ
    group.add(
        FailingConsumer(
            name="failing_observation_consumer",
            topics=["gateway_observation", "http_observation"],
            failure_probability=0.05,
            permanent_failure_probability=0.01,
            metrics=metrics,
        )
    )

    # Projections
    group.add(
        ProjectionConsumer(
            name="order_projection",
            topics=["orders_fact"],
            entity_key_field="order_id",
            metrics=metrics,
        )
    )

    # Derivation
    group.add(
        DerivationConsumer(
            name="balance_derivation",
            topics=["ledger_fact"],
            processing_time_ms=10,
            metrics=metrics,
        )
    )

    return group
