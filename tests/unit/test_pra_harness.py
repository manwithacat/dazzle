"""Tests for PRA test harness components."""

from __future__ import annotations

from uuid import uuid4

import pytest

from dazzle_dnr_back.events.envelope import EventEnvelope
from dazzle_dnr_back.metrics import MetricsCollector
from dazzle_dnr_back.pra.consumers import (
    ConsumerGroup,
    DerivationConsumer,
    FailingConsumer,
    NormalConsumer,
    ProjectionConsumer,
    SlowConsumer,
    create_backpressure_test_consumers,
    create_dlq_test_consumers,
    create_full_test_consumers,
    create_projection_test_consumers,
)
from dazzle_dnr_back.pra.harness import (
    CriteriaResult,
    TestHarness,
    TestResult,
    TestStatus,
    run_quick_test,
)
from dazzle_dnr_back.pra.scenarios import (
    ScenarioType,
    SuccessCriteria,
    TestScenario,
    get_scenario,
    list_scenarios,
)


class TestConsumers:
    """Tests for test consumers."""

    @pytest.mark.asyncio
    async def test_normal_consumer_processes_events(self) -> None:
        """Test NormalConsumer processes events successfully."""
        consumer = NormalConsumer(
            name="test_consumer",
            topics=["test_topic"],
        )

        envelope = EventEnvelope.create(
            event_type="test.event",
            key="test-key",
            payload={"data": "test"},
        )

        success = await consumer.process("test_topic", envelope)

        assert success
        assert consumer.stats.events_processed == 1
        assert consumer.stats.events_failed == 0

    @pytest.mark.asyncio
    async def test_slow_consumer_adds_delay(self) -> None:
        """Test SlowConsumer introduces latency."""
        consumer = SlowConsumer(
            name="slow_consumer",
            topics=["test_topic"],
            delay_ms=50,
            delay_variance_ms=0,
        )

        envelope = EventEnvelope.create(
            event_type="test.event",
            key="test-key",
            payload={"data": "test"},
        )

        import time

        start = time.monotonic()
        await consumer.process("test_topic", envelope)
        elapsed = (time.monotonic() - start) * 1000

        assert elapsed >= 45  # Allow some tolerance
        assert consumer.stats.events_processed == 1

    @pytest.mark.asyncio
    async def test_failing_consumer_failures(self) -> None:
        """Test FailingConsumer generates failures."""
        consumer = FailingConsumer(
            name="failing_consumer",
            topics=["test_topic"],
            failure_probability=1.0,  # Always fail (transient)
            permanent_failure_probability=0.0,
        )

        envelope = EventEnvelope.create(
            event_type="test.event",
            key="test-key",
            payload={"data": "test"},
        )

        success = await consumer.process("test_topic", envelope)

        assert not success
        assert consumer.stats.events_failed == 1

    @pytest.mark.asyncio
    async def test_failing_consumer_dlq(self) -> None:
        """Test FailingConsumer sends to DLQ on permanent failure."""
        consumer = FailingConsumer(
            name="failing_consumer",
            topics=["test_topic"],
            failure_probability=0.0,
            permanent_failure_probability=1.0,  # Always permanent fail
        )

        envelope = EventEnvelope.create(
            event_type="test.event",
            key="test-key",
            payload={"data": "test"},
        )

        success = await consumer.process("test_topic", envelope)

        assert not success
        assert consumer.stats.events_dlq == 1

    @pytest.mark.asyncio
    async def test_projection_consumer_updates_state(self) -> None:
        """Test ProjectionConsumer tracks entity state."""
        consumer = ProjectionConsumer(
            name="order_projection",
            topics=["orders"],
            entity_key_field="order_id",
            processing_time_ms=1,
        )

        order_id = str(uuid4())
        envelope = EventEnvelope.create(
            event_type="orders.created",
            key=order_id,
            payload={"order_id": order_id, "status": "pending"},
        )

        await consumer.process("orders", envelope)

        assert order_id in consumer.projections
        assert consumer.projections[order_id]["status"] == "pending"

        # Update the order
        envelope2 = EventEnvelope.create(
            event_type="orders.updated",
            key=order_id,
            payload={"order_id": order_id, "status": "shipped"},
        )

        await consumer.process("orders", envelope2)

        assert consumer.projections[order_id]["status"] == "shipped"

    @pytest.mark.asyncio
    async def test_derivation_consumer_rebuild(self) -> None:
        """Test DerivationConsumer tracks rebuild time."""
        consumer = DerivationConsumer(
            name="balance_derivation",
            topics=["ledger"],
            processing_time_ms=1,
        )

        consumer.start_rebuild()

        # Process some events
        for i in range(5):
            envelope = EventEnvelope.create(
                event_type="ledger.entry",
                key=str(i),
                payload={"amount": 100},
            )
            await consumer.process("ledger", envelope)

        consumer.complete_rebuild()

        assert consumer.sequence == 5
        assert consumer.rebuild_time_ms is not None
        assert consumer.rebuild_time_ms > 0

    @pytest.mark.asyncio
    async def test_consumer_with_metrics(self) -> None:
        """Test consumer records to MetricsCollector."""
        metrics = MetricsCollector()

        consumer = NormalConsumer(
            name="metered_consumer",
            topics=["test"],
            metrics=metrics,
        )

        envelope = EventEnvelope.create(
            event_type="test.event",
            key="test-key",
            payload={"data": "test"},
        )

        await consumer.process("test", envelope)

        # Check metrics were recorded
        throughput = metrics.get_throughput_stats("consumer.metered_consumer")
        assert throughput is not None
        assert throughput.total_count >= 1

    @pytest.mark.asyncio
    async def test_consumer_callback(self) -> None:
        """Test consumer callback is called."""
        called_with: list[tuple[str, EventEnvelope, float]] = []

        def callback(topic: str, envelope: EventEnvelope, latency_ms: float) -> None:
            called_with.append((topic, envelope, latency_ms))

        consumer = NormalConsumer(
            name="callback_consumer",
            topics=["test"],
            on_processed=callback,
        )

        envelope = EventEnvelope.create(
            event_type="test.event",
            key="test-key",
            payload={"data": "test"},
        )

        await consumer.process("test", envelope)

        assert len(called_with) == 1
        assert called_with[0][0] == "test"


class TestConsumerGroup:
    """Tests for ConsumerGroup."""

    def test_consumer_group_aggregation(self) -> None:
        """Test ConsumerGroup aggregates stats."""
        group = ConsumerGroup(name="test_group")

        c1 = NormalConsumer(name="c1", topics=["t1"])
        c1._stats.events_processed = 10
        c1._stats.events_failed = 2

        c2 = NormalConsumer(name="c2", topics=["t2"])
        c2._stats.events_processed = 20
        c2._stats.events_failed = 3

        group.add(c1)
        group.add(c2)

        assert group.total_processed() == 30
        assert group.total_failed() == 5

    def test_consumer_factories(self) -> None:
        """Test consumer factory functions."""
        bp = create_backpressure_test_consumers()
        assert len(bp.consumers) == 2

        dlq = create_dlq_test_consumers()
        assert len(dlq.consumers) == 2

        proj = create_projection_test_consumers()
        assert len(proj.consumers) == 2

        full = create_full_test_consumers()
        assert len(full.consumers) >= 4


class TestScenarios:
    """Tests for test scenarios."""

    def test_list_scenarios(self) -> None:
        """Test listing all scenarios."""
        scenarios = list_scenarios()

        assert len(scenarios) >= 5
        assert all("name" in s for s in scenarios)
        assert all("type" in s for s in scenarios)

    def test_get_scenario_by_type(self) -> None:
        """Test getting scenario by enum."""
        scenario = get_scenario(ScenarioType.QUICK)

        assert scenario.name == "quick"
        assert scenario.scenario_type == ScenarioType.QUICK
        assert scenario.profile is not None
        assert scenario.generator_config is not None
        assert scenario.success_criteria is not None

    def test_get_scenario_by_string(self) -> None:
        """Test getting scenario by string name."""
        scenario = get_scenario("standard")

        assert scenario.name == "standard"
        assert scenario.scenario_type == ScenarioType.STANDARD

    def test_scenario_creates_consumers(self) -> None:
        """Test scenario consumer factory works."""
        scenario = get_scenario(ScenarioType.QUICK)

        consumers = scenario.create_consumers()

        assert isinstance(consumers, ConsumerGroup)
        assert len(consumers.consumers) > 0

    def test_all_scenarios_valid(self) -> None:
        """Test all predefined scenarios are valid."""
        for scenario_type in ScenarioType:
            scenario = get_scenario(scenario_type)

            assert scenario.name
            assert scenario.description
            assert scenario.profile is not None
            assert scenario.generator_config is not None
            assert scenario.consumer_factory is not None


class TestSuccessCriteria:
    """Tests for success criteria."""

    def test_criteria_defaults(self) -> None:
        """Test criteria defaults to None."""
        criteria = SuccessCriteria()

        assert criteria.max_p50_latency_ms is None
        assert criteria.max_p95_latency_ms is None
        assert criteria.max_error_rate is None

    def test_criteria_custom(self) -> None:
        """Test custom criteria values."""
        criteria = SuccessCriteria(
            max_p50_latency_ms=100,
            max_p95_latency_ms=500,
            max_error_rate=0.01,
        )

        assert criteria.max_p50_latency_ms == 100
        assert criteria.max_p95_latency_ms == 500
        assert criteria.max_error_rate == 0.01


class TestCriteriaResult:
    """Tests for CriteriaResult."""

    def test_criteria_result_pass(self) -> None:
        """Test passing criteria result."""
        result = CriteriaResult(
            name="p95_latency",
            threshold=500,
            actual=300,
            passed=True,
            unit="ms",
        )

        assert result.passed
        assert result.actual < result.threshold

    def test_criteria_result_fail(self) -> None:
        """Test failing criteria result."""
        result = CriteriaResult(
            name="error_rate",
            threshold=0.01,
            actual=0.05,
            passed=False,
            unit="ratio",
        )

        assert not result.passed
        assert result.actual > result.threshold


class TestTestResult:
    """Tests for TestResult."""

    def test_result_to_dict(self) -> None:
        """Test result serialization."""
        from datetime import UTC, datetime

        from dazzle_dnr_back.pra.generator import GeneratorStats

        result = TestResult(
            test_id="abc123",
            scenario_name="quick",
            scenario_type=ScenarioType.QUICK,
            status=TestStatus.COMPLETED,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            duration_seconds=10.5,
            generator_stats=GeneratorStats(
                intents_generated=100,
                facts_generated=50,
            ),
            criteria_passed=True,
        )

        d = result.to_dict()

        assert d["test_id"] == "abc123"
        assert d["scenario_name"] == "quick"
        assert d["status"] == "completed"
        assert d["generator_stats"]["intents_generated"] == 100


class TestTestHarness:
    """Tests for TestHarness."""

    @pytest.mark.asyncio
    async def test_harness_initialization(self) -> None:
        """Test harness initializes correctly."""
        harness = TestHarness()

        assert harness._event_bus is None
        assert harness._owns_event_bus

    @pytest.mark.asyncio
    async def test_harness_run_minimal_scenario(self) -> None:
        """Test harness can run a minimal test."""
        from dazzle_dnr_back.pra.profiles import SteadyRampProfile

        # Create a very short scenario for testing
        scenario = TestScenario(
            name="minimal",
            description="Minimal test",
            scenario_type=ScenarioType.QUICK,
            profile=SteadyRampProfile(
                warmup_rate=10,
                peak_rate=10,
                warmup_seconds=0.05,
                ramp_seconds=0.05,
                peak_seconds=0.05,
                cooldown_seconds=0.05,
            ),
            generator_config=__import__(
                "dazzle_dnr_back.pra.generator", fromlist=["GeneratorConfig"]
            ).GeneratorConfig(
                seed=42,
                batch_size=5,
                batch_interval_ms=10,
            ),
            consumer_factory=create_full_test_consumers,
            success_criteria=SuccessCriteria(max_error_rate=0.5),
        )

        harness = TestHarness()
        result = await harness.run_test(scenario)

        assert result.status == TestStatus.COMPLETED
        assert result.generator_stats is not None
        assert result.generator_stats.total_generated > 0

    @pytest.mark.asyncio
    async def test_harness_evaluate_criteria(self) -> None:
        """Test harness evaluates success criteria."""
        harness = TestHarness()

        criteria = SuccessCriteria(
            max_p50_latency_ms=100,
            max_p95_latency_ms=500,
            max_error_rate=0.05,
        )

        metrics = {
            "latency": {"p50": 50, "p95": 200, "p99": 400},
            "throughput": {"events": {"total_count": 1000, "current_rate": 100}},
            "error_counts": {"rejection": 10},
        }

        results = harness._evaluate_criteria(criteria, metrics)

        # Find each result
        p50_result = next(r for r in results if r.name == "p50_latency")
        p95_result = next(r for r in results if r.name == "p95_latency")
        error_result = next(r for r in results if r.name == "error_rate")

        assert p50_result.passed  # 50 <= 100
        assert p95_result.passed  # 200 <= 500
        assert error_result.passed  # 10/1000 = 0.01 <= 0.05

    @pytest.mark.asyncio
    async def test_harness_generate_human_report(self) -> None:
        """Test harness generates human-readable report."""
        from datetime import UTC, datetime

        from dazzle_dnr_back.metrics.reporter import ReportFormat
        from dazzle_dnr_back.pra.generator import GeneratorStats

        harness = TestHarness()

        result = TestResult(
            test_id="test123",
            scenario_name="test_scenario",
            scenario_type=ScenarioType.QUICK,
            status=TestStatus.COMPLETED,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            duration_seconds=60,
            generator_stats=GeneratorStats(
                intents_generated=1000,
                facts_generated=500,
                observations_generated=200,
            ),
            consumer_stats={
                "consumer1": {
                    "events_processed": 100,
                    "events_failed": 5,
                    "events_dlq": 1,
                    "avg_processing_ms": 10.5,
                }
            },
            criteria_results=[
                CriteriaResult(
                    name="p95_latency",
                    threshold=500,
                    actual=300,
                    passed=True,
                    unit="ms",
                )
            ],
            criteria_passed=True,
        )

        report = harness.generate_report(result, format=ReportFormat.HUMAN)

        assert "test123" in report
        assert "test_scenario" in report
        assert "PASSED" in report

    @pytest.mark.asyncio
    async def test_harness_generate_markdown_report(self) -> None:
        """Test harness generates markdown report."""
        from datetime import UTC, datetime

        from dazzle_dnr_back.metrics.reporter import ReportFormat
        from dazzle_dnr_back.pra.generator import GeneratorStats

        harness = TestHarness()

        result = TestResult(
            test_id="test456",
            scenario_name="md_test",
            scenario_type=ScenarioType.STANDARD,
            status=TestStatus.COMPLETED,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            duration_seconds=30,
            generator_stats=GeneratorStats(),
            consumer_stats={},
            criteria_results=[],
            criteria_passed=True,
        )

        report = harness.generate_report(result, format=ReportFormat.MARKDOWN)

        assert "# PRA Test Report" in report
        assert "md_test" in report


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Takes too long for CI")
    async def test_run_quick_test(self) -> None:
        """Test run_quick_test convenience function."""
        result = await run_quick_test()

        assert result.status in [TestStatus.COMPLETED, TestStatus.FAILED]
        assert result.scenario_type == ScenarioType.QUICK
