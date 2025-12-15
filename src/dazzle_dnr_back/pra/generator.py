"""
Load generator for PRA stress testing.

Orchestrates load generation according to load profiles,
using data factories to create synthetic payloads.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from dazzle_dnr_back.events.envelope import EventEnvelope
from dazzle_dnr_back.metrics import MetricsCollector

from .data_factory import PRADataFactory
from .hot_keys import create_pareto_selector
from .profiles import LoadProfile, LoadState, SteadyRampProfile

logger = logging.getLogger(__name__)


# Type for event emission callback
EventEmitter = Callable[[str, EventEnvelope], Any]


@dataclass
class GeneratorConfig:
    """Configuration for the load generator."""

    # Data generation
    seed: int | None = None
    rejection_rate: float = 0.15
    payment_failure_rate: float = 0.10
    payment_timeout_rate: float = 0.02

    # Hot key configuration
    actor_count: int = 100
    account_count: int = 200
    hot_key_ratio: float = 0.1  # 10% are hot
    hot_traffic_share: float = 0.8  # 80% of traffic

    # Schema evolution
    v2_schema_probability: float = 0.3  # 30% use v2 schemas

    # Rate limiting
    batch_size: int = 100
    batch_interval_ms: float = 100.0

    # Duplicate submission for idempotency testing
    duplicate_probability: float = 0.05  # 5% duplicates


@dataclass
class GeneratorStats:
    """Runtime statistics for the generator."""

    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    intents_generated: int = 0
    facts_generated: int = 0
    observations_generated: int = 0
    derivations_generated: int = 0
    duplicates_generated: int = 0
    errors: int = 0

    @property
    def total_generated(self) -> int:
        return (
            self.intents_generated
            + self.facts_generated
            + self.observations_generated
            + self.derivations_generated
        )


class LoadGenerator:
    """
    Generates load according to a profile.

    Example:
        generator = LoadGenerator(
            profile=SteadyRampProfile(peak_rate=1000),
            emit_callback=my_emitter,
        )

        await generator.start()
        # ... runs until profile completes or stopped
        await generator.stop()
    """

    def __init__(
        self,
        profile: LoadProfile | None = None,
        emit_callback: EventEmitter | None = None,
        config: GeneratorConfig | None = None,
        metrics: MetricsCollector | None = None,
    ) -> None:
        """
        Initialize the load generator.

        Args:
            profile: Load profile to execute
            emit_callback: Callback to emit events (topic, envelope)
            config: Generator configuration
            metrics: Metrics collector for tracking
        """
        self.profile = profile or SteadyRampProfile()
        self.emit_callback = emit_callback
        self.config = config or GeneratorConfig()
        self.metrics = metrics

        # Initialize data factory
        self.factory = PRADataFactory(
            seed=self.config.seed,
            rejection_rate=self.config.rejection_rate,
            payment_failure_rate=self.config.payment_failure_rate,
            payment_timeout_rate=self.config.payment_timeout_rate,
        )

        # Initialize key selectors
        self.actor_selector = create_pareto_selector(
            total_keys=self.config.actor_count,
            pareto_ratio=self.config.hot_key_ratio,
            traffic_share=self.config.hot_traffic_share,
            seed=self.config.seed,
        )
        self.account_selector = create_pareto_selector(
            total_keys=self.config.account_count,
            pareto_ratio=self.config.hot_key_ratio,
            traffic_share=self.config.hot_traffic_share,
            seed=self.config.seed + 1 if self.config.seed else None,
        )

        # Runtime state
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._start_time: float = 0.0
        self._stats = GeneratorStats()

        # Track recent events for duplicate generation
        self._recent_intents: list[dict[str, Any]] = []
        self._max_recent = 100

    @property
    def stats(self) -> GeneratorStats:
        """Get current generator statistics."""
        return self._stats

    @property
    def is_running(self) -> bool:
        """Check if generator is running."""
        return self._running

    async def start(self) -> None:
        """Start the load generator."""
        if self._running:
            return

        logger.info(f"Starting load generator with profile: {self.profile.name}")
        self._running = True
        self._start_time = time.monotonic()
        self._stats = GeneratorStats()

        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> GeneratorStats:
        """
        Stop the load generator.

        Returns:
            Final statistics
        """
        if not self._running:
            return self._stats

        logger.info("Stopping load generator")
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        return self._stats

    async def _run_loop(self) -> None:
        """Main generation loop."""
        batch_interval = self.config.batch_interval_ms / 1000.0

        while self._running:
            elapsed = time.monotonic() - self._start_time
            state = self.profile.get_state(elapsed)

            # Check if profile complete
            if self.profile.is_complete(elapsed):
                logger.info("Load profile complete")
                self._running = False
                break

            # Calculate batch size based on target rate
            events_per_batch = int(state.target_rate * batch_interval)
            events_per_batch = max(1, min(events_per_batch, self.config.batch_size))

            # Generate batch
            batch_start = time.monotonic()
            await self._generate_batch(events_per_batch, state)
            batch_duration = time.monotonic() - batch_start

            # Sleep for remainder of interval
            sleep_time = max(0, batch_interval - batch_duration)
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)

    async def _generate_batch(self, count: int, state: LoadState) -> None:
        """Generate a batch of events."""
        for _ in range(count):
            try:
                await self._generate_event(state)
            except Exception as e:
                logger.error(f"Error generating event: {e}")
                self._stats.errors += 1

    async def _generate_event(self, state: LoadState) -> None:
        """Generate a single event based on current state."""
        import random

        # Check for skewed burst mode
        use_hot_keys = False
        if state.metadata.get("skewed_burst"):
            hot_prob = state.metadata.get("hot_key_probability", 0.8)
            use_hot_keys = random.random() < hot_prob

        # Decide event type (weighted toward order flow)
        r = random.random()
        if r < 0.4:
            await self._generate_order_intent(use_hot_keys, state)
        elif r < 0.6:
            await self._generate_payment_intent(state)
        elif r < 0.75:
            await self._generate_observation(state)
        else:
            await self._generate_order_fact(use_hot_keys, state)

    async def _generate_order_intent(self, use_hot_keys: bool, state: LoadState) -> None:
        """Generate an order placement intent."""
        import random

        # Select actor with optional hot key bias
        if use_hot_keys:
            actor_id = self.actor_selector.select_hot()
            account_id = self.account_selector.select_hot()
        else:
            actor_id = self.actor_selector.select()
            account_id = self.account_selector.select()

        # Decide schema version
        use_v2 = random.random() < self.config.v2_schema_probability

        # Check for duplicate generation
        is_duplicate = False
        if self._recent_intents and random.random() < self.config.duplicate_probability:
            # Reuse a recent intent (idempotency test)
            payload = random.choice(self._recent_intents).copy()
            is_duplicate = True
            self._stats.duplicates_generated += 1
        else:
            payload = self.factory.order_placement_requested(
                actor_id=actor_id,
                account_id=account_id,
                use_v2=use_v2,
            )
            # Store for potential duplicate
            self._recent_intents.append(payload)
            if len(self._recent_intents) > self._max_recent:
                self._recent_intents.pop(0)

        # Create envelope
        schema_name = "OrderPlacementRequestedV2" if use_v2 else "OrderPlacementRequested"
        envelope = EventEnvelope.create(
            event_type=f"pra.orders_intent.{schema_name}",
            key=str(actor_id),
            payload=self._serialize_payload(payload),
        )

        await self._emit("orders_intent", envelope)
        self._stats.intents_generated += 1

        if self.metrics:
            self.metrics.record_throughput("intents")
            if is_duplicate:
                self.metrics.record_throughput("duplicates")

    async def _generate_payment_intent(self, state: LoadState) -> None:
        """Generate a payment intent."""
        payload = self.factory.payment_requested()

        envelope = EventEnvelope.create(
            event_type="pra.payments_intent.PaymentRequested",
            key=str(payload["order_id"]),
            payload=self._serialize_payload(payload),
        )

        await self._emit("payments_intent", envelope)
        self._stats.intents_generated += 1

        if self.metrics:
            self.metrics.record_throughput("intents")

    async def _generate_order_fact(self, use_hot_keys: bool, state: LoadState) -> None:
        """Generate an order fact (placed or rejected)."""
        if use_hot_keys:
            actor_id = self.actor_selector.select_hot()
            account_id = self.account_selector.select_hot()
        else:
            actor_id = self.actor_selector.select()
            account_id = self.account_selector.select()

        # Decide outcome
        if self.factory.should_reject_order():
            payload = self.factory.order_placement_rejected(
                actor_id=actor_id,
                account_id=account_id,
            )
            schema_name = "OrderPlacementRejected"
            if self.metrics:
                self.metrics.record_error("rejection")
        else:
            payload = self.factory.order_placed(
                actor_id=actor_id,
                account_id=account_id,
            )
            schema_name = "OrderPlaced"

        envelope = EventEnvelope.create(
            event_type=f"pra.orders_fact.{schema_name}",
            key=str(payload["order_id"]),
            payload=self._serialize_payload(payload),
        )

        await self._emit("orders_fact", envelope)
        self._stats.facts_generated += 1

        if self.metrics:
            self.metrics.record_throughput("facts")

    async def _generate_observation(self, state: LoadState) -> None:
        """Generate an observation event."""
        import random

        if random.random() < 0.5:
            # Gateway webhook
            use_v2 = random.random() < self.config.v2_schema_probability
            payload = self.factory.gateway_webhook_received(use_v2=use_v2)
            schema_name = "GatewayWebhookReceivedV2" if use_v2 else "GatewayWebhookReceived"

            envelope = EventEnvelope.create(
                event_type=f"pra.gateway_observation.{schema_name}",
                key=payload["gateway_ref"],
                payload=self._serialize_payload(payload),
            )
            await self._emit("gateway_observation", envelope)
        else:
            # HTTP request
            payload = self.factory.http_request_observed()

            envelope = EventEnvelope.create(
                event_type="pra.http_observation.HttpRequestObserved",
                key=str(payload["trace_id"]),
                payload=self._serialize_payload(payload),
            )
            await self._emit("http_observation", envelope)

        self._stats.observations_generated += 1

        if self.metrics:
            self.metrics.record_throughput("observations")

    async def _emit(self, topic: str, envelope: EventEnvelope) -> None:
        """Emit an event through the callback."""
        if self.emit_callback:
            result = self.emit_callback(topic, envelope)
            if asyncio.iscoroutine(result):
                await result

    def _serialize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Serialize payload for event envelope."""
        result = {}
        for key, value in payload.items():
            if isinstance(value, UUID):
                result[key] = str(value)
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            elif hasattr(value, "isoformat"):
                result[key] = value.isoformat()
            else:
                result[key] = value
        return result

    def get_current_state(self) -> LoadState | None:
        """Get current load profile state."""
        if not self._running:
            return None
        elapsed = time.monotonic() - self._start_time
        return self.profile.get_state(elapsed)


async def run_load_test(
    profile: LoadProfile,
    emit_callback: EventEmitter,
    config: GeneratorConfig | None = None,
    metrics: MetricsCollector | None = None,
) -> GeneratorStats:
    """
    Run a complete load test with the given profile.

    Args:
        profile: Load profile to execute
        emit_callback: Callback to emit events
        config: Optional generator configuration
        metrics: Optional metrics collector

    Returns:
        Final generator statistics
    """
    generator = LoadGenerator(
        profile=profile,
        emit_callback=emit_callback,
        config=config,
        metrics=metrics,
    )

    await generator.start()

    # Wait for profile to complete
    while generator.is_running:
        await asyncio.sleep(1.0)

    return generator.stats
