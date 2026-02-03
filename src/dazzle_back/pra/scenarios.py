"""
Predefined test scenarios for PRA stress testing.

Each scenario configures a complete test run with:
- Load profile
- Generator configuration
- Consumer setup
- Success criteria
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from dazzle_back.metrics import MetricsCollector

from .consumers import (
    ConsumerGroup,
    create_backpressure_test_consumers,
    create_dlq_test_consumers,
    create_full_test_consumers,
    create_projection_test_consumers,
)
from .generator import GeneratorConfig
from .profiles import (
    BurstProfile,
    FailureInjectionProfile,
    LoadProfile,
    ReplayProfile,
    SkewedBurstProfile,
    SteadyRampProfile,
    create_extended_test_profile,
    create_quick_test_profile,
    create_standard_test_profile,
)


class ScenarioType(StrEnum):
    """Types of test scenarios."""

    QUICK = "quick"
    STANDARD = "standard"
    EXTENDED = "extended"
    BURST = "burst"
    SKEWED_BURST = "skewed_burst"
    BACKPRESSURE = "backpressure"
    DLQ = "dlq"
    REPLAY = "replay"
    FAILURE_INJECTION = "failure_injection"
    FULL = "full"


@dataclass
class SuccessCriteria:
    """
    Success criteria for a test scenario.

    Defines thresholds that determine pass/fail.
    """

    # Latency thresholds (milliseconds)
    max_p50_latency_ms: float | None = None
    max_p95_latency_ms: float | None = None
    max_p99_latency_ms: float | None = None

    # Throughput thresholds
    min_throughput_per_sec: float | None = None

    # Error thresholds
    max_error_rate: float | None = None
    max_dlq_rate: float | None = None

    # Backlog thresholds
    max_backlog_growth_rate: float | None = None

    # Recovery thresholds
    max_rebuild_time_ms: float | None = None


@dataclass
class StressScenario:
    """
    A complete test scenario configuration.

    Encapsulates all settings needed to run a reproducible test.
    """

    name: str
    description: str
    scenario_type: ScenarioType
    profile: LoadProfile
    generator_config: GeneratorConfig
    consumer_factory: Callable[[MetricsCollector | None], ConsumerGroup]
    success_criteria: SuccessCriteria
    metadata: dict[str, Any] = field(default_factory=dict)

    def create_consumers(self, metrics: MetricsCollector | None = None) -> ConsumerGroup:
        """Create consumers for this scenario."""
        return self.consumer_factory(metrics)


def create_quick_scenario() -> StressScenario:
    """
    Quick sanity check scenario.

    1-minute test with moderate load.

    Note: Throughput threshold is set to 35 events/sec to account for
    CI environment variability. Local runs typically achieve 40-60 events/sec.
    """
    return StressScenario(
        name="quick",
        description="Quick 1-minute sanity check",
        scenario_type=ScenarioType.QUICK,
        profile=create_quick_test_profile(),
        generator_config=GeneratorConfig(
            seed=42,
            batch_size=50,
            batch_interval_ms=100,
        ),
        consumer_factory=create_full_test_consumers,
        success_criteria=SuccessCriteria(
            max_p95_latency_ms=500,
            min_throughput_per_sec=35,  # Lowered from 50 for CI environment variability
            max_error_rate=0.05,
        ),
        metadata={"duration_minutes": 1},
    )


def create_standard_scenario() -> StressScenario:
    """
    Standard 5-minute test scenario.

    Balanced test for regular CI runs.
    """
    return StressScenario(
        name="standard",
        description="Standard 5-minute performance test",
        scenario_type=ScenarioType.STANDARD,
        profile=create_standard_test_profile(),
        generator_config=GeneratorConfig(
            seed=42,
            batch_size=100,
            batch_interval_ms=50,
        ),
        consumer_factory=create_full_test_consumers,
        success_criteria=SuccessCriteria(
            max_p50_latency_ms=100,
            max_p95_latency_ms=300,
            max_p99_latency_ms=1000,
            min_throughput_per_sec=500,
            max_error_rate=0.02,
            max_dlq_rate=0.01,
        ),
        metadata={"duration_minutes": 5},
    )


def create_extended_scenario() -> StressScenario:
    """
    Extended 30-minute soak test.

    For release validation.
    """
    return StressScenario(
        name="extended",
        description="Extended 30-minute soak test",
        scenario_type=ScenarioType.EXTENDED,
        profile=create_extended_test_profile(),
        generator_config=GeneratorConfig(
            seed=42,
            batch_size=200,
            batch_interval_ms=20,
        ),
        consumer_factory=create_full_test_consumers,
        success_criteria=SuccessCriteria(
            max_p50_latency_ms=50,
            max_p95_latency_ms=200,
            max_p99_latency_ms=500,
            min_throughput_per_sec=2000,
            max_error_rate=0.01,
            max_dlq_rate=0.005,
        ),
        metadata={"duration_minutes": 30},
    )


def create_burst_scenario() -> StressScenario:
    """
    Burst test scenario.

    Tests system response to sudden load spikes.
    """
    return StressScenario(
        name="burst",
        description="Sudden 10x burst for backpressure testing",
        scenario_type=ScenarioType.BURST,
        profile=BurstProfile(
            baseline_rate=100,
            burst_multiplier=10,
            baseline_seconds=30,
            burst_seconds=30,
            recovery_seconds=60,
        ),
        generator_config=GeneratorConfig(
            seed=42,
            batch_size=200,
            batch_interval_ms=20,
        ),
        consumer_factory=create_backpressure_test_consumers,
        success_criteria=SuccessCriteria(
            max_p99_latency_ms=2000,  # Allow higher during burst
            max_error_rate=0.05,
            max_backlog_growth_rate=100,  # events/sec backlog growth max
        ),
        metadata={"burst_multiplier": 10},
    )


def create_skewed_burst_scenario() -> StressScenario:
    """
    Skewed burst scenario.

    Tests hot partition handling under burst.
    """
    return StressScenario(
        name="skewed_burst",
        description="Burst focused on hot partitions (95% traffic to 10% keys)",
        scenario_type=ScenarioType.SKEWED_BURST,
        profile=SkewedBurstProfile(
            baseline_rate=100,
            burst_multiplier=10,
            hot_key_probability=0.95,
            baseline_seconds=30,
            burst_seconds=30,
            recovery_seconds=60,
        ),
        generator_config=GeneratorConfig(
            seed=42,
            hot_key_ratio=0.1,
            hot_traffic_share=0.95,
            batch_size=200,
            batch_interval_ms=20,
        ),
        consumer_factory=create_projection_test_consumers,
        success_criteria=SuccessCriteria(
            max_p99_latency_ms=3000,  # Hot partitions may be slower
            max_error_rate=0.05,
        ),
        metadata={"hot_key_percentage": 10, "traffic_share": 95},
    )


def create_backpressure_scenario() -> StressScenario:
    """
    Backpressure testing scenario.

    One slow consumer creates backpressure.
    """
    return StressScenario(
        name="backpressure",
        description="Test bounded backlog with slow consumer",
        scenario_type=ScenarioType.BACKPRESSURE,
        profile=SteadyRampProfile(
            warmup_rate=50,
            peak_rate=500,
            warmup_seconds=10,
            ramp_seconds=30,
            peak_seconds=120,
            cooldown_seconds=30,
        ),
        generator_config=GeneratorConfig(
            seed=42,
            batch_size=100,
            batch_interval_ms=50,
        ),
        consumer_factory=create_backpressure_test_consumers,
        success_criteria=SuccessCriteria(
            max_backlog_growth_rate=50,  # Backlog should stay bounded
            max_error_rate=0.01,
        ),
        metadata={"slow_consumer_delay_ms": 200},
    )


def create_dlq_scenario() -> StressScenario:
    """
    DLQ activation scenario.

    Tests that invalid records route to DLQ.
    """
    return StressScenario(
        name="dlq",
        description="Test DLQ routing for failing events",
        scenario_type=ScenarioType.DLQ,
        profile=SteadyRampProfile(
            warmup_rate=100,
            peak_rate=500,
            warmup_seconds=10,
            ramp_seconds=20,
            peak_seconds=60,
            cooldown_seconds=10,
        ),
        generator_config=GeneratorConfig(
            seed=42,
            batch_size=100,
            batch_interval_ms=50,
        ),
        consumer_factory=create_dlq_test_consumers,
        success_criteria=SuccessCriteria(
            max_error_rate=0.15,  # Expect failures
            max_dlq_rate=0.05,  # But DLQ should be bounded
        ),
        metadata={"failure_probability": 0.10, "permanent_failure_probability": 0.02},
    )


def create_replay_scenario() -> StressScenario:
    """
    Full replay scenario.

    Tests derivation rebuild from logs.
    """
    return StressScenario(
        name="replay",
        description="Full derivation rebuild from offset zero",
        scenario_type=ScenarioType.REPLAY,
        profile=ReplayProfile(
            source_stream="orders_fact",
            max_rate=5000,
            estimated_records=50000,
        ),
        generator_config=GeneratorConfig(
            seed=42,
            batch_size=500,
            batch_interval_ms=10,
        ),
        consumer_factory=create_projection_test_consumers,
        success_criteria=SuccessCriteria(
            max_rebuild_time_ms=60000,  # 60 seconds max
            max_error_rate=0.001,
        ),
        metadata={"estimated_records": 50000, "max_rate": 5000},
    )


def create_failure_injection_scenario() -> StressScenario:
    """
    Failure injection scenario.

    Tests system behavior under partial failures.
    """
    return StressScenario(
        name="failure_injection",
        description="Partial downstream failure simulation",
        scenario_type=ScenarioType.FAILURE_INJECTION,
        profile=FailureInjectionProfile(
            rate=300,
            failure_probability=0.20,
            failure_targets=["database", "payment_gateway"],
            duration_seconds=180,
        ),
        generator_config=GeneratorConfig(
            seed=42,
            batch_size=50,
            batch_interval_ms=100,
        ),
        consumer_factory=create_dlq_test_consumers,
        success_criteria=SuccessCriteria(
            max_error_rate=0.25,  # Allow for injected failures
            max_dlq_rate=0.10,
        ),
        metadata={"failure_probability": 0.20, "failure_targets": ["database", "payment_gateway"]},
    )


def create_full_scenario() -> StressScenario:
    """
    Comprehensive full test scenario.

    Exercises all stress patterns sequentially.
    """
    return StressScenario(
        name="full",
        description="Comprehensive test exercising all patterns",
        scenario_type=ScenarioType.FULL,
        profile=SteadyRampProfile(
            warmup_rate=100,
            peak_rate=2000,
            warmup_seconds=60,
            ramp_seconds=120,
            peak_seconds=300,
            cooldown_seconds=60,
        ),
        generator_config=GeneratorConfig(
            seed=42,
            batch_size=200,
            batch_interval_ms=20,
            duplicate_probability=0.05,
            v2_schema_probability=0.30,
        ),
        consumer_factory=create_full_test_consumers,
        success_criteria=SuccessCriteria(
            max_p50_latency_ms=100,
            max_p95_latency_ms=500,
            max_p99_latency_ms=2000,
            min_throughput_per_sec=1000,
            max_error_rate=0.02,
            max_dlq_rate=0.01,
            max_backlog_growth_rate=100,
        ),
        metadata={"duration_minutes": 9, "exercises_all_patterns": True},
    )


# Registry of all scenarios
SCENARIOS: dict[ScenarioType, StressScenario] = {
    ScenarioType.QUICK: create_quick_scenario(),
    ScenarioType.STANDARD: create_standard_scenario(),
    ScenarioType.EXTENDED: create_extended_scenario(),
    ScenarioType.BURST: create_burst_scenario(),
    ScenarioType.SKEWED_BURST: create_skewed_burst_scenario(),
    ScenarioType.BACKPRESSURE: create_backpressure_scenario(),
    ScenarioType.DLQ: create_dlq_scenario(),
    ScenarioType.REPLAY: create_replay_scenario(),
    ScenarioType.FAILURE_INJECTION: create_failure_injection_scenario(),
    ScenarioType.FULL: create_full_scenario(),
}


def get_scenario(scenario_type: ScenarioType | str) -> StressScenario:
    """
    Get a test scenario by type.

    Args:
        scenario_type: ScenarioType enum or string name

    Returns:
        StressScenario configuration

    Raises:
        KeyError: If scenario type not found
    """
    if isinstance(scenario_type, str):
        scenario_type = ScenarioType(scenario_type)

    return SCENARIOS[scenario_type]


def list_scenarios() -> list[dict[str, Any]]:
    """
    List all available scenarios.

    Returns:
        List of scenario summaries
    """
    return [
        {
            "name": s.name,
            "type": s.scenario_type.value,
            "description": s.description,
            "duration_minutes": s.metadata.get("duration_minutes", "varies"),
        }
        for s in SCENARIOS.values()
    ]
