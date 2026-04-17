"""Unit tests for ``dazzle sweep examples``."""

from __future__ import annotations

import json
from pathlib import Path

import typer
from typer.testing import CliRunner

from dazzle.cli.sweep import (
    AppResult,
    _parse_lint_output,
    _render_human,
    _render_json,
    sweep_examples_command,
)

# Build a Typer app that wires `dazzle sweep examples` in isolation so
# we don't pull the full CLI module (which imports many unrelated
# heavyweight modules).
_sweep = typer.Typer()
_sweep.command(name="examples")(sweep_examples_command)
app = typer.Typer()
app.add_typer(_sweep, name="sweep")

runner = CliRunner()


class TestParseLintOutput:
    def test_separates_errors_from_warnings(self) -> None:
        text = "\n".join(
            [
                "Validating DSL...",
                "ERROR: bad thing",
                "WARNING: minor thing",
                "Relevant capabilities:",
                "  some capability",
            ]
        )
        errs, warns = _parse_lint_output(text)
        assert errs == ["ERROR: bad thing"]
        assert warns == ["WARNING: minor thing"]

    def test_skips_preview_warnings(self) -> None:
        # "[Preview]" warnings flag unimplemented features; not actionable.
        text = "WARNING: [Preview] 1 webhook(s) defined.\nWARNING: real issue"
        errs, warns = _parse_lint_output(text)
        assert errs == []
        assert warns == ["WARNING: real issue"]

    def test_no_findings_returns_empty_lists(self) -> None:
        errs, warns = _parse_lint_output("All checks passed.\nRelevant capabilities (0):")
        assert errs == []
        assert warns == []


class TestRenderHuman:
    def test_clean_report_has_no_finding_sections(self) -> None:
        results = [
            AppResult(name="clean_app", path=Path("/tmp/clean_app")),
        ]
        coverage = {
            "display_modes": {"percent": 100.0, "covered": 17, "total": 17, "uncovered": []},
        }
        output = _render_human(results, coverage)
        assert "clean_app" in output
        assert "OK" in output
        # No "## clean_app" findings heading when there are no findings
        assert "## clean_app" not in output

    def test_findings_rendered_per_app(self) -> None:
        r = AppResult(
            name="broken_app",
            path=Path("/tmp/broken_app"),
            validate_ok=False,
            validate_output="Error: thing went wrong",
            lint_errors=["ERROR: missing X"],
            lint_warnings=["WARNING: stale Y"],
        )
        output = _render_human([r], {})
        assert "VALIDATE FAILED" in output
        assert "ERROR: missing X" in output
        assert "WARN:  WARNING: stale Y" in output


class TestRenderJson:
    def test_machine_readable_payload(self) -> None:
        r = AppResult(
            name="support_tickets",
            path=Path("/tmp/support_tickets"),
            lint_warnings=["WARNING: minor thing"],
        )
        coverage = {
            "dsl_constructs": {"percent": 100.0, "covered": 23, "total": 23, "uncovered": []},
        }
        payload = json.loads(_render_json([r], coverage))
        assert payload["apps"][0]["name"] == "support_tickets"
        assert payload["apps"][0]["validate_ok"] is True
        assert payload["apps"][0]["lint_warnings"] == ["WARNING: minor thing"]
        assert payload["coverage"]["dsl_constructs"]["percent"] == 100.0


class TestSweepIntegration:
    """End-to-end: actually run against the real examples/ dir."""

    def test_runs_against_real_examples(self) -> None:
        # No args — human report. Depends on real examples/ being clean,
        # which is enforced by the coverage + template-composite gates.
        result = runner.invoke(app, ["sweep", "examples"])
        # Cannot assert exit 0 deterministically (a regression in any
        # example would fail), but we can assert the command runs and
        # produces the header.
        assert "Dazzle example-app sweep" in result.stdout
        # Every example app name appears in the table.
        for name in (
            "contact_manager",
            "fieldtest_hub",
            "ops_dashboard",
            "simple_task",
            "support_tickets",
        ):
            assert name in result.stdout, f"{name} missing from sweep output"

    def test_json_output_is_valid_json(self) -> None:
        result = runner.invoke(app, ["sweep", "examples", "--json"])
        payload = json.loads(result.stdout)
        assert "apps" in payload
        assert "coverage" in payload
        assert len(payload["apps"]) == 5  # every example app
