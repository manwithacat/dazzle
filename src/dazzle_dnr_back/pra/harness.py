"""
Test harness for PRA stress testing.

Orchestrates load generation, event processing, metrics collection,
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

from dazzle_dnr_back.events.bus import EventBus
from dazzle_dnr_back.events.dev_sqlite import DevBrokerSQLite
from dazzle_dnr_back.events.envelope import EventEnvelope
from dazzle_dnr_back.metrics import MetricsCollector
from dazzle_dnr_back.metrics.reporter import ReportFormat

from .consumers import ConsumerGroup
from .generator import GeneratorStats, LoadGenerator
from .scenarios import ScenarioType, StressScenario, SuccessCriteria, get_scenario

logger = logging.getLogger(__name__)


class RunStatus(str, Enum):
    """Status of a test run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class CriteriaResult:
    """Result of evaluating a single criterion."""

    name: str
    threshold: float
    actual: float
    passed: bool
    unit: str = ""


@dataclass
class RunResult:
    """
    Complete result of a test run.

    Contains all metrics, criteria evaluations, and status.
    """

    test_id: str
    scenario_name: str
    scenario_type: ScenarioType
    status: RunStatus
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float = 0.0

    # Generator stats
    generator_stats: GeneratorStats | None = None

    # Consumer stats
    consumer_stats: dict[str, dict[str, Any]] = field(default_factory=dict)

    # Metrics
    metrics_snapshot: dict[str, Any] = field(default_factory=dict)

    # Criteria evaluation
    criteria_results: list[CriteriaResult] = field(default_factory=list)
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
            "generator_stats": {
                "intents_generated": self.generator_stats.intents_generated,
                "facts_generated": self.generator_stats.facts_generated,
                "observations_generated": self.generator_stats.observations_generated,
                "derivations_generated": self.generator_stats.derivations_generated,
                "duplicates_generated": self.generator_stats.duplicates_generated,
                "total_generated": self.generator_stats.total_generated,
                "errors": self.generator_stats.errors,
            }
            if self.generator_stats
            else None,
            "consumer_stats": self.consumer_stats,
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


class StressHarness:
    """
    Orchestrates PRA stress tests.

    Coordinates load generation, event processing, and metrics collection.

    Example:
        harness = StressHarness()
        result = await harness.run_scenario(ScenarioType.STANDARD)
        print(result.criteria_passed)
    """

    def __init__(
        self,
        event_bus: EventBus | None = None,
        db_path: str = ":memory:",
    ) -> None:
        """
        Initialize the test harness.

        Args:
            event_bus: Optional event bus (creates DevBrokerSQLite if not provided)
            db_path: Path for SQLite database if creating event bus
        """
        self._event_bus = event_bus
        self._db_path = db_path
        self._owns_event_bus = event_bus is None

        # Will be initialized per test
        self._metrics: MetricsCollector | None = None
        self._generator: LoadGenerator | None = None
        self._consumers: ConsumerGroup | None = None
        self._current_result: RunResult | None = None

        # Event routing
        self._topic_events: dict[str, list[EventEnvelope]] = {}

    async def _ensure_event_bus(self) -> EventBus:
        """Ensure event bus is initialized."""
        if self._event_bus is None:
            self._event_bus = DevBrokerSQLite(self._db_path)
            await self._event_bus.connect()
        return self._event_bus

    async def run_scenario(
        self,
        scenario_type: ScenarioType | str,
        progress_callback: Any | None = None,
    ) -> RunResult:
        """
        Run a predefined test scenario.

        Args:
            scenario_type: Type of scenario to run
            progress_callback: Optional callback for progress updates

        Returns:
            RunResult with all metrics and evaluations
        """
        scenario = get_scenario(scenario_type)
        return await self.run_test(scenario, progress_callback)

    async def run_test(
        self,
        scenario: StressScenario,
        progress_callback: Any | None = None,
    ) -> RunResult:
        """
        Run a custom test scenario.

        Args:
            scenario: StressScenario configuration
            progress_callback: Optional callback for progress updates

        Returns:
            RunResult with all metrics and evaluations
        """
        test_id = str(uuid4())[:8]
        started_at = datetime.now(UTC)
        start_time = time.monotonic()

        logger.info(f"Starting test {test_id}: {scenario.name}")

        result = RunResult(
            test_id=test_id,
            scenario_name=scenario.name,
            scenario_type=scenario.scenario_type,
            status=RunStatus.RUNNING,
            started_at=started_at,
        )
        self._current_result = result

        try:
            # Initialize components
            await self._ensure_event_bus()
            self._metrics = MetricsCollector()
            self._topic_events = {}

            # Create consumers
            self._consumers = scenario.create_consumers(self._metrics)

            # Create generator
            self._generator = LoadGenerator(
                profile=scenario.profile,
                emit_callback=self._handle_emitted_event,
                config=scenario.generator_config,
                metrics=self._metrics,
            )

            # Run test
            await self._generator.start()

            # Run consumer loop concurrently
            consumer_task = asyncio.create_task(self._run_consumer_loop(progress_callback))

            # Wait for generator to complete
            while self._generator.is_running:
                await asyncio.sleep(0.1)

                # Report progress
                if progress_callback and self._generator:
                    state = self._generator.get_current_state()
                    if state:
                        progress_callback(
                            phase=state.phase.value,
                            progress=state.progress_pct,
                            rate=state.target_rate,
                        )

            # Stop generator and wait a bit for consumers to catch up
            gen_stats = await self._generator.stop()
            await asyncio.sleep(0.5)  # Allow consumer processing to complete

            # Cancel consumer loop
            consumer_task.cancel()
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass

            # Collect results
            result.generator_stats = gen_stats
            result.consumer_stats = {
                name: {
                    "events_processed": stats.events_processed,
                    "events_failed": stats.events_failed,
                    "events_dlq": stats.events_dlq,
                    "avg_processing_ms": stats.avg_processing_ms,
                }
                for name, stats in self._consumers.get_stats().items()
            }

            # Get metrics snapshot
            result.metrics_snapshot = self._metrics.to_dict()

            # Evaluate success criteria
            result.criteria_results = self._evaluate_criteria(
                scenario.success_criteria, result.metrics_snapshot
            )
            result.criteria_passed = all(cr.passed for cr in result.criteria_results)

            # Set final status
            result.status = RunStatus.COMPLETED
            result.completed_at = datetime.now(UTC)
            result.duration_seconds = time.monotonic() - start_time

            logger.info(
                f"Test {test_id} completed: {'PASSED' if result.criteria_passed else 'FAILED'}"
            )

        except Exception as e:
            logger.error(f"Test {test_id} failed with error: {e}")
            result.status = RunStatus.FAILED
            result.error_message = str(e)
            result.completed_at = datetime.now(UTC)
            result.duration_seconds = time.monotonic() - start_time

        finally:
            # Cleanup
            if self._generator and self._generator.is_running:
                await self._generator.stop()

            # Note: DevBrokerSQLite doesn't require explicit disconnect
            # Just clear the reference if we own it
            if self._owns_event_bus:
                self._event_bus = None

        return result

    async def _handle_emitted_event(self, topic: str, envelope: EventEnvelope) -> None:
        """Handle event emitted by generator."""
        # Store for consumer processing
        if topic not in self._topic_events:
            self._topic_events[topic] = []
        self._topic_events[topic].append(envelope)

        # Also publish to event bus if available
        if self._event_bus:
            await self._event_bus.publish(topic, envelope)

    async def _run_consumer_loop(self, progress_callback: Any | None = None) -> None:
        """Run consumer processing loop."""
        if not self._consumers:
            return

        while True:
            # Process events for each consumer
            for consumer in self._consumers.consumers:
                for topic in consumer.topics:
                    events = self._topic_events.get(topic, [])

                    # Process available events
                    while events:
                        envelope = events.pop(0)
                        await consumer.process(topic, envelope)

            await asyncio.sleep(0.01)  # Small delay to prevent tight loop

    def _evaluate_criteria(
        self,
        criteria: SuccessCriteria,
        metrics: dict[str, Any],
    ) -> list[CriteriaResult]:
        """Evaluate success criteria against metrics."""
        results: list[CriteriaResult] = []

        # Latency criteria
        latency = metrics.get("latency", {})

        if criteria.max_p50_latency_ms is not None:
            actual = latency.get("p50", 0)
            results.append(
                CriteriaResult(
                    name="p50_latency",
                    threshold=criteria.max_p50_latency_ms,
                    actual=actual,
                    passed=actual <= criteria.max_p50_latency_ms,
                    unit="ms",
                )
            )

        if criteria.max_p95_latency_ms is not None:
            actual = latency.get("p95", 0)
            results.append(
                CriteriaResult(
                    name="p95_latency",
                    threshold=criteria.max_p95_latency_ms,
                    actual=actual,
                    passed=actual <= criteria.max_p95_latency_ms,
                    unit="ms",
                )
            )

        if criteria.max_p99_latency_ms is not None:
            actual = latency.get("p99", 0)
            results.append(
                CriteriaResult(
                    name="p99_latency",
                    threshold=criteria.max_p99_latency_ms,
                    actual=actual,
                    passed=actual <= criteria.max_p99_latency_ms,
                    unit="ms",
                )
            )

        # Throughput criteria
        throughput = metrics.get("throughput", {})

        if criteria.min_throughput_per_sec is not None:
            # Sum all throughput counters
            total_rate = sum(
                t.get("current_rate", 0) for t in throughput.values() if isinstance(t, dict)
            )
            results.append(
                CriteriaResult(
                    name="throughput",
                    threshold=criteria.min_throughput_per_sec,
                    actual=total_rate,
                    passed=total_rate >= criteria.min_throughput_per_sec,
                    unit="events/sec",
                )
            )

        # Error rate criteria
        errors = metrics.get("errors", {})
        total_events = sum(
            t.get("total_count", 0) for t in throughput.values() if isinstance(t, dict)
        )
        total_errors = sum(errors.values()) if isinstance(errors, dict) else 0

        if criteria.max_error_rate is not None and total_events > 0:
            error_rate = total_errors / total_events
            results.append(
                CriteriaResult(
                    name="error_rate",
                    threshold=criteria.max_error_rate,
                    actual=error_rate,
                    passed=error_rate <= criteria.max_error_rate,
                    unit="ratio",
                )
            )

        # DLQ rate criteria
        dlq_count = errors.get("dlq", 0) if isinstance(errors, dict) else 0

        if criteria.max_dlq_rate is not None and total_events > 0:
            dlq_rate = dlq_count / total_events
            results.append(
                CriteriaResult(
                    name="dlq_rate",
                    threshold=criteria.max_dlq_rate,
                    actual=dlq_rate,
                    passed=dlq_rate <= criteria.max_dlq_rate,
                    unit="ratio",
                )
            )

        # Backlog growth rate criteria
        backlog = metrics.get("backlog", {})

        if criteria.max_backlog_growth_rate is not None:
            max_growth = 0.0
            for stream_data in backlog.values():
                if isinstance(stream_data, dict):
                    growth = stream_data.get("growth_rate", 0)
                    max_growth = max(max_growth, growth)

            results.append(
                CriteriaResult(
                    name="backlog_growth_rate",
                    threshold=criteria.max_backlog_growth_rate,
                    actual=max_growth,
                    passed=max_growth <= criteria.max_backlog_growth_rate,
                    unit="events/sec",
                )
            )

        # Rebuild time criteria
        recovery = metrics.get("recovery_times", {})

        if criteria.max_rebuild_time_ms is not None:
            max_rebuild = max(recovery.values()) if recovery else 0
            results.append(
                CriteriaResult(
                    name="rebuild_time",
                    threshold=criteria.max_rebuild_time_ms,
                    actual=max_rebuild,
                    passed=max_rebuild <= criteria.max_rebuild_time_ms,
                    unit="ms",
                )
            )

        return results

    def generate_report(self, result: RunResult, format: ReportFormat = ReportFormat.HUMAN) -> str:
        """
        Generate a report from test results.

        Args:
            result: RunResult from a test run
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

    def _generate_human_report(self, result: RunResult) -> str:
        """Generate human-readable report."""
        lines = [
            f"PRA Test Report: {result.scenario_name}",
            "=" * 50,
            f"Test ID: {result.test_id}",
            f"Status: {result.status.value.upper()}",
            f"Duration: {result.duration_seconds:.1f}s",
            "",
            "Generator Stats:",
            "-" * 20,
        ]

        if result.generator_stats:
            gs = result.generator_stats
            lines.extend(
                [
                    f"  Total generated: {gs.total_generated}",
                    f"  Intents: {gs.intents_generated}",
                    f"  Facts: {gs.facts_generated}",
                    f"  Observations: {gs.observations_generated}",
                    f"  Derivations: {gs.derivations_generated}",
                    f"  Duplicates: {gs.duplicates_generated}",
                    f"  Errors: {gs.errors}",
                ]
            )

        lines.extend(["", "Consumer Stats:", "-" * 20])
        for name, stats in result.consumer_stats.items():
            lines.append(f"  {name}:")
            lines.append(f"    Processed: {stats['events_processed']}")
            lines.append(f"    Failed: {stats['events_failed']}")
            lines.append(f"    DLQ: {stats['events_dlq']}")
            lines.append(f"    Avg latency: {stats['avg_processing_ms']:.2f}ms")

        lines.extend(["", "Success Criteria:", "-" * 20])
        for cr in result.criteria_results:
            status = "PASS" if cr.passed else "FAIL"
            lines.append(
                f"  [{status}] {cr.name}: {cr.actual:.2f}{cr.unit} (threshold: {cr.threshold}{cr.unit})"
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

    def _generate_markdown_report(self, result: RunResult) -> str:
        """Generate markdown report."""
        status_emoji = "✅" if result.criteria_passed else "❌"

        lines = [
            f"# PRA Test Report: {result.scenario_name}",
            "",
            f"**Status:** {status_emoji} {result.status.value.upper()}",
            f"**Test ID:** `{result.test_id}`",
            f"**Duration:** {result.duration_seconds:.1f}s",
            "",
            "## Generator Stats",
            "",
            "| Metric | Value |",
            "|--------|-------|",
        ]

        if result.generator_stats:
            gs = result.generator_stats
            lines.extend(
                [
                    f"| Total generated | {gs.total_generated} |",
                    f"| Intents | {gs.intents_generated} |",
                    f"| Facts | {gs.facts_generated} |",
                    f"| Observations | {gs.observations_generated} |",
                    f"| Derivations | {gs.derivations_generated} |",
                    f"| Duplicates | {gs.duplicates_generated} |",
                    f"| Errors | {gs.errors} |",
                ]
            )

        lines.extend(
            [
                "",
                "## Consumer Stats",
                "",
                "| Consumer | Processed | Failed | DLQ | Avg Latency |",
                "|----------|-----------|--------|-----|-------------|",
            ]
        )

        for name, stats in result.consumer_stats.items():
            lines.append(
                f"| {name} | {stats['events_processed']} | {stats['events_failed']} | {stats['events_dlq']} | {stats['avg_processing_ms']:.2f}ms |"
            )

        lines.extend(
            [
                "",
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
                f"## Overall Result: {status_emoji} {'PASSED' if result.criteria_passed else 'FAILED'}",
            ]
        )

        if result.error_message:
            lines.extend(["", f"**Error:** {result.error_message}"])

        return "\n".join(lines)


async def run_quick_test() -> RunResult:
    """
    Convenience function to run a quick test.

    Returns:
        RunResult from quick scenario
    """
    harness = StressHarness()
    return await harness.run_scenario(ScenarioType.QUICK)


async def run_standard_test() -> RunResult:
    """
    Convenience function to run a standard test.

    Returns:
        RunResult from standard scenario
    """
    harness = StressHarness()
    return await harness.run_scenario(ScenarioType.STANDARD)
