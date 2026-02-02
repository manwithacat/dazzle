"""
CLI commands for PRA stress testing.

Provides commands to run tests, view reports, and compare results.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import click

from dazzle_back.metrics.reporter import ReportFormat

from .harness import StressHarness
from .scenarios import ScenarioType, list_scenarios


@click.group("pra")
def pra_group() -> None:
    """Performance Reference App commands."""
    pass


@pra_group.command("list")
def list_cmd() -> None:
    """List available test scenarios."""
    scenarios = list_scenarios()

    click.echo("\nAvailable PRA Scenarios:")
    click.echo("=" * 60)

    for s in scenarios:
        duration = s.get("duration_minutes", "varies")
        click.echo(f"\n{s['name']} ({s['type']})")
        click.echo(f"  {s['description']}")
        click.echo(f"  Duration: {duration} minutes")

    click.echo()


@pra_group.command("run")
@click.argument("scenario", type=str, default="quick")
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file for results (JSON)",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["json", "human", "markdown"]),
    default="human",
    help="Report format",
)
@click.option(
    "--compare",
    "-c",
    type=click.Path(exists=True),
    help="Compare against previous results",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show verbose progress",
)
def run_cmd(
    scenario: str,
    output: str | None,
    format: str,
    compare: str | None,
    verbose: bool,
) -> None:
    """Run a PRA stress test scenario.

    SCENARIO is the scenario name (default: quick).
    Use 'pra list' to see available scenarios.

    Examples:

        dazzle pra run quick

        dazzle pra run standard -o results.json

        dazzle pra run full --format markdown

        dazzle pra run standard -c baseline.json
    """
    try:
        scenario_type = ScenarioType(scenario)
    except ValueError:
        click.echo(f"Unknown scenario: {scenario}", err=True)
        click.echo("Use 'dazzle pra list' to see available scenarios", err=True)
        sys.exit(1)

    click.echo(f"\nRunning PRA scenario: {scenario}")
    click.echo("=" * 60)

    # Progress callback
    def progress_callback(phase: str, progress: float, rate: float) -> None:
        if verbose:
            click.echo(f"  [{phase}] {progress:.1f}% @ {rate:.0f} events/sec")

    # Run the test
    harness = StressHarness()

    result = asyncio.run(
        harness.run_scenario(scenario_type, progress_callback if verbose else None)
    )

    # Generate report
    report_format = {
        "json": ReportFormat.JSON,
        "human": ReportFormat.HUMAN,
        "markdown": ReportFormat.MARKDOWN,
    }[format]

    report = harness.generate_report(result, report_format)

    # Output
    if output:
        output_path = Path(output)
        output_path.write_text(json.dumps(result.to_dict(), indent=2, default=str))
        click.echo(f"\nResults saved to: {output_path}")

    click.echo("\n" + report)

    # Compare if requested
    if compare:
        compare_path = Path(compare)
        baseline = json.loads(compare_path.read_text())
        comparison = compare_results(result.to_dict(), baseline)
        click.echo("\n" + format_comparison(comparison))

    # Exit code based on criteria
    if result.criteria_passed:
        click.echo("\n✅ All criteria passed")
        sys.exit(0)
    else:
        click.echo("\n❌ Some criteria failed")
        sys.exit(1)


@pra_group.command("compare")
@click.argument("file1", type=click.Path(exists=True))
@click.argument("file2", type=click.Path(exists=True))
@click.option(
    "--format",
    "-f",
    type=click.Choice(["human", "markdown", "json"]),
    default="human",
    help="Output format",
)
def compare_cmd(file1: str, file2: str, format: str) -> None:
    """Compare two PRA test results.

    FILE1 is the baseline (older) result.
    FILE2 is the current result.

    Example:

        dazzle pra compare baseline.json current.json
    """
    baseline = json.loads(Path(file1).read_text())
    current = json.loads(Path(file2).read_text())

    comparison = compare_results(current, baseline)

    if format == "json":
        click.echo(json.dumps(comparison, indent=2))
    elif format == "markdown":
        click.echo(format_comparison_markdown(comparison))
    else:
        click.echo(format_comparison(comparison))


@pra_group.command("report")
@click.argument("file", type=click.Path(exists=True))
@click.option(
    "--format",
    "-f",
    type=click.Choice(["human", "markdown", "json"]),
    default="human",
    help="Output format",
)
def report_cmd(file: str, format: str) -> None:
    """Generate a report from saved test results.

    FILE is a JSON results file from 'pra run -o'.

    Example:

        dazzle pra report results.json --format markdown
    """
    data = json.loads(Path(file).read_text())

    if format == "json":
        click.echo(json.dumps(data, indent=2))
    elif format == "markdown":
        click.echo(format_result_markdown(data))
    else:
        click.echo(format_result_human(data))


def compare_results(
    current: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    """
    Compare two test results.

    Returns comparison dict with deltas and regressions.
    """
    comparison: dict[str, Any] = {
        "current_test_id": current.get("test_id"),
        "baseline_test_id": baseline.get("test_id"),
        "metrics": {},
        "regressions": [],
        "improvements": [],
    }

    # Compare latency
    current_latency = current.get("metrics", {}).get("latency", {})
    baseline_latency = baseline.get("metrics", {}).get("latency", {})

    for key in ["p50", "p95", "p99"]:
        current_val = _get_latency_value(current_latency, key)
        baseline_val = _get_latency_value(baseline_latency, key)

        if current_val is not None and baseline_val is not None and baseline_val > 0:
            delta = current_val - baseline_val
            delta_pct = (delta / baseline_val) * 100

            comparison["metrics"][f"latency_{key}"] = {
                "current": current_val,
                "baseline": baseline_val,
                "delta": delta,
                "delta_pct": delta_pct,
            }

            # Regression if latency increased by more than 10%
            if delta_pct > 10:
                comparison["regressions"].append(f"latency_{key} increased by {delta_pct:.1f}%")
            elif delta_pct < -10:
                comparison["improvements"].append(
                    f"latency_{key} decreased by {abs(delta_pct):.1f}%"
                )

    # Compare throughput
    current_throughput = current.get("metrics", {}).get("throughput", {})
    baseline_throughput = baseline.get("metrics", {}).get("throughput", {})

    total_current = sum(
        t.get("total_count", 0) for t in current_throughput.values() if isinstance(t, dict)
    )
    total_baseline = sum(
        t.get("total_count", 0) for t in baseline_throughput.values() if isinstance(t, dict)
    )

    if total_baseline > 0:
        delta = total_current - total_baseline
        delta_pct = (delta / total_baseline) * 100

        comparison["metrics"]["total_throughput"] = {
            "current": total_current,
            "baseline": total_baseline,
            "delta": delta,
            "delta_pct": delta_pct,
        }

        if delta_pct < -10:
            comparison["regressions"].append(f"throughput decreased by {abs(delta_pct):.1f}%")
        elif delta_pct > 10:
            comparison["improvements"].append(f"throughput increased by {delta_pct:.1f}%")

    # Compare error rates
    current_errors = current.get("metrics", {}).get("error_counts", {})
    baseline_errors = baseline.get("metrics", {}).get("error_counts", {})

    if total_current > 0 and total_baseline > 0:
        current_error_total = (
            sum(current_errors.values()) if isinstance(current_errors, dict) else 0
        )
        baseline_error_total = (
            sum(baseline_errors.values()) if isinstance(baseline_errors, dict) else 0
        )

        current_rate = current_error_total / total_current
        baseline_rate = baseline_error_total / total_baseline if total_baseline > 0 else 0

        comparison["metrics"]["error_rate"] = {
            "current": current_rate,
            "baseline": baseline_rate,
            "delta": current_rate - baseline_rate,
        }

        if current_rate > baseline_rate * 1.5 and current_rate > 0.01:
            comparison["regressions"].append(
                f"error rate increased from {baseline_rate:.2%} to {current_rate:.2%}"
            )

    # Overall assessment
    comparison["has_regressions"] = len(comparison["regressions"]) > 0
    comparison["has_improvements"] = len(comparison["improvements"]) > 0

    return comparison


def _get_latency_value(latency_data: dict[str, Any], key: str) -> float | None:
    """Extract latency value from nested structure."""
    if key in latency_data:
        val = latency_data[key]
        if isinstance(val, int | float):
            return float(val)
        if isinstance(val, dict):
            return val.get("value") or val.get(key)
    # Try nested structure
    for _, data in latency_data.items():
        if isinstance(data, dict) and key in data:
            return float(data[key])
    return None


def format_comparison(comparison: dict[str, Any]) -> str:
    """Format comparison as human-readable text."""
    lines = [
        "Performance Comparison",
        "=" * 50,
        f"Baseline: {comparison['baseline_test_id']}",
        f"Current:  {comparison['current_test_id']}",
        "",
        "Metrics:",
        "-" * 20,
    ]

    for name, data in comparison["metrics"].items():
        delta = data.get("delta", 0)
        delta_pct = data.get("delta_pct", 0)
        sign = "+" if delta > 0 else ""
        lines.append(
            f"  {name}: {data['current']:.2f} (was {data['baseline']:.2f}, {sign}{delta_pct:.1f}%)"
        )

    if comparison["regressions"]:
        lines.extend(["", "⚠️  Regressions:", "-" * 20])
        for r in comparison["regressions"]:
            lines.append(f"  - {r}")

    if comparison["improvements"]:
        lines.extend(["", "✅ Improvements:", "-" * 20])
        for i in comparison["improvements"]:
            lines.append(f"  - {i}")

    if not comparison["regressions"] and not comparison["improvements"]:
        lines.extend(["", "No significant changes detected."])

    return "\n".join(lines)


def format_comparison_markdown(comparison: dict[str, Any]) -> str:
    """Format comparison as markdown."""
    lines = [
        "# Performance Comparison",
        "",
        "| | Baseline | Current | Delta |",
        "|---|---|---|---|",
    ]

    for name, data in comparison["metrics"].items():
        delta = data.get("delta", 0)
        delta_pct = data.get("delta_pct", 0)
        sign = "+" if delta > 0 else ""
        lines.append(
            f"| {name} | {data['baseline']:.2f} | {data['current']:.2f} | {sign}{delta_pct:.1f}% |"
        )

    if comparison["regressions"]:
        lines.extend(["", "## ⚠️ Regressions", ""])
        for r in comparison["regressions"]:
            lines.append(f"- {r}")

    if comparison["improvements"]:
        lines.extend(["", "## ✅ Improvements", ""])
        for i in comparison["improvements"]:
            lines.append(f"- {i}")

    return "\n".join(lines)


def format_result_human(data: dict[str, Any]) -> str:
    """Format result as human-readable text."""
    lines = [
        f"PRA Test Report: {data.get('scenario_name', 'unknown')}",
        "=" * 50,
        f"Test ID: {data.get('test_id', 'unknown')}",
        f"Status: {data.get('status', 'unknown').upper()}",
        f"Duration: {data.get('duration_seconds', 0):.1f}s",
    ]

    if data.get("generator_stats"):
        gs = data["generator_stats"]
        lines.extend(
            [
                "",
                "Generator Stats:",
                "-" * 20,
                f"  Total generated: {gs.get('total_generated', 0)}",
                f"  Intents: {gs.get('intents_generated', 0)}",
                f"  Facts: {gs.get('facts_generated', 0)}",
                f"  Errors: {gs.get('errors', 0)}",
            ]
        )

    if data.get("criteria_results"):
        lines.extend(["", "Criteria:", "-" * 20])
        for cr in data["criteria_results"]:
            status = "PASS" if cr.get("passed") else "FAIL"
            lines.append(
                f"  [{status}] {cr['name']}: {cr['actual']:.2f} (threshold: {cr['threshold']})"
            )

    passed = data.get("criteria_passed", False)
    lines.extend(
        [
            "",
            "=" * 50,
            f"OVERALL: {'PASSED' if passed else 'FAILED'}",
        ]
    )

    return "\n".join(lines)


def format_result_markdown(data: dict[str, Any]) -> str:
    """Format result as markdown."""
    status_emoji = "✅" if data.get("criteria_passed") else "❌"

    lines = [
        f"# PRA Test Report: {data.get('scenario_name', 'unknown')}",
        "",
        f"**Status:** {status_emoji} {data.get('status', 'unknown').upper()}",
        f"**Test ID:** `{data.get('test_id', 'unknown')}`",
        f"**Duration:** {data.get('duration_seconds', 0):.1f}s",
    ]

    if data.get("generator_stats"):
        gs = data["generator_stats"]
        lines.extend(
            [
                "",
                "## Generator Stats",
                "",
                "| Metric | Value |",
                "|--------|-------|",
                f"| Total generated | {gs.get('total_generated', 0)} |",
                f"| Intents | {gs.get('intents_generated', 0)} |",
                f"| Facts | {gs.get('facts_generated', 0)} |",
                f"| Errors | {gs.get('errors', 0)} |",
            ]
        )

    if data.get("criteria_results"):
        lines.extend(
            [
                "",
                "## Success Criteria",
                "",
                "| Criterion | Threshold | Actual | Status |",
                "|-----------|-----------|--------|--------|",
            ]
        )
        for cr in data["criteria_results"]:
            status = "✅ Pass" if cr.get("passed") else "❌ Fail"
            lines.append(f"| {cr['name']} | {cr['threshold']} | {cr['actual']:.2f} | {status} |")

    return "\n".join(lines)


# ============================================================================
# TigerBeetle Commands (v0.5.0)
# ============================================================================


@pra_group.group("tb")
def tb_group() -> None:
    """TigerBeetle stress testing commands."""
    pass


@tb_group.command("list")
def tb_list_cmd() -> None:
    """List available TigerBeetle test scenarios."""
    try:
        from .tigerbeetle_scenarios import list_tb_scenarios
    except ImportError:
        click.echo(
            "TigerBeetle not installed. Install with: pip install dazzle[tigerbeetle]", err=True
        )
        sys.exit(1)

    scenarios = list_tb_scenarios()

    click.echo("\nAvailable TigerBeetle Scenarios:")
    click.echo("=" * 60)

    for s in scenarios:
        duration = s.get("duration_seconds", "varies")
        click.echo(f"\n{s['name']} ({s['type']})")
        click.echo(f"  {s['description']}")
        click.echo(f"  Duration: {duration} seconds")

    click.echo()


@tb_group.command("run")
@click.argument("scenario", type=str, default="tb_quick")
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    help="Output file for results (JSON)",
)
@click.option(
    "--format",
    "-f",
    type=click.Choice(["json", "human", "markdown"]),
    default="human",
    help="Report format",
)
@click.option(
    "--address",
    "-a",
    type=str,
    default="127.0.0.1:3000",
    help="TigerBeetle server address",
)
@click.option(
    "--cluster-id",
    "-c",
    type=int,
    default=0,
    help="TigerBeetle cluster ID",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Show verbose progress",
)
def tb_run_cmd(
    scenario: str,
    output: str | None,
    format: str,
    address: str,
    cluster_id: int,
    verbose: bool,
) -> None:
    """Run a TigerBeetle stress test scenario.

    SCENARIO is the scenario name (default: tb_quick).
    Use 'pra tb list' to see available scenarios.

    Examples:

        dazzle pra tb run tb_quick

        dazzle pra tb run tb_steady -o results.json

        dazzle pra tb run tb_burst --format markdown

        dazzle pra tb run tb_full -a 192.168.1.10:3000
    """
    try:
        from .tigerbeetle_client import TigerBeetleConfig
        from .tigerbeetle_harness import TigerBeetleHarness
        from .tigerbeetle_scenarios import TBScenarioType
    except ImportError:
        click.echo(
            "TigerBeetle not installed. Install with: pip install dazzle[tigerbeetle]", err=True
        )
        sys.exit(1)

    try:
        scenario_type = TBScenarioType(scenario)
    except ValueError:
        click.echo(f"Unknown scenario: {scenario}", err=True)
        click.echo("Use 'dazzle pra tb list' to see available scenarios", err=True)
        sys.exit(1)

    click.echo(f"\nRunning TigerBeetle scenario: {scenario}")
    click.echo(f"Connecting to: {address} (cluster {cluster_id})")
    click.echo("=" * 60)

    # Configure connection
    tb_config = TigerBeetleConfig(
        cluster_id=cluster_id,
        addresses=[address],
    )

    # Progress callback
    def progress_callback(
        phase: str,
        progress: float,
        rate: float,
        accounts: int,
        transfers: int,
    ) -> None:
        if verbose:
            click.echo(
                f"  [{phase}] {progress:.1f}% @ {rate:.0f}/s "
                f"(accounts: {accounts}, transfers: {transfers})"
            )

    # Run the test
    harness = TigerBeetleHarness(tb_config)

    result = asyncio.run(
        harness.run_scenario(scenario_type, progress_callback if verbose else None)
    )

    # Generate report
    report_format = {
        "json": ReportFormat.JSON,
        "human": ReportFormat.HUMAN,
        "markdown": ReportFormat.MARKDOWN,
    }[format]

    report = harness.generate_report(result, report_format)

    # Output
    if output:
        output_path = Path(output)
        output_path.write_text(json.dumps(result.to_dict(), indent=2, default=str))
        click.echo(f"\nResults saved to: {output_path}")

    click.echo("\n" + report)

    # Exit code based on status and criteria
    if result.status.value == "skipped":
        click.echo("\n⏭️  Test skipped (TigerBeetle not available)")
        sys.exit(2)
    elif result.criteria_passed:
        click.echo("\n✅ All criteria passed")
        sys.exit(0)
    else:
        click.echo("\n❌ Some criteria failed")
        sys.exit(1)


@tb_group.command("check")
@click.option(
    "--address",
    "-a",
    type=str,
    default="127.0.0.1:3000",
    help="TigerBeetle server address",
)
@click.option(
    "--cluster-id",
    "-c",
    type=int,
    default=0,
    help="TigerBeetle cluster ID",
)
def tb_check_cmd(address: str, cluster_id: int) -> None:
    """Check if TigerBeetle is available.

    Example:

        dazzle pra tb check

        dazzle pra tb check -a 192.168.1.10:3000
    """
    try:
        from .tigerbeetle_client import TigerBeetleConfig, check_tigerbeetle_available
    except ImportError:
        click.echo("❌ TigerBeetle client not installed")
        click.echo("   Install with: pip install dazzle[tigerbeetle]")
        sys.exit(1)

    click.echo(f"Checking TigerBeetle at {address} (cluster {cluster_id})...")

    tb_config = TigerBeetleConfig(
        cluster_id=cluster_id,
        addresses=[address],
    )

    available = asyncio.run(check_tigerbeetle_available(tb_config))

    if available:
        click.echo("✅ TigerBeetle is available and responding")
        sys.exit(0)
    else:
        click.echo("❌ TigerBeetle is not available")
        click.echo("   Make sure the server is running and accessible")
        sys.exit(1)


# Export for registration with main CLI
__all__ = ["pra_group"]
