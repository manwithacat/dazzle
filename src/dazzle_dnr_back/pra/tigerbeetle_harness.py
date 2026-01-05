"""
TigerBeetle stress testing harness for PRA.

Orchestrates TigerBeetle load generation, metrics collection,
and result reporting.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from dazzle_dnr_back.metrics import MetricsCollector
from dazzle_dnr_back.metrics.reporter import ReportFormat

from .tigerbeetle_client import (
    TigerBeetleClient,
    TigerBeetleConfig,
    TigerBeetleStats,
    check_tigerbeetle_available,
)
from .tigerbeetle_generator import TBGeneratorStats, TigerBeetleLoadGenerator
from .tigerbeetle_scenarios import (
    TBScenario,
    TBScenarioType,
    TBSuccessCriteria,
    get_tb_scenario,
)

logger = logging.getLogger(__name__)


class TBRunStatus(str, Enum):
    """Status of a TigerBeetle test run."""

    PENDING = "pending"
    CONNECTING = "connecting"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"  # TigerBeetle not available


@dataclass
class TBCriteriaResult:
    """Result of evaluating a single criterion."""

    name: str
    threshold: float
    actual: float
    passed: bool
    unit: str = ""


@dataclass
class TBRunResult:
    """
    Complete result of a TigerBeetle test run.

    Contains all metrics, criteria evaluations, and status.
    """

    test_id: str
    scenario_name: str
    scenario_type: TBScenarioType
    status: TBRunStatus
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float = 0.0

    # Client stats
    client_stats: TigerBeetleStats | None = None

    # Generator stats
    generator_stats: TBGeneratorStats | None = None

    # Metrics snapshot
    metrics_snapshot: dict[str, Any] = field(default_factory=dict)

    # Criteria evaluation
    criteria_results: list[TBCriteriaResult] = field(default_factory=list)
    criteria_passed: bool = True

    # Error info
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "test_id": self.test_id,
            "scenario_name": self.scenario_name,
            "scenario_type": self.scenario_type.value,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "client_stats": {
                "accounts_created": self.client_stats.accounts_created,
                "accounts_failed": self.client_stats.accounts_failed,
                "transfers_created": self.client_stats.transfers_created,
                "transfers_failed": self.client_stats.transfers_failed,
                "lookups_performed": self.client_stats.lookups_performed,
                "avg_latency_ms": self.client_stats.avg_latency_ms,
            }
            if self.client_stats
            else None,
            "generator_stats": {
                "accounts_created": self.generator_stats.accounts_created,
                "accounts_failed": self.generator_stats.accounts_failed,
                "transfers_created": self.generator_stats.transfers_created,
                "transfers_failed": self.generator_stats.transfers_failed,
                "multi_leg_transfers": self.generator_stats.multi_leg_transfers,
                "overdraft_attempts": self.generator_stats.overdraft_attempts,
                "total_amount_transferred": self.generator_stats.total_amount_transferred,
                "current_rate": self.generator_stats.current_rate,
            }
            if self.generator_stats
            else None,
            "metrics": self.metrics_snapshot,
            "criteria_results": [
                {
                    "name": cr.name,
                    "threshold": cr.threshold,
                    "actual": cr.actual,
                    "passed": cr.passed,
                    "unit": cr.unit,
                }
                for cr in self.criteria_results
            ],
            "criteria_passed": self.criteria_passed,
            "error_message": self.error_message,
        }


class TigerBeetleHarness:
    """
    Orchestrates TigerBeetle PRA stress tests.

    Coordinates connection management, load generation, and metrics collection.

    Example:
        harness = TigerBeetleHarness()
        result = await harness.run_scenario(TBScenarioType.TB_QUICK)
        print(f"Passed: {result.criteria_passed}")
    """

    def __init__(
        self,
        tb_config: TigerBeetleConfig | None = None,
    ) -> None:
        """
        Initialize the TigerBeetle harness.

        Args:
            tb_config: Optional TigerBeetle connection configuration
        """
        self._tb_config = tb_config or TigerBeetleConfig()
        self._metrics: MetricsCollector | None = None
        self._current_result: TBRunResult | None = None

    async def check_available(self) -> bool:
        """Check if TigerBeetle is available."""
        return await check_tigerbeetle_available(self._tb_config)

    async def run_scenario(
        self,
        scenario_type: TBScenarioType | str,
        progress_callback: Any | None = None,
    ) -> TBRunResult:
        """
        Run a predefined TigerBeetle test scenario.

        Args:
            scenario_type: Type of scenario to run
            progress_callback: Optional callback for progress updates

        Returns:
            TBRunResult with all metrics and evaluations
        """
        scenario = get_tb_scenario(scenario_type)
        return await self.run_test(scenario, progress_callback)

    async def run_test(
        self,
        scenario: TBScenario,
        progress_callback: Any | None = None,
    ) -> TBRunResult:
        """
        Run a custom TigerBeetle test scenario.

        Args:
            scenario: TBScenario configuration
            progress_callback: Optional callback for progress updates

        Returns:
            TBRunResult with all metrics and evaluations
        """
        test_id = str(uuid4())[:8]
        started_at = datetime.now(UTC)
        start_time = time.monotonic()

        logger.info(f"Starting TigerBeetle test {test_id}: {scenario.name}")

        result = TBRunResult(
            test_id=test_id,
            scenario_name=scenario.name,
            scenario_type=scenario.scenario_type,
            status=TBRunStatus.PENDING,
            started_at=started_at,
        )
        self._current_result = result

        # Check TigerBeetle availability
        result.status = TBRunStatus.CONNECTING
        if not await self.check_available():
            logger.warning("TigerBeetle not available - skipping test")
            result.status = TBRunStatus.SKIPPED
            result.error_message = "TigerBeetle not available"
            result.completed_at = datetime.now(UTC)
            result.duration_seconds = time.monotonic() - start_time
            return result

        try:
            # Initialize metrics
            self._metrics = MetricsCollector()

            result.status = TBRunStatus.RUNNING

            # Connect and run test
            async with TigerBeetleClient.connect(self._tb_config, self._metrics) as client:
                # Create generator
                generator = TigerBeetleLoadGenerator(
                    config=scenario.generator_config,
                    metrics=self._metrics,
                )

                # Run with progress updates
                if progress_callback:
                    # Run generator with periodic progress updates
                    gen_task = asyncio.create_task(generator.run(client))

                    while not gen_task.done():
                        await asyncio.sleep(0.5)
                        state = generator.get_current_state()
                        progress_callback(
                            phase=state.phase.value,
                            progress=state.progress_pct,
                            rate=state.actual_rate,
                            accounts=state.accounts_created,
                            transfers=state.transfers_completed,
                        )

                    gen_stats = await gen_task
                else:
                    gen_stats = await generator.run(client)

                # Collect results
                result.generator_stats = gen_stats
                result.client_stats = client.stats

            # Get metrics snapshot
            result.metrics_snapshot = self._metrics.to_dict()

            # Evaluate success criteria
            result.criteria_results = self._evaluate_criteria(
                scenario.success_criteria,
                result.generator_stats,
                result.client_stats,
                result.metrics_snapshot,
            )
            result.criteria_passed = all(cr.passed for cr in result.criteria_results)

            # Set final status
            result.status = TBRunStatus.COMPLETED
            result.completed_at = datetime.now(UTC)
            result.duration_seconds = time.monotonic() - start_time

            logger.info(
                f"TigerBeetle test {test_id} completed: "
                f"{'PASSED' if result.criteria_passed else 'FAILED'}"
            )

        except Exception as e:
            logger.error(f"TigerBeetle test {test_id} failed: {e}")
            result.status = TBRunStatus.FAILED
            result.error_message = str(e)
            result.completed_at = datetime.now(UTC)
            result.duration_seconds = time.monotonic() - start_time

        return result

    def _evaluate_criteria(
        self,
        criteria: TBSuccessCriteria,
        gen_stats: TBGeneratorStats,
        client_stats: TigerBeetleStats,
        metrics: dict[str, Any],
    ) -> list[TBCriteriaResult]:
        """Evaluate success criteria against metrics."""
        results: list[TBCriteriaResult] = []

        # Get latency stats from metrics
        latency = metrics.get("latency", {})

        # P50 latency
        if criteria.max_p50_latency_ms is not None:
            actual = latency.get("p50", 0)
            results.append(
                TBCriteriaResult(
                    name="p50_latency",
                    threshold=criteria.max_p50_latency_ms,
                    actual=actual,
                    passed=actual <= criteria.max_p50_latency_ms,
                    unit="ms",
                )
            )

        # P95 latency
        if criteria.max_p95_latency_ms is not None:
            actual = latency.get("p95", 0)
            results.append(
                TBCriteriaResult(
                    name="p95_latency",
                    threshold=criteria.max_p95_latency_ms,
                    actual=actual,
                    passed=actual <= criteria.max_p95_latency_ms,
                    unit="ms",
                )
            )

        # P99 latency
        if criteria.max_p99_latency_ms is not None:
            actual = latency.get("p99", 0)
            results.append(
                TBCriteriaResult(
                    name="p99_latency",
                    threshold=criteria.max_p99_latency_ms,
                    actual=actual,
                    passed=actual <= criteria.max_p99_latency_ms,
                    unit="ms",
                )
            )

        # Transfers per second
        if criteria.min_transfers_per_sec is not None:
            actual = gen_stats.current_rate
            results.append(
                TBCriteriaResult(
                    name="transfers_per_sec",
                    threshold=criteria.min_transfers_per_sec,
                    actual=actual,
                    passed=actual >= criteria.min_transfers_per_sec,
                    unit="/s",
                )
            )

        # Accounts created
        if criteria.min_accounts_created is not None:
            actual = float(gen_stats.accounts_created)
            results.append(
                TBCriteriaResult(
                    name="accounts_created",
                    threshold=float(criteria.min_accounts_created),
                    actual=actual,
                    passed=actual >= criteria.min_accounts_created,
                    unit="",
                )
            )

        # Transfer failure rate
        if criteria.max_transfer_failure_rate is not None:
            total = gen_stats.transfers_created + gen_stats.transfers_failed
            if total > 0:
                actual = gen_stats.transfers_failed / total
            else:
                actual = 0.0
            results.append(
                TBCriteriaResult(
                    name="transfer_failure_rate",
                    threshold=criteria.max_transfer_failure_rate,
                    actual=actual,
                    passed=actual <= criteria.max_transfer_failure_rate,
                    unit="",
                )
            )

        # Account failure rate
        if criteria.max_account_failure_rate is not None:
            total = gen_stats.accounts_created + gen_stats.accounts_failed
            if total > 0:
                actual = gen_stats.accounts_failed / total
            else:
                actual = 0.0
            results.append(
                TBCriteriaResult(
                    name="account_failure_rate",
                    threshold=criteria.max_account_failure_rate,
                    actual=actual,
                    passed=actual <= criteria.max_account_failure_rate,
                    unit="",
                )
            )

        # Multi-leg failure rate
        if criteria.max_multi_leg_failure_rate is not None:
            # Estimate from transfer failures in multi-leg context
            total = gen_stats.multi_leg_transfers
            if total > 0:
                # Rough estimate - multi-leg failures would be reflected in transfer failures
                actual = gen_stats.transfers_failed / max(1, gen_stats.transfers_created)
            else:
                actual = 0.0
            results.append(
                TBCriteriaResult(
                    name="multi_leg_failure_rate",
                    threshold=criteria.max_multi_leg_failure_rate,
                    actual=actual,
                    passed=actual <= criteria.max_multi_leg_failure_rate,
                    unit="",
                )
            )

        return results

    def generate_report(
        self, result: TBRunResult, format: ReportFormat = ReportFormat.HUMAN
    ) -> str:
        """
        Generate a report from test results.

        Args:
            result: TBRunResult from a test run
            format: Output format

        Returns:
            Formatted report string
        """
        if format == ReportFormat.JSON:
            import json

            return json.dumps(result.to_dict(), indent=2, default=str)

        elif format == ReportFormat.MARKDOWN:
            return self._generate_markdown_report(result)

        else:
            return self._generate_human_report(result)

    def _generate_human_report(self, result: TBRunResult) -> str:
        """Generate human-readable report."""
        lines = [
            f"TigerBeetle PRA Report: {result.scenario_name}",
            "=" * 50,
            f"Test ID: {result.test_id}",
            f"Status: {result.status.value.upper()}",
            f"Duration: {result.duration_seconds:.1f}s",
            "",
        ]

        if result.generator_stats:
            gs = result.generator_stats
            lines.extend(
                [
                    "Generator Stats:",
                    "-" * 20,
                    f"  Accounts created: {gs.accounts_created}",
                    f"  Accounts failed: {gs.accounts_failed}",
                    f"  Transfers created: {gs.transfers_created}",
                    f"  Transfers failed: {gs.transfers_failed}",
                    f"  Multi-leg transfers: {gs.multi_leg_transfers}",
                    f"  Overdraft attempts: {gs.overdraft_attempts}",
                    f"  Total amount: {gs.total_amount_transferred:,}",
                    f"  Final rate: {gs.current_rate:.1f}/s",
                    "",
                ]
            )

        if result.client_stats:
            cs = result.client_stats
            lines.extend(
                [
                    "Client Stats:",
                    "-" * 20,
                    f"  Avg latency: {cs.avg_latency_ms:.2f}ms",
                    f"  Lookups: {cs.lookups_performed}",
                    "",
                ]
            )

        lines.extend(["Success Criteria:", "-" * 20])
        for cr in result.criteria_results:
            status = "PASS" if cr.passed else "FAIL"
            lines.append(
                f"  [{status}] {cr.name}: {cr.actual:.2f}{cr.unit} "
                f"(threshold: {cr.threshold}{cr.unit})"
            )

        lines.extend(
            [
                "",
                "=" * 50,
                f"OVERALL: {'PASSED' if result.criteria_passed else 'FAILED'}",
            ]
        )

        if result.error_message:
            lines.extend(["", f"Error: {result.error_message}"])

        return "\n".join(lines)

    def _generate_markdown_report(self, result: TBRunResult) -> str:
        """Generate markdown report."""
        status_emoji = "✅" if result.criteria_passed else "❌"
        if result.status == TBRunStatus.SKIPPED:
            status_emoji = "⏭️"

        lines = [
            f"# TigerBeetle PRA Report: {result.scenario_name}",
            "",
            f"**Status:** {status_emoji} {result.status.value.upper()}",
            f"**Test ID:** `{result.test_id}`",
            f"**Duration:** {result.duration_seconds:.1f}s",
            "",
        ]

        if result.generator_stats:
            gs = result.generator_stats
            lines.extend(
                [
                    "## Generator Stats",
                    "",
                    "| Metric | Value |",
                    "|--------|-------|",
                    f"| Accounts created | {gs.accounts_created} |",
                    f"| Accounts failed | {gs.accounts_failed} |",
                    f"| Transfers created | {gs.transfers_created} |",
                    f"| Transfers failed | {gs.transfers_failed} |",
                    f"| Multi-leg transfers | {gs.multi_leg_transfers} |",
                    f"| Overdraft attempts | {gs.overdraft_attempts} |",
                    f"| Total amount | {gs.total_amount_transferred:,} |",
                    f"| Final rate | {gs.current_rate:.1f}/s |",
                    "",
                ]
            )

        if result.client_stats:
            cs = result.client_stats
            lines.extend(
                [
                    "## Client Stats",
                    "",
                    "| Metric | Value |",
                    "|--------|-------|",
                    f"| Avg latency | {cs.avg_latency_ms:.2f}ms |",
                    f"| Lookups | {cs.lookups_performed} |",
                    "",
                ]
            )

        lines.extend(
            [
                "## Success Criteria",
                "",
                "| Criterion | Threshold | Actual | Status |",
                "|-----------|-----------|--------|--------|",
            ]
        )

        for cr in result.criteria_results:
            status = "✅ Pass" if cr.passed else "❌ Fail"
            lines.append(
                f"| {cr.name} | {cr.threshold}{cr.unit} | {cr.actual:.2f}{cr.unit} | {status} |"
            )

        lines.extend(
            [
                "",
                f"## Overall: {status_emoji} {'PASSED' if result.criteria_passed else 'FAILED'}",
            ]
        )

        if result.error_message:
            lines.extend(["", f"**Error:** {result.error_message}"])

        return "\n".join(lines)


async def run_quick_tb_scenario() -> TBRunResult:
    """
    Convenience function to run a quick TigerBeetle test.

    Returns:
        TBRunResult from quick scenario
    """
    harness = TigerBeetleHarness()
    return await harness.run_scenario(TBScenarioType.TB_QUICK)


async def run_tb_scenario(
    scenario_type: TBScenarioType | str,
    tb_config: TigerBeetleConfig | None = None,
) -> TBRunResult:
    """
    Convenience function to run a TigerBeetle test scenario.

    Args:
        scenario_type: Scenario type to run
        tb_config: Optional TigerBeetle configuration

    Returns:
        TBRunResult with test results
    """
    harness = TigerBeetleHarness(tb_config)
    return await harness.run_scenario(scenario_type)
