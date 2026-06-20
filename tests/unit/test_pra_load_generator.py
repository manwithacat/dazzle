"""Tests for PRA load generator components."""

import asyncio
from collections import defaultdict

# Note: PRA data factory uses Money pattern (amount_minor: int + currency: str)
from uuid import UUID

import pytest

from dazzle.http.events.envelope import EventEnvelope
from dazzle.http.pra.data_factory import PRADataFactory
from dazzle.http.pra.generator import GeneratorConfig, GeneratorStats, LoadGenerator
from dazzle.http.pra.hot_keys import (
    HotKeySelector,
    WeightedKeySelector,
    create_extreme_skew_selector,
    create_pareto_selector,
)
from dazzle.http.pra.profiles import (
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

    def test_hot_key_selector_combined(self) -> None:
        """Combined: initialization (key pools), hot-key selection bias,
        select_hot/select_cold contracts, is_hot, reset regenerates."""
        # Initialization
        selector = HotKeySelector(hot_key_count=10, total_keys=100, seed=42)
        hot_keys = selector.get_hot_keys()
        cold_keys = selector.get_cold_keys()
        assert len(hot_keys) == 10
        assert len(cold_keys) == 90
        assert all(isinstance(k, UUID) for k in hot_keys)

        # Hot key selection bias (80% probability)
        bias_sel = HotKeySelector(
            hot_key_count=10, hot_key_probability=0.8, total_keys=100, seed=42
        )
        hot_set = set(bias_sel.get_hot_keys())
        hot_count = sum(1 for _ in range(1000) if bias_sel.select() in hot_set)
        assert 700 < hot_count < 900

        # select_hot always returns hot
        small = HotKeySelector(hot_key_count=5, total_keys=50, seed=42)
        small_hot = set(small.get_hot_keys())
        small_cold = set(small.get_cold_keys())
        for _ in range(100):
            assert small.select_hot() in small_hot
            assert small.select_cold() in small_cold

        # is_hot
        for k in selector.get_hot_keys():
            assert selector.is_hot(k)
        for k in selector.get_cold_keys():
            assert not selector.is_hot(k)

        # Reset regenerates
        original_hot = set(selector.get_hot_keys())
        selector.reset(seed=99)
        assert original_hot != set(selector.get_hot_keys())


class TestWeightedKeySelector:
    """Tests for WeightedKeySelector."""

    def test_weighted_selector_combined(self) -> None:
        """Combined: weighted selection (heavy bias), empty -> new UUID,
        clear resets state."""
        from uuid import uuid4

        # Weighted selection
        selector = WeightedKeySelector(seed=42)
        heavy = uuid4()
        light = uuid4()
        selector.add_key(heavy, weight=100)
        selector.add_key(light, weight=1)
        heavy_count = sum(1 for _ in range(1000) if selector.select() == heavy)
        assert heavy_count > 950

        # Empty -> new UUID
        empty = WeightedKeySelector()
        assert isinstance(empty.select(), UUID)

        # Clear
        clr = WeightedKeySelector()
        clr.add_key(uuid4(), weight=10)
        clr.add_key(uuid4(), weight=10)
        assert clr._total_weight == 20
        clr.clear()
        assert clr._total_weight == 0
        assert len(clr._keys) == 0


class TestCreateParetoSelector:
    """Tests for pareto selector factory."""

    def test_pareto_combined(self) -> None:
        """Combined: default 80/20 + custom ratio."""
        # Defaults
        sel = create_pareto_selector(total_keys=100)
        assert len(sel.get_hot_keys()) == 20
        assert len(sel.get_cold_keys()) == 80
        assert sel.hot_key_probability == 0.8

        # Custom
        custom = create_pareto_selector(total_keys=100, pareto_ratio=0.1, traffic_share=0.9)
        assert len(custom.get_hot_keys()) == 10
        assert custom.hot_key_probability == 0.9


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

    def test_payload_shapes_combined(self) -> None:
        """Combined payload shape tests for: order_placement_requested
        (v1+v2), payment_requested, order_placed, payment_succeeded,
        payment_failed, gateway_webhook_received (v1+v2), http_request_observed,
        account_balance_calculated, daily_revenue_aggregated (v1+v2)."""
        factory = PRADataFactory(seed=42)

        # order_placement_requested
        op = factory.order_placement_requested()
        for k in (
            "request_id",
            "actor_id",
            "account_id",
            "amount_minor",
            "currency",
            "occurred_at",
        ):
            assert k in op
        assert isinstance(op["request_id"], UUID)
        assert isinstance(op["amount_minor"], int)
        assert op["currency"] in ["GBP", "USD", "EUR"]

        # order_placement_requested v2
        op_v2 = factory.order_placement_requested(use_v2=True)
        assert "idempotency_key" in op_v2
        assert isinstance(op_v2["idempotency_key"], str)
        assert len(op_v2["idempotency_key"]) == 32

        # payment_requested
        pr = factory.payment_requested()
        for k in ("request_id", "order_id", "amount_minor", "currency", "gateway"):
            assert k in pr
        assert pr["gateway"] in ["stripe", "adyen", "worldpay", "paypal"]

        # order_placed
        op2 = factory.order_placed()
        for k in ("order_id", "actor_id", "account_id", "causation_id"):
            assert k in op2

        # payment_succeeded
        ps = factory.payment_succeeded()
        assert "payment_id" in ps
        assert "gateway_ref" in ps
        assert ps["gateway_ref"].startswith(("pi_", "ch_", "txn_", "pay_"))

        # payment_failed
        pf = factory.payment_failed()
        assert "reason" in pf
        assert "gateway_error_code" in pf

        # gateway_webhook_received v1
        gw = factory.gateway_webhook_received()
        for k in ("observation_id", "gateway_ref", "webhook_type"):
            assert k in gw

        # gateway_webhook_received v2
        gw_v2 = factory.gateway_webhook_received(use_v2=True)
        assert "signature_valid" in gw_v2
        assert "idempotency_key" in gw_v2

        # http_request_observed
        hr = factory.http_request_observed()
        for k in (
            "trace_id",
            "span_id",
            "http_method",
            "request_path",
            "response_status",
            "duration_ms",
        ):
            assert k in hr

        # account_balance_calculated
        ab = factory.account_balance_calculated()
        for k in ("calculation_id", "account_id", "balance_minor", "currency", "as_of_sequence"):
            assert k in ab

        # daily_revenue_aggregated
        dr = factory.daily_revenue_aggregated()
        for k in (
            "calculation_id",
            "revenue_date",
            "total_revenue_minor",
            "currency",
            "order_count",
        ):
            assert k in dr

        # daily_revenue_aggregated v2
        dr_v2 = factory.daily_revenue_aggregated(use_v2=True)
        assert "average_order_value_minor" in dr_v2

    def test_distributions_combined(self) -> None:
        """Combined: should_reject_order rate, payment_outcome distribution,
        and seed determinism."""
        # Rejection rate
        rej_factory = PRADataFactory(seed=42, rejection_rate=0.5)
        rejections = sum(1 for _ in range(1000) if rej_factory.should_reject_order())
        assert 400 < rejections < 600

        # Payment outcome distribution
        po_factory = PRADataFactory(seed=42, payment_failure_rate=0.10, payment_timeout_rate=0.02)
        outcomes = defaultdict(int)
        for _ in range(1000):
            outcomes[po_factory.get_payment_outcome()] += 1
        assert outcomes["success"] > 800
        assert 50 < outcomes["failure"] < 150
        assert outcomes["timeout"] < 50

        # Determinism
        f1 = PRADataFactory(seed=42)
        f2 = PRADataFactory(seed=42)
        for _ in range(10):
            assert (
                f1.order_placement_requested()["currency"]
                == f2.order_placement_requested()["currency"]
            )


class TestLoadProfiles:
    """Tests for load profiles."""

    def test_profiles_combined(self) -> None:
        """Combined: SteadyRamp phase transitions, Burst, SkewedBurst,
        FailureInjection metadata, Replay, quick test factory, is_complete,
        progress percentage."""
        # SteadyRamp phases
        sr = SteadyRampProfile(
            warmup_rate=10,
            peak_rate=100,
            warmup_seconds=10,
            ramp_seconds=10,
            peak_seconds=10,
            cooldown_seconds=10,
        )
        s = sr.get_state(5)
        assert s.phase == LoadPhase.WARMUP and s.target_rate == 10
        s = sr.get_state(15)
        assert s.phase == LoadPhase.RAMP and 50 < s.target_rate < 60
        s = sr.get_state(25)
        assert s.phase == LoadPhase.PEAK and s.target_rate == 100
        s = sr.get_state(35)
        assert s.phase == LoadPhase.COOLDOWN
        s = sr.get_state(45)
        assert s.phase == LoadPhase.COMPLETE and s.target_rate == 0

        # Burst profile
        bp = BurstProfile(
            baseline_rate=100,
            burst_multiplier=10,
            baseline_seconds=10,
            burst_seconds=10,
            recovery_seconds=10,
        )
        s = bp.get_state(5)
        assert s.phase == LoadPhase.WARMUP and s.target_rate == 100
        s = bp.get_state(15)
        assert s.phase == LoadPhase.PEAK and s.target_rate == 1000
        assert s.metadata.get("burst_active")
        s = bp.get_state(25)
        assert s.phase == LoadPhase.COOLDOWN and s.target_rate == 100

        # SkewedBurst metadata
        skew = SkewedBurstProfile(
            baseline_rate=100,
            burst_multiplier=10,
            hot_key_probability=0.95,
            baseline_seconds=10,
            burst_seconds=10,
            recovery_seconds=10,
        )
        s = skew.get_state(15)
        assert s.metadata.get("skewed_burst")
        assert s.metadata.get("hot_key_probability") == 0.95

        # FailureInjection metadata
        fi = FailureInjectionProfile(
            rate=500,
            failure_probability=0.20,
            failure_targets=["database", "gateway"],
            duration_seconds=60,
        )
        s = fi.get_state(30)
        assert s.metadata.get("failure_injection")
        assert s.metadata.get("failure_probability") == 0.20
        assert "database" in s.metadata.get("failure_targets", [])

        # Replay
        rp = ReplayProfile(source_stream="orders_fact", max_rate=10000, estimated_records=100000)
        s = rp.get_state(5)
        assert s.metadata.get("replay_mode")
        assert s.metadata.get("source_stream") == "orders_fact"
        assert s.target_rate == 10000

        # Quick test factory
        qt = create_quick_test_profile()
        assert qt.peak_rate == 100
        assert qt.total_duration_seconds == 60

        # is_complete
        ic = SteadyRampProfile(
            warmup_seconds=10, ramp_seconds=10, peak_seconds=10, cooldown_seconds=10
        )
        assert not ic.is_complete(20)
        assert not ic.is_complete(39)
        assert ic.is_complete(40)
        assert ic.is_complete(100)

        # Progress percentage
        pp = SteadyRampProfile(
            warmup_seconds=25, ramp_seconds=25, peak_seconds=25, cooldown_seconds=25
        )
        assert pp.get_state(0).progress_pct == 0
        assert pp.get_state(50).progress_pct == 50
        assert pp.get_state(100).progress_pct == 100


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

    def test_config_combined(self) -> None:
        """Combined: default values + custom override."""
        # Defaults
        d = GeneratorConfig()
        assert d.rejection_rate == 0.15
        assert d.payment_failure_rate == 0.10
        assert d.payment_timeout_rate == 0.02
        assert d.actor_count == 100
        assert d.account_count == 200
        assert d.hot_key_ratio == 0.1
        assert d.hot_traffic_share == 0.8
        assert d.v2_schema_probability == 0.3
        assert d.duplicate_probability == 0.05

        # Custom
        c = GeneratorConfig(seed=42, rejection_rate=0.5, actor_count=50, duplicate_probability=0.1)
        assert c.seed == 42
        assert c.rejection_rate == 0.5
        assert c.actor_count == 50
        assert c.duplicate_probability == 0.1


class TestGeneratorStats:
    """Tests for GeneratorStats."""

    def test_stats_combined(self) -> None:
        """Combined: total_generated calc + initial stats are zero."""
        # Total
        s = GeneratorStats(
            intents_generated=100,
            facts_generated=50,
            observations_generated=25,
            derivations_generated=10,
        )
        assert s.total_generated == 185

        # Initial
        init = GeneratorStats()
        assert init.total_generated == 0
        assert init.errors == 0
        assert init.duplicates_generated == 0
