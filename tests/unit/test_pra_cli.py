"""Tests for PRA CLI and reporting functions."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from dazzle_back.pra.cli import (
    compare_results,
    format_comparison,
    format_comparison_markdown,
    format_result_human,
    format_result_markdown,
    pra_group,
)


class TestCompareResults:
    """Tests for result comparison."""

    def test_compare_latency_improvement(self) -> None:
        """Test detecting latency improvement."""
        baseline = {
            "test_id": "baseline",
            "metrics": {
                "latency": {"p95": 500},
                "throughput": {"events": {"total_count": 1000}},
            },
        }

        current = {
            "test_id": "current",
            "metrics": {
                "latency": {"p95": 300},
                "throughput": {"events": {"total_count": 1000}},
            },
        }

        comparison = compare_results(current, baseline)

        assert "latency_p95" in comparison["metrics"]
        assert comparison["metrics"]["latency_p95"]["delta"] == -200
        assert comparison["metrics"]["latency_p95"]["delta_pct"] == -40
        assert len(comparison["improvements"]) > 0
        assert "latency_p95" in comparison["improvements"][0]

    def test_compare_latency_regression(self) -> None:
        """Test detecting latency regression."""
        baseline = {
            "test_id": "baseline",
            "metrics": {
                "latency": {"p95": 300},
                "throughput": {"events": {"total_count": 1000}},
            },
        }

        current = {
            "test_id": "current",
            "metrics": {
                "latency": {"p95": 500},
                "throughput": {"events": {"total_count": 1000}},
            },
        }

        comparison = compare_results(current, baseline)

        assert comparison["has_regressions"]
        assert "latency_p95 increased" in comparison["regressions"][0]

    def test_compare_throughput_regression(self) -> None:
        """Test detecting throughput regression."""
        baseline = {
            "test_id": "baseline",
            "metrics": {
                "latency": {},
                "throughput": {"events": {"total_count": 10000}},
            },
        }

        current = {
            "test_id": "current",
            "metrics": {
                "latency": {},
                "throughput": {"events": {"total_count": 5000}},
            },
        }

        comparison = compare_results(current, baseline)

        assert "total_throughput" in comparison["metrics"]
        assert comparison["metrics"]["total_throughput"]["delta_pct"] == -50
        assert comparison["has_regressions"]

    def test_compare_error_rate_increase(self) -> None:
        """Test detecting error rate increase."""
        baseline = {
            "test_id": "baseline",
            "metrics": {
                "latency": {},
                "throughput": {"events": {"total_count": 1000}},
                "error_counts": {"rejection": 10},
            },
        }

        current = {
            "test_id": "current",
            "metrics": {
                "latency": {},
                "throughput": {"events": {"total_count": 1000}},
                "error_counts": {"rejection": 100},
            },
        }

        comparison = compare_results(current, baseline)

        assert "error_rate" in comparison["metrics"]
        assert comparison["metrics"]["error_rate"]["current"] == 0.1
        assert comparison["metrics"]["error_rate"]["baseline"] == 0.01

    def test_compare_no_changes(self) -> None:
        """Test when no significant changes."""
        baseline = {
            "test_id": "baseline",
            "metrics": {
                "latency": {"p95": 100},
                "throughput": {"events": {"total_count": 1000}},
            },
        }

        current = {
            "test_id": "current",
            "metrics": {
                "latency": {"p95": 105},  # Only 5% increase
                "throughput": {"events": {"total_count": 1000}},
            },
        }

        comparison = compare_results(current, baseline)

        assert not comparison["has_regressions"]
        assert not comparison["has_improvements"]


class TestFormatFunctions:
    """Tests for formatting functions."""

    def test_format_comparison_human(self) -> None:
        """Test human-readable comparison format."""
        comparison = {
            "current_test_id": "abc123",
            "baseline_test_id": "def456",
            "metrics": {
                "latency_p95": {
                    "current": 200,
                    "baseline": 300,
                    "delta": -100,
                    "delta_pct": -33.3,
                }
            },
            "regressions": [],
            "improvements": ["latency_p95 decreased by 33.3%"],
        }

        output = format_comparison(comparison)

        assert "Performance Comparison" in output
        assert "abc123" in output
        assert "def456" in output
        assert "latency_p95" in output
        assert "Improvements" in output

    def test_format_comparison_markdown(self) -> None:
        """Test markdown comparison format."""
        comparison = {
            "current_test_id": "abc123",
            "baseline_test_id": "def456",
            "metrics": {
                "latency_p95": {
                    "current": 500,
                    "baseline": 300,
                    "delta": 200,
                    "delta_pct": 66.7,
                }
            },
            "regressions": ["latency_p95 increased by 66.7%"],
            "improvements": [],
        }

        output = format_comparison_markdown(comparison)

        assert "# Performance Comparison" in output
        assert "| latency_p95" in output
        assert "## ⚠️ Regressions" in output

    def test_format_result_human(self) -> None:
        """Test human-readable result format."""
        data = {
            "test_id": "test123",
            "scenario_name": "quick",
            "status": "completed",
            "duration_seconds": 60.5,
            "generator_stats": {
                "total_generated": 1000,
                "intents_generated": 500,
                "facts_generated": 300,
                "errors": 5,
            },
            "criteria_results": [
                {"name": "p95_latency", "threshold": 500, "actual": 300, "passed": True}
            ],
            "criteria_passed": True,
        }

        output = format_result_human(data)

        assert "test123" in output
        assert "quick" in output
        assert "COMPLETED" in output
        assert "60.5s" in output
        assert "Total generated: 1000" in output
        assert "PASS" in output
        assert "PASSED" in output

    def test_format_result_markdown(self) -> None:
        """Test markdown result format."""
        data = {
            "test_id": "test456",
            "scenario_name": "standard",
            "status": "completed",
            "duration_seconds": 300,
            "generator_stats": {
                "total_generated": 10000,
                "intents_generated": 5000,
                "facts_generated": 3000,
                "errors": 10,
            },
            "criteria_results": [
                {"name": "error_rate", "threshold": 0.01, "actual": 0.02, "passed": False}
            ],
            "criteria_passed": False,
        }

        output = format_result_markdown(data)

        assert "# PRA Test Report" in output
        assert "test456" in output
        assert "## Generator Stats" in output
        assert "## Success Criteria" in output
        assert "❌" in output


class TestPRACLI:
    """Tests for PRA CLI commands."""

    def test_pra_list(self) -> None:
        """Test pra list command."""
        runner = CliRunner()
        result = runner.invoke(pra_group, ["list"])

        assert result.exit_code == 0
        assert "Available PRA Scenarios" in result.output
        assert "quick" in result.output
        assert "standard" in result.output

    def test_pra_run_unknown_scenario(self) -> None:
        """Test pra run with unknown scenario."""
        runner = CliRunner()
        result = runner.invoke(pra_group, ["run", "nonexistent"])

        assert result.exit_code == 1
        assert "Unknown scenario" in result.output

    def test_pra_compare_files(self, tmp_path: Path) -> None:
        """Test pra compare command."""
        baseline = {
            "test_id": "baseline",
            "metrics": {
                "latency": {"p95": 500},
                "throughput": {"events": {"total_count": 1000}},
            },
        }

        current = {
            "test_id": "current",
            "metrics": {
                "latency": {"p95": 300},
                "throughput": {"events": {"total_count": 1000}},
            },
        }

        baseline_file = tmp_path / "baseline.json"
        current_file = tmp_path / "current.json"

        baseline_file.write_text(json.dumps(baseline))
        current_file.write_text(json.dumps(current))

        runner = CliRunner()
        result = runner.invoke(pra_group, ["compare", str(baseline_file), str(current_file)])

        assert result.exit_code == 0
        assert "Performance Comparison" in result.output

    def test_pra_report_from_file(self, tmp_path: Path) -> None:
        """Test pra report command."""
        data = {
            "test_id": "test123",
            "scenario_name": "quick",
            "status": "completed",
            "duration_seconds": 60,
            "generator_stats": {
                "total_generated": 1000,
                "intents_generated": 500,
                "facts_generated": 300,
                "errors": 0,
            },
            "criteria_results": [],
            "criteria_passed": True,
        }

        file_path = tmp_path / "results.json"
        file_path.write_text(json.dumps(data))

        runner = CliRunner()
        result = runner.invoke(pra_group, ["report", str(file_path)])

        assert result.exit_code == 0
        assert "test123" in result.output

    def test_pra_report_markdown_format(self, tmp_path: Path) -> None:
        """Test pra report with markdown format."""
        data = {
            "test_id": "test789",
            "scenario_name": "burst",
            "status": "completed",
            "duration_seconds": 120,
            "generator_stats": {},
            "criteria_results": [],
            "criteria_passed": True,
        }

        file_path = tmp_path / "results.json"
        file_path.write_text(json.dumps(data))

        runner = CliRunner()
        result = runner.invoke(pra_group, ["report", str(file_path), "--format", "markdown"])

        assert result.exit_code == 0
        assert "# PRA Test Report" in result.output
