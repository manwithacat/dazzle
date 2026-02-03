"""
TigerBeetle-specific PRA scenarios for stress testing ledger operations.

These scenarios exercise TigerBeetle under various load patterns to
identify bottlenecks and validate performance characteristics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .tigerbeetle_generator import TBGeneratorConfig


class TBScenarioType(StrEnum):
    """Types of TigerBeetle test scenarios."""

    TB_QUICK = "tb_quick"
    TB_STEADY = "tb_steady"
    TB_BURST = "tb_burst"
    TB_HOT_ACCOUNTS = "tb_hot_accounts"
    TB_MULTI_LEG = "tb_multi_leg"
    TB_OVERDRAFT = "tb_overdraft"
    TB_FULL = "tb_full"


@dataclass
class TBSuccessCriteria:
    """
    Success criteria for TigerBeetle stress tests.

    Defines thresholds that determine pass/fail.
    """

    # Latency thresholds (milliseconds)
    max_p50_latency_ms: float | None = None
    max_p95_latency_ms: float | None = None
    max_p99_latency_ms: float | None = None

    # Throughput thresholds
    min_transfers_per_sec: float | None = None
    min_accounts_created: int | None = None

    # Error thresholds
    max_transfer_failure_rate: float | None = None
    max_account_failure_rate: float | None = None

    # Specific operation thresholds
    max_multi_leg_failure_rate: float | None = None
    expected_overdraft_rejection_rate: float | None = None  # Expected to fail


@dataclass
class TBScenario:
    """
    A TigerBeetle test scenario configuration.

    Encapsulates all settings for a reproducible TigerBeetle stress test.
    """

    name: str
    description: str
    scenario_type: TBScenarioType
    generator_config: TBGeneratorConfig
    success_criteria: TBSuccessCriteria
    metadata: dict[str, Any] = field(default_factory=dict)


def create_tb_quick_scenario() -> TBScenario:
    """
    Quick TigerBeetle sanity check.

    30-second test with moderate load to verify connectivity
    and basic operation.
    """
    return TBScenario(
        name="tb_quick",
        description="Quick 30-second TigerBeetle sanity check",
        scenario_type=TBScenarioType.TB_QUICK,
        generator_config=TBGeneratorConfig(
            num_accounts=100,
            transfers_per_second=50,
            warmup_seconds=2,
            steady_seconds=15,
            burst_seconds=5,
            cooldown_seconds=2,
            multi_leg_probability=0.05,
            seed=42,
        ),
        success_criteria=TBSuccessCriteria(
            max_p95_latency_ms=50,  # TigerBeetle should be very fast
            min_transfers_per_sec=40,
            max_transfer_failure_rate=0.01,
        ),
        metadata={"duration_seconds": 30},
    )


def create_tb_steady_scenario() -> TBScenario:
    """
    Steady-state TigerBeetle test.

    2-minute test with consistent load to measure baseline performance.
    """
    return TBScenario(
        name="tb_steady",
        description="2-minute steady-state TigerBeetle performance test",
        scenario_type=TBScenarioType.TB_STEADY,
        generator_config=TBGeneratorConfig(
            num_accounts=500,
            transfers_per_second=200,
            warmup_seconds=5,
            steady_seconds=90,
            burst_seconds=0,
            cooldown_seconds=5,
            multi_leg_probability=0.1,
            seed=42,
        ),
        success_criteria=TBSuccessCriteria(
            max_p50_latency_ms=5,
            max_p95_latency_ms=20,
            max_p99_latency_ms=50,
            min_transfers_per_sec=180,
            max_transfer_failure_rate=0.005,
        ),
        metadata={"duration_seconds": 120},
    )


def create_tb_burst_scenario() -> TBScenario:
    """
    TigerBeetle burst test.

    Tests system response to sudden 5x load spike.
    """
    return TBScenario(
        name="tb_burst",
        description="TigerBeetle burst test with 5x spike",
        scenario_type=TBScenarioType.TB_BURST,
        generator_config=TBGeneratorConfig(
            num_accounts=500,
            transfers_per_second=100,
            warmup_seconds=5,
            steady_seconds=20,
            burst_seconds=30,
            burst_multiplier=5.0,
            cooldown_seconds=10,
            seed=42,
        ),
        success_criteria=TBSuccessCriteria(
            max_p99_latency_ms=100,  # Allow higher during burst
            min_transfers_per_sec=80,  # Lower due to averaging with burst
            max_transfer_failure_rate=0.02,
        ),
        metadata={"burst_multiplier": 5.0, "duration_seconds": 65},
    )


def create_tb_hot_accounts_scenario() -> TBScenario:
    """
    TigerBeetle hot accounts test.

    Tests performance when 80% of traffic goes to 5% of accounts
    (Pareto distribution).
    """
    return TBScenario(
        name="tb_hot_accounts",
        description="Hot account contention test (80/5 distribution)",
        scenario_type=TBScenarioType.TB_HOT_ACCOUNTS,
        generator_config=TBGeneratorConfig(
            num_accounts=200,
            transfers_per_second=300,
            hot_account_probability=0.80,
            hot_account_count=10,  # 5% of 200
            warmup_seconds=5,
            steady_seconds=60,
            burst_seconds=0,
            cooldown_seconds=5,
            seed=42,
        ),
        success_criteria=TBSuccessCriteria(
            max_p95_latency_ms=30,
            max_p99_latency_ms=100,  # Hot accounts may be slower
            min_transfers_per_sec=250,
            max_transfer_failure_rate=0.01,
        ),
        metadata={
            "hot_account_percentage": 5,
            "traffic_share": 80,
            "duration_seconds": 70,
        },
    )


def create_tb_multi_leg_scenario() -> TBScenario:
    """
    TigerBeetle multi-leg transaction test.

    Tests linked transfer chains with 50% multi-leg transactions.
    """
    return TBScenario(
        name="tb_multi_leg",
        description="Multi-leg linked transaction test (50% multi-leg)",
        scenario_type=TBScenarioType.TB_MULTI_LEG,
        generator_config=TBGeneratorConfig(
            num_accounts=300,
            transfers_per_second=100,
            multi_leg_probability=0.50,
            max_legs_per_transaction=4,
            warmup_seconds=5,
            steady_seconds=60,
            burst_seconds=0,
            cooldown_seconds=5,
            seed=42,
        ),
        success_criteria=TBSuccessCriteria(
            max_p95_latency_ms=50,  # Multi-leg has more overhead
            max_p99_latency_ms=100,
            min_transfers_per_sec=80,  # Lower due to multi-leg overhead
            max_multi_leg_failure_rate=0.01,
        ),
        metadata={
            "multi_leg_probability": 0.50,
            "max_legs": 4,
            "duration_seconds": 70,
        },
    )


def create_tb_overdraft_scenario() -> TBScenario:
    """
    TigerBeetle overdraft rejection test.

    Tests that overdraft attempts are properly rejected.
    Accounts start with zero balance, so most transfers should fail
    unless we fund them first.
    """
    return TBScenario(
        name="tb_overdraft",
        description="Overdraft rejection test (constraint validation)",
        scenario_type=TBScenarioType.TB_OVERDRAFT,
        generator_config=TBGeneratorConfig(
            num_accounts=100,
            transfers_per_second=100,
            overdraft_probability=0.50,  # 50% of transfers attempt overdraft
            warmup_seconds=2,
            steady_seconds=30,
            burst_seconds=0,
            cooldown_seconds=2,
            seed=42,
        ),
        success_criteria=TBSuccessCriteria(
            max_p95_latency_ms=20,
            # Expect high failure rate due to overdraft attempts
            expected_overdraft_rejection_rate=0.45,  # ~50% overdrafts should fail
        ),
        metadata={
            "overdraft_probability": 0.50,
            "duration_seconds": 34,
        },
    )


def create_tb_full_scenario() -> TBScenario:
    """
    Comprehensive TigerBeetle test.

    5-minute test exercising all patterns: steady, burst, hot accounts,
    multi-leg, and overdraft testing.
    """
    return TBScenario(
        name="tb_full",
        description="Comprehensive 5-minute TigerBeetle stress test",
        scenario_type=TBScenarioType.TB_FULL,
        generator_config=TBGeneratorConfig(
            num_accounts=1000,
            transfers_per_second=500,
            multi_leg_probability=0.15,
            max_legs_per_transaction=4,
            hot_account_probability=0.70,
            hot_account_count=50,
            overdraft_probability=0.05,
            warmup_seconds=10,
            steady_seconds=180,
            burst_seconds=60,
            burst_multiplier=3.0,
            cooldown_seconds=30,
            seed=42,
        ),
        success_criteria=TBSuccessCriteria(
            max_p50_latency_ms=10,
            max_p95_latency_ms=50,
            max_p99_latency_ms=200,
            min_transfers_per_sec=400,
            min_accounts_created=990,  # Allow some failures
            max_transfer_failure_rate=0.10,  # Higher due to overdrafts
        ),
        metadata={
            "duration_seconds": 280,
            "exercises_all_patterns": True,
        },
    )


# Registry of TigerBeetle scenarios
TB_SCENARIOS: dict[TBScenarioType, TBScenario] = {
    TBScenarioType.TB_QUICK: create_tb_quick_scenario(),
    TBScenarioType.TB_STEADY: create_tb_steady_scenario(),
    TBScenarioType.TB_BURST: create_tb_burst_scenario(),
    TBScenarioType.TB_HOT_ACCOUNTS: create_tb_hot_accounts_scenario(),
    TBScenarioType.TB_MULTI_LEG: create_tb_multi_leg_scenario(),
    TBScenarioType.TB_OVERDRAFT: create_tb_overdraft_scenario(),
    TBScenarioType.TB_FULL: create_tb_full_scenario(),
}


def get_tb_scenario(scenario_type: TBScenarioType | str) -> TBScenario:
    """
    Get a TigerBeetle scenario by type.

    Args:
        scenario_type: TBScenarioType enum or string name

    Returns:
        TBScenario configuration

    Raises:
        KeyError: If scenario type not found
    """
    if isinstance(scenario_type, str):
        scenario_type = TBScenarioType(scenario_type)

    return TB_SCENARIOS[scenario_type]


def list_tb_scenarios() -> list[dict[str, Any]]:
    """
    List all available TigerBeetle scenarios.

    Returns:
        List of scenario summaries
    """
    return [
        {
            "name": s.name,
            "type": s.scenario_type.value,
            "description": s.description,
            "duration_seconds": s.metadata.get("duration_seconds", "varies"),
        }
        for s in TB_SCENARIOS.values()
    ]
