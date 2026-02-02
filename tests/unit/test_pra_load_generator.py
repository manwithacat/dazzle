"""Tests for PRA load generator components."""

from __future__ import annotations

import asyncio
from collections import defaultdict

# Note: PRA data factory uses Money pattern (amount_minor: int + currency: str)
from uuid import UUID

import pytest

from dazzle_back.events.envelope import EventEnvelope
from dazzle_back.pra.data_factory import PRADataFactory
from dazzle_back.pra.generator import GeneratorConfig, GeneratorStats, LoadGenerator
from dazzle_back.pra.hot_keys import (
    HotKeySelector,
    WeightedKeySelector,
    create_extreme_skew_selector,
    create_pareto_selector,
)
from dazzle_back.pra.profiles import (
    BurstProfile,
    FailureInjectionProfile,
    LoadPhase,
    ReplayProfile,
    SkewedBurstProfile,
    SteadyRampProfile,
    create_quick_test_profile,
)


class TestHotKeySelector:
    """Tests for HotKeySelector."""

    def test_initialization(self) -> None:
        """Test selector initializes key pools."""
        selector = HotKeySelector(
            hot_key_count=10,
            total_keys=100,
            seed=42,
        )

        hot_keys = selector.get_hot_keys()
        cold_keys = selector.get_cold_keys()

        assert len(hot_keys) == 10
        assert len(cold_keys) == 90
        assert all(isinstance(k, UUID) for k in hot_keys)

    def test_hot_key_selection_bias(self) -> None:
        """Test that hot keys are selected more frequently."""
        selector = HotKeySelector(
            hot_key_count=10,
            hot_key_probability=0.8,
            total_keys=100,
            seed=42,
        )

        hot_keys = set(selector.get_hot_keys())
        hot_count = 0
        iterations = 1000

        for _ in range(iterations):
            key = selector.select()
            if key in hot_keys:
                hot_count += 1

        # With 80% hot probability, expect ~800 hot selections
        # Allow some variance
        assert 700 < hot_count < 900

    def test_select_hot_always_hot(self) -> None:
        """Test select_hot always returns hot key."""
        selector = HotKeySelector(
            hot_key_count=5,
            total_keys=50,
            seed=42,
        )

        hot_keys = set(selector.get_hot_keys())

        for _ in range(100):
            key = selector.select_hot()
            assert key in hot_keys

    def test_select_cold_always_cold(self) -> None:
        """Test select_cold always returns cold key."""
        selector = HotKeySelector(
            hot_key_count=5,
            total_keys=50,
            seed=42,
        )

        cold_keys = set(selector.get_cold_keys())

        for _ in range(100):
            key = selector.select_cold()
            assert key in cold_keys

    def test_is_hot(self) -> None:
        """Test is_hot correctly identifies hot keys."""
        selector = HotKeySelector(
            hot_key_count=10,
            total_keys=100,
            seed=42,
        )

        for key in selector.get_hot_keys():
            assert selector.is_hot(key)

        for key in selector.get_cold_keys():
            assert not selector.is_hot(key)

    def test_reset_regenerates_keys(self) -> None:
        """Test reset generates new key pools."""
        selector = HotKeySelector(
            hot_key_count=10,
            total_keys=100,
            seed=42,
        )

        original_hot = set(selector.get_hot_keys())

        selector.reset(seed=99)

        new_hot = set(selector.get_hot_keys())

        # Different seeds should produce different keys
        assert original_hot != new_hot


class TestWeightedKeySelector:
    """Tests for WeightedKeySelector."""

    def test_weighted_selection(self) -> None:
        """Test keys selected according to weight."""
        selector = WeightedKeySelector(seed=42)

        # Add keys with very different weights
        from uuid import uuid4

        heavy = uuid4()
        light = uuid4()

        selector.add_key(heavy, weight=100)
        selector.add_key(light, weight=1)

        heavy_count = 0
        for _ in range(1000):
            if selector.select() == heavy:
                heavy_count += 1

        # Heavy key should be selected ~99% of the time
        assert heavy_count > 950

    def test_empty_selector_returns_uuid(self) -> None:
        """Test empty selector returns new UUID."""
        selector = WeightedKeySelector()
        key = selector.select()
        assert isinstance(key, UUID)

    def test_clear(self) -> None:
        """Test clear removes all keys."""
        selector = WeightedKeySelector()
        from uuid import uuid4

        selector.add_key(uuid4(), weight=10)
        selector.add_key(uuid4(), weight=10)

        assert selector._total_weight == 20

        selector.clear()

        assert selector._total_weight == 0
        assert len(selector._keys) == 0


class TestCreateParetoSelector:
    """Tests for pareto selector factory."""

    def test_pareto_defaults(self) -> None:
        """Test default 80/20 distribution."""
        selector = create_pareto_selector(total_keys=100)

        # 20% of 100 = 20 hot keys
        assert len(selector.get_hot_keys()) == 20
        assert len(selector.get_cold_keys()) == 80
        assert selector.hot_key_probability == 0.8

    def test_custom_pareto(self) -> None:
        """Test custom pareto ratio."""
        selector = create_pareto_selector(
            total_keys=100,
            pareto_ratio=0.1,
            traffic_share=0.9,
        )

        # 10% of 100 = 10 hot keys
        assert len(selector.get_hot_keys()) == 10
        assert selector.hot_key_probability == 0.9


class TestCreateExtremeSkewSelector:
    """Tests for extreme skew selector factory."""

    def test_extreme_skew(self) -> None:
        """Test 1%/90% distribution."""
        selector = create_extreme_skew_selector(total_keys=100)

        # 1% of 100 = 1 hot key
        assert len(selector.get_hot_keys()) == 1
        assert selector.hot_key_probability == 0.9


class TestPRADataFactory:
    """Tests for PRA data factory."""

    def test_order_placement_requested(self) -> None:
        """Test order placement intent generation."""
        factory = PRADataFactory(seed=42)
        payload = factory.order_placement_requested()

        assert "request_id" in payload
        assert "actor_id" in payload
        assert "account_id" in payload
        assert "amount_minor" in payload  # Money pattern: amount in minor units
        assert "currency" in payload
        assert "occurred_at" in payload

        assert isinstance(payload["request_id"], UUID)
        assert isinstance(payload["amount_minor"], int)  # Money uses int for precision
        assert payload["currency"] in ["GBP", "USD", "EUR"]

    def test_order_placement_requested_v2(self) -> None:
        """Test v2 schema includes idempotency key."""
        factory = PRADataFactory(seed=42)
        payload = factory.order_placement_requested(use_v2=True)

        assert "idempotency_key" in payload
        assert isinstance(payload["idempotency_key"], str)
        assert len(payload["idempotency_key"]) == 32

    def test_payment_requested(self) -> None:
        """Test payment intent generation."""
        factory = PRADataFactory(seed=42)
        payload = factory.payment_requested()

        assert "request_id" in payload
        assert "order_id" in payload
        assert "amount_minor" in payload  # Money pattern
        assert "currency" in payload
        assert "gateway" in payload

        assert payload["gateway"] in ["stripe", "adyen", "worldpay", "paypal"]

    def test_order_placed(self) -> None:
        """Test order placed fact generation."""
        factory = PRADataFactory(seed=42)
        payload = factory.order_placed()

        assert "order_id" in payload
        assert "actor_id" in payload
        assert "account_id" in payload
        assert "causation_id" in payload

    def test_payment_succeeded(self) -> None:
        """Test payment succeeded fact."""
        factory = PRADataFactory(seed=42)
        payload = factory.payment_succeeded()

        assert "payment_id" in payload
        assert "gateway_ref" in payload
        assert payload["gateway_ref"].startswith(("pi_", "ch_", "txn_", "pay_"))

    def test_payment_failed(self) -> None:
        """Test payment failed fact."""
        factory = PRADataFactory(seed=42)
        payload = factory.payment_failed()

        assert "reason" in payload
        assert "gateway_error_code" in payload

    def test_gateway_webhook_received(self) -> None:
        """Test gateway webhook observation."""
        factory = PRADataFactory(seed=42)
        payload = factory.gateway_webhook_received()

        assert "observation_id" in payload
        assert "gateway_ref" in payload
        assert "webhook_type" in payload

    def test_gateway_webhook_received_v2(self) -> None:
        """Test v2 webhook includes signature_valid."""
        factory = PRADataFactory(seed=42)
        payload = factory.gateway_webhook_received(use_v2=True)

        assert "signature_valid" in payload
        assert "idempotency_key" in payload

    def test_http_request_observed(self) -> None:
        """Test HTTP request observation."""
        factory = PRADataFactory(seed=42)
        payload = factory.http_request_observed()

        assert "trace_id" in payload
        assert "span_id" in payload
        assert "http_method" in payload
        assert "request_path" in payload
        assert "response_status" in payload
        assert "duration_ms" in payload

    def test_account_balance_calculated(self) -> None:
        """Test balance derivation."""
        factory = PRADataFactory(seed=42)
        payload = factory.account_balance_calculated()

        assert "calculation_id" in payload
        assert "account_id" in payload
        assert "balance_minor" in payload  # Money pattern
        assert "currency" in payload
        assert "as_of_sequence" in payload

    def test_daily_revenue_aggregated(self) -> None:
        """Test revenue derivation."""
        factory = PRADataFactory(seed=42)
        payload = factory.daily_revenue_aggregated()

        assert "calculation_id" in payload
        assert "revenue_date" in payload
        assert "total_revenue_minor" in payload  # Money pattern
        assert "currency" in payload
        assert "order_count" in payload

    def test_daily_revenue_v2(self) -> None:
        """Test v2 revenue includes average_order_value_minor."""
        factory = PRADataFactory(seed=42)
        payload = factory.daily_revenue_aggregated(use_v2=True)

        assert "average_order_value_minor" in payload  # Money pattern

    def test_should_reject_order_rate(self) -> None:
        """Test rejection rate follows configuration."""
        factory = PRADataFactory(seed=42, rejection_rate=0.5)

        rejections = sum(1 for _ in range(1000) if factory.should_reject_order())

        # With 50% rate, expect ~500 rejections
        assert 400 < rejections < 600

    def test_payment_outcome_distribution(self) -> None:
        """Test payment outcomes follow configured rates."""
        factory = PRADataFactory(
            seed=42,
            payment_failure_rate=0.10,
            payment_timeout_rate=0.02,
        )

        outcomes = defaultdict(int)
        for _ in range(1000):
            outcomes[factory.get_payment_outcome()] += 1

        # ~88% success, ~10% failure, ~2% timeout
        assert outcomes["success"] > 800
        assert 50 < outcomes["failure"] < 150
        assert outcomes["timeout"] < 50

    def test_deterministic_with_seed(self) -> None:
        """Test same seed produces same data."""
        factory1 = PRADataFactory(seed=42)
        factory2 = PRADataFactory(seed=42)

        # Same seed should produce same currency
        for _ in range(10):
            p1 = factory1.order_placement_requested()
            p2 = factory2.order_placement_requested()
            assert p1["currency"] == p2["currency"]


class TestLoadProfiles:
    """Tests for load profiles."""

    def test_steady_ramp_phases(self) -> None:
        """Test SteadyRampProfile phase transitions."""
        profile = SteadyRampProfile(
            warmup_rate=10,
            peak_rate=100,
            warmup_seconds=10,
            ramp_seconds=10,
            peak_seconds=10,
            cooldown_seconds=10,
        )

        # Warmup
        state = profile.get_state(5)
        assert state.phase == LoadPhase.WARMUP
        assert state.target_rate == 10

        # Ramp (linear interpolation)
        state = profile.get_state(15)
        assert state.phase == LoadPhase.RAMP
        assert 50 < state.target_rate < 60  # ~55 (halfway)

        # Peak
        state = profile.get_state(25)
        assert state.phase == LoadPhase.PEAK
        assert state.target_rate == 100

        # Cooldown
        state = profile.get_state(35)
        assert state.phase == LoadPhase.COOLDOWN

        # Complete
        state = profile.get_state(45)
        assert state.phase == LoadPhase.COMPLETE
        assert state.target_rate == 0

    def test_burst_profile(self) -> None:
        """Test BurstProfile burst phase."""
        profile = BurstProfile(
            baseline_rate=100,
            burst_multiplier=10,
            baseline_seconds=10,
            burst_seconds=10,
            recovery_seconds=10,
        )

        # Baseline
        state = profile.get_state(5)
        assert state.phase == LoadPhase.WARMUP
        assert state.target_rate == 100

        # Burst
        state = profile.get_state(15)
        assert state.phase == LoadPhase.PEAK
        assert state.target_rate == 1000
        assert state.metadata.get("burst_active")

        # Recovery
        state = profile.get_state(25)
        assert state.phase == LoadPhase.COOLDOWN
        assert state.target_rate == 100

    def test_skewed_burst_metadata(self) -> None:
        """Test SkewedBurstProfile includes hot key probability."""
        profile = SkewedBurstProfile(
            baseline_rate=100,
            burst_multiplier=10,
            hot_key_probability=0.95,
            baseline_seconds=10,
            burst_seconds=10,
            recovery_seconds=10,
        )

        # During burst
        state = profile.get_state(15)
        assert state.metadata.get("skewed_burst")
        assert state.metadata.get("hot_key_probability") == 0.95

    def test_failure_injection_metadata(self) -> None:
        """Test FailureInjectionProfile includes failure info."""
        profile = FailureInjectionProfile(
            rate=500,
            failure_probability=0.20,
            failure_targets=["database", "gateway"],
            duration_seconds=60,
        )

        state = profile.get_state(30)
        assert state.metadata.get("failure_injection")
        assert state.metadata.get("failure_probability") == 0.20
        assert "database" in state.metadata.get("failure_targets", [])

    def test_replay_profile(self) -> None:
        """Test ReplayProfile configuration."""
        profile = ReplayProfile(
            source_stream="orders_fact",
            max_rate=10000,
            estimated_records=100000,
        )

        state = profile.get_state(5)
        assert state.metadata.get("replay_mode")
        assert state.metadata.get("source_stream") == "orders_fact"
        assert state.target_rate == 10000

    def test_quick_test_profile(self) -> None:
        """Test quick test profile factory."""
        profile = create_quick_test_profile()

        assert profile.peak_rate == 100
        assert profile.total_duration_seconds == 60

    def test_is_complete(self) -> None:
        """Test profile completion detection."""
        profile = SteadyRampProfile(
            warmup_seconds=10,
            ramp_seconds=10,
            peak_seconds=10,
            cooldown_seconds=10,
        )

        assert not profile.is_complete(20)
        assert not profile.is_complete(39)
        assert profile.is_complete(40)
        assert profile.is_complete(100)

    def test_progress_percentage(self) -> None:
        """Test progress percentage calculation."""
        profile = SteadyRampProfile(
            warmup_seconds=25,
            ramp_seconds=25,
            peak_seconds=25,
            cooldown_seconds=25,
        )

        state = profile.get_state(0)
        assert state.progress_pct == 0

        state = profile.get_state(50)
        assert state.progress_pct == 50

        state = profile.get_state(100)
        assert state.progress_pct == 100


class TestLoadGenerator:
    """Tests for LoadGenerator."""

    @pytest.mark.asyncio
    async def test_generator_emits_events(self) -> None:
        """Test generator emits events through callback."""
        emitted: list[tuple[str, EventEnvelope]] = []

        def callback(topic: str, envelope: EventEnvelope) -> None:
            emitted.append((topic, envelope))

        profile = create_quick_test_profile()
        profile.warmup_seconds = 0.1
        profile.ramp_seconds = 0.1
        profile.peak_seconds = 0.1
        profile.cooldown_seconds = 0.1

        generator = LoadGenerator(
            profile=profile,
            emit_callback=callback,
            config=GeneratorConfig(
                batch_size=10,
                batch_interval_ms=50,
                seed=42,
            ),
        )

        await generator.start()
        await asyncio.sleep(0.5)
        stats = await generator.stop()

        assert len(emitted) > 0
        assert stats.total_generated > 0

    @pytest.mark.asyncio
    async def test_generator_stats(self) -> None:
        """Test generator tracks statistics."""
        events: list[tuple[str, EventEnvelope]] = []

        def callback(topic: str, envelope: EventEnvelope) -> None:
            events.append((topic, envelope))

        profile = SteadyRampProfile(
            warmup_seconds=0.05,
            ramp_seconds=0.05,
            peak_seconds=0.05,
            cooldown_seconds=0.05,
            peak_rate=100,
        )

        generator = LoadGenerator(
            profile=profile,
            emit_callback=callback,
            config=GeneratorConfig(batch_interval_ms=10, seed=42),
        )

        await generator.start()
        await asyncio.sleep(0.3)
        stats = await generator.stop()

        # Check stats categories populated
        total = (
            stats.intents_generated
            + stats.facts_generated
            + stats.observations_generated
            + stats.derivations_generated
        )
        assert total == stats.total_generated

    @pytest.mark.asyncio
    async def test_generator_duplicate_generation(self) -> None:
        """Test generator produces duplicates for idempotency testing."""
        events: list[tuple[str, EventEnvelope]] = []

        def callback(topic: str, envelope: EventEnvelope) -> None:
            events.append((topic, envelope))

        profile = SteadyRampProfile(
            warmup_seconds=0.1,
            ramp_seconds=0.1,
            peak_seconds=0.2,
            cooldown_seconds=0.1,
            peak_rate=200,
        )

        generator = LoadGenerator(
            profile=profile,
            emit_callback=callback,
            config=GeneratorConfig(
                duplicate_probability=0.5,  # High for testing
                batch_interval_ms=10,
                seed=42,
            ),
        )

        await generator.start()
        await asyncio.sleep(0.6)
        stats = await generator.stop()

        # Should have generated some duplicates
        assert stats.duplicates_generated > 0

    @pytest.mark.asyncio
    async def test_generator_not_running_after_stop(self) -> None:
        """Test generator stops cleanly."""
        generator = LoadGenerator(
            profile=create_quick_test_profile(),
            config=GeneratorConfig(seed=42),
        )

        assert not generator.is_running

        await generator.start()
        assert generator.is_running

        await generator.stop()
        assert not generator.is_running

    @pytest.mark.asyncio
    async def test_generator_get_current_state(self) -> None:
        """Test getting current load state."""
        profile = SteadyRampProfile(
            warmup_seconds=1,
            ramp_seconds=1,
            peak_seconds=1,
            cooldown_seconds=1,
        )

        generator = LoadGenerator(
            profile=profile,
            config=GeneratorConfig(seed=42),
        )

        # Not running - no state
        assert generator.get_current_state() is None

        await generator.start()
        await asyncio.sleep(0.1)

        state = generator.get_current_state()
        assert state is not None
        assert state.phase == LoadPhase.WARMUP

        await generator.stop()

    @pytest.mark.asyncio
    async def test_async_emit_callback(self) -> None:
        """Test generator handles async callbacks."""
        events: list[str] = []

        async def async_callback(topic: str, envelope: EventEnvelope) -> None:
            await asyncio.sleep(0.001)
            events.append(topic)

        profile = SteadyRampProfile(
            warmup_seconds=0.05,
            ramp_seconds=0.05,
            peak_seconds=0.1,
            cooldown_seconds=0.05,
        )

        generator = LoadGenerator(
            profile=profile,
            emit_callback=async_callback,
            config=GeneratorConfig(batch_interval_ms=20, seed=42),
        )

        await generator.start()
        await asyncio.sleep(0.3)
        await generator.stop()

        assert len(events) > 0


class TestGeneratorConfig:
    """Tests for GeneratorConfig."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = GeneratorConfig()

        assert config.rejection_rate == 0.15
        assert config.payment_failure_rate == 0.10
        assert config.payment_timeout_rate == 0.02
        assert config.actor_count == 100
        assert config.account_count == 200
        assert config.hot_key_ratio == 0.1
        assert config.hot_traffic_share == 0.8
        assert config.v2_schema_probability == 0.3
        assert config.duplicate_probability == 0.05

    def test_custom_config(self) -> None:
        """Test custom configuration."""
        config = GeneratorConfig(
            seed=42,
            rejection_rate=0.5,
            actor_count=50,
            duplicate_probability=0.1,
        )

        assert config.seed == 42
        assert config.rejection_rate == 0.5
        assert config.actor_count == 50
        assert config.duplicate_probability == 0.1


class TestGeneratorStats:
    """Tests for GeneratorStats."""

    def test_total_generated(self) -> None:
        """Test total calculation."""
        stats = GeneratorStats(
            intents_generated=100,
            facts_generated=50,
            observations_generated=25,
            derivations_generated=10,
        )

        assert stats.total_generated == 185

    def test_initial_stats(self) -> None:
        """Test initial stats are zero."""
        stats = GeneratorStats()

        assert stats.total_generated == 0
        assert stats.errors == 0
        assert stats.duplicates_generated == 0
