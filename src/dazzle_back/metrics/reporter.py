"""
Metrics reporter for PRA.

Generates machine-readable (JSON) and human-readable reports from metrics.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from .collector import MetricsCollector


class ReportFormat(StrEnum):
    """Output format for metrics reports."""

    JSON = "json"
    HUMAN = "human"
    MARKDOWN = "markdown"


@dataclass
class PRAReport:
    """
    Complete PRA performance report.

    Machine-readable format suitable for CI comparison.
    """

    version: str = "1.0"
    profile: str = "unknown"
    timestamp: str = ""
    duration_seconds: float = 0.0

    # Summary metrics
    latency_p50_ms: float = 0.0
    latency_p95_ms: float = 0.0
    latency_p99_ms: float = 0.0

    throughput_intents_per_sec: float = 0.0
    throughput_facts_per_sec: float = 0.0
    throughput_projections_per_sec: float = 0.0

    backlog_max_lag: int = 0
    backlog_total_lag: int = 0

    recovery_rebuild_time_sec: float = 0.0

    rejection_rate: float = 0.0
    dlq_rate: float = 0.0
    retry_rate: float = 0.0

    # Detailed breakdowns
    latency_detail: dict[str, Any] | None = None
    throughput_detail: dict[str, Any] | None = None
    backlog_detail: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)


class MetricsReporter:
    """
    Generate reports from metrics collector.

    Example:
        reporter = MetricsReporter(collector)
        report = reporter.generate_report(profile="steady-ramp")

        # Output formats
        print(reporter.format_human(report))
        print(reporter.format_json(report))
        print(reporter.format_markdown(report))
    """

    def __init__(self, collector: MetricsCollector) -> None:
        """
        Initialize reporter.

        Args:
            collector: Metrics collector to report from
        """
        self.collector = collector

    def generate_report(self, profile: str = "unknown") -> PRAReport:
        """
        Generate a PRA report from current metrics.

        Args:
            profile: Load profile name

        Returns:
            PRAReport with all metrics
        """
        metrics = self.collector.snapshot()

        # Calculate summary latency (use end_to_end if available, else intent_to_fact)
        latency_key = "end_to_end"
        if latency_key not in metrics.latency:
            latency_key = "intent_to_fact"

        latency = metrics.latency.get(latency_key)
        p50 = latency.p50_ms if latency else 0.0
        p95 = latency.p95_ms if latency else 0.0
        p99 = latency.p99_ms if latency else 0.0

        # Calculate throughput rates
        intents = metrics.throughput.get("intents")
        facts = metrics.throughput.get("facts")
        projections = metrics.throughput.get("projections")

        intents_rate = intents.avg_rate if intents else 0.0
        facts_rate = facts.avg_rate if facts else 0.0
        proj_rate = projections.avg_rate if projections else 0.0

        # Calculate backlog
        max_lag = 0
        total_lag = 0
        for stats in metrics.backlog.values():
            total_lag += stats.current_lag
            if stats.max_lag > max_lag:
                max_lag = stats.max_lag

        # Calculate error rates
        total_intents = intents.total_count if intents else 1
        rejections = metrics.error_counts.get("rejection", 0)
        dlq = metrics.error_counts.get("dlq", 0)
        retries = metrics.error_counts.get("retry", 0)

        rejection_rate = rejections / total_intents if total_intents > 0 else 0.0
        dlq_rate = dlq / total_intents if total_intents > 0 else 0.0
        retry_rate = retries / total_intents if total_intents > 0 else 0.0

        # Recovery time (max of all derivations)
        rebuild_time = max(metrics.recovery.values()) if metrics.recovery else 0.0

        return PRAReport(
            version="1.0",
            profile=profile,
            timestamp=metrics.timestamp.isoformat(),
            duration_seconds=metrics.duration_seconds,
            latency_p50_ms=p50,
            latency_p95_ms=p95,
            latency_p99_ms=p99,
            throughput_intents_per_sec=intents_rate,
            throughput_facts_per_sec=facts_rate,
            throughput_projections_per_sec=proj_rate,
            backlog_max_lag=max_lag,
            backlog_total_lag=total_lag,
            recovery_rebuild_time_sec=rebuild_time,
            rejection_rate=rejection_rate,
            dlq_rate=dlq_rate,
            retry_rate=retry_rate,
            latency_detail={k: asdict(v) for k, v in metrics.latency.items()},
            throughput_detail={k: asdict(v) for k, v in metrics.throughput.items()},
            backlog_detail={k: asdict(v) for k, v in metrics.backlog.items()},
        )

    def format_json(self, report: PRAReport, indent: int = 2) -> str:
        """Format report as JSON."""
        return report.to_json(indent=indent)

    def format_human(self, report: PRAReport) -> str:
        """Format report as human-readable text."""
        lines = [
            "=" * 60,
            "DAZZLE PRA PERFORMANCE REPORT",
            "=" * 60,
            "",
            f"Profile:    {report.profile}",
            f"Duration:   {report.duration_seconds:.1f}s",
            f"Timestamp:  {report.timestamp}",
            "",
            "LATENCY",
            "-" * 40,
            f"  p50:  {report.latency_p50_ms:>8.2f} ms",
            f"  p95:  {report.latency_p95_ms:>8.2f} ms",
            f"  p99:  {report.latency_p99_ms:>8.2f} ms",
            "",
            "THROUGHPUT",
            "-" * 40,
            f"  INTENTs:     {report.throughput_intents_per_sec:>8.1f} /sec",
            f"  FACTs:       {report.throughput_facts_per_sec:>8.1f} /sec",
            f"  Projections: {report.throughput_projections_per_sec:>8.1f} /sec",
            "",
            "BACKLOG",
            "-" * 40,
            f"  Max lag:   {report.backlog_max_lag:>8}",
            f"  Total lag: {report.backlog_total_lag:>8}",
            "",
            "ERRORS",
            "-" * 40,
            f"  Rejection rate: {report.rejection_rate * 100:>6.2f}%",
            f"  DLQ rate:       {report.dlq_rate * 100:>6.2f}%",
            f"  Retry rate:     {report.retry_rate * 100:>6.2f}%",
            "",
            "RECOVERY",
            "-" * 40,
            f"  Rebuild time: {report.recovery_rebuild_time_sec:>6.2f}s",
            "",
            "=" * 60,
        ]
        return "\n".join(lines)

    def format_markdown(self, report: PRAReport) -> str:
        """Format report as Markdown."""
        lines = [
            "# PRA Performance Report",
            "",
            f"**Profile:** {report.profile}  ",
            f"**Duration:** {report.duration_seconds:.1f}s  ",
            f"**Timestamp:** {report.timestamp}",
            "",
            "## Latency",
            "",
            "| Percentile | Value |",
            "|------------|-------|",
            f"| p50 | {report.latency_p50_ms:.2f} ms |",
            f"| p95 | {report.latency_p95_ms:.2f} ms |",
            f"| p99 | {report.latency_p99_ms:.2f} ms |",
            "",
            "## Throughput",
            "",
            "| Metric | Rate |",
            "|--------|------|",
            f"| INTENTs | {report.throughput_intents_per_sec:.1f} /sec |",
            f"| FACTs | {report.throughput_facts_per_sec:.1f} /sec |",
            f"| Projections | {report.throughput_projections_per_sec:.1f} /sec |",
            "",
            "## Backlog",
            "",
            "| Metric | Value |",
            "|--------|-------|",
            f"| Max lag | {report.backlog_max_lag} |",
            f"| Total lag | {report.backlog_total_lag} |",
            "",
            "## Error Rates",
            "",
            "| Type | Rate |",
            "|------|------|",
            f"| Rejection | {report.rejection_rate * 100:.2f}% |",
            f"| DLQ | {report.dlq_rate * 100:.2f}% |",
            f"| Retry | {report.retry_rate * 100:.2f}% |",
            "",
            "## Recovery",
            "",
            f"**Rebuild time:** {report.recovery_rebuild_time_sec:.2f}s",
            "",
        ]
        return "\n".join(lines)

    def format(self, report: PRAReport, fmt: ReportFormat = ReportFormat.JSON) -> str:
        """
        Format report in specified format.

        Args:
            report: Report to format
            fmt: Output format

        Returns:
            Formatted string
        """
        if fmt == ReportFormat.JSON:
            return self.format_json(report)
        elif fmt == ReportFormat.HUMAN:
            return self.format_human(report)
        elif fmt == ReportFormat.MARKDOWN:
            return self.format_markdown(report)
        else:
            return self.format_json(report)


def compare_reports(baseline: PRAReport, current: PRAReport) -> dict[str, Any]:
    """
    Compare two reports and highlight regressions.

    Args:
        baseline: Baseline report to compare against
        current: Current report

    Returns:
        Dictionary with comparison results and regression flags
    """

    def pct_change(old: float, new: float) -> float:
        if old == 0:
            return 0.0 if new == 0 else float("inf")
        return ((new - old) / old) * 100

    latency_p99_change = pct_change(baseline.latency_p99_ms, current.latency_p99_ms)
    throughput_change = pct_change(
        baseline.throughput_intents_per_sec,
        current.throughput_intents_per_sec,
    )

    # Regression thresholds
    latency_regression = latency_p99_change > 20  # >20% slower
    throughput_regression = throughput_change < -20  # >20% slower

    return {
        "baseline_profile": baseline.profile,
        "current_profile": current.profile,
        "latency_p99": {
            "baseline": baseline.latency_p99_ms,
            "current": current.latency_p99_ms,
            "change_pct": latency_p99_change,
            "regression": latency_regression,
        },
        "throughput_intents": {
            "baseline": baseline.throughput_intents_per_sec,
            "current": current.throughput_intents_per_sec,
            "change_pct": throughput_change,
            "regression": throughput_regression,
        },
        "has_regression": latency_regression or throughput_regression,
    }
