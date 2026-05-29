"""#1295 — `dazzle e2e run-viewport` exit-code contract.

The orthogonal viewport gate can only become a blocking CI check if the CLI
exits non-zero on real failures/errors. It must NOT fail on skipped-only runs
(persona-unreachable pages are skips, not regressions).
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from dazzle.cli.e2e import e2e_app

runner = CliRunner()


def _patch(monkeypatch, payload: dict) -> None:
    import dazzle.cli.common as common
    import dazzle.mcp.server.handlers.viewport_testing as vt

    monkeypatch.setattr(common, "resolve_project", lambda manifest: Path("."))
    monkeypatch.setattr(vt, "run_viewport_tests_impl", lambda **kw: json.dumps(payload))


def test_exit_zero_on_clean_run(monkeypatch) -> None:
    _patch(
        monkeypatch,
        {
            "total_passed": 16,
            "total_assertions": 16,
            "total_failed": 0,
            "total_skipped": 14,
            "error": None,
            "reports": [],
        },
    )
    res = runner.invoke(e2e_app, ["run-viewport", "--json"])
    assert res.exit_code == 0, res.output


def test_exit_nonzero_on_failures(monkeypatch) -> None:
    _patch(
        monkeypatch,
        {
            "total_passed": 1,
            "total_assertions": 3,
            "total_failed": 2,
            "total_skipped": 0,
            "error": None,
            "reports": [],
        },
    )
    res = runner.invoke(e2e_app, ["run-viewport", "--json"])
    assert res.exit_code == 1


def test_exit_nonzero_on_error(monkeypatch) -> None:
    # The loud guard: persona run evaluated nothing (all skipped) → error set.
    _patch(
        monkeypatch,
        {
            "total_passed": 0,
            "total_assertions": 0,
            "total_failed": 0,
            "total_skipped": 6,
            "error": "0 of 6 viewport assertions evaluated — every page was skipped.",
            "reports": [],
        },
    )
    res = runner.invoke(e2e_app, ["run-viewport", "--json"])
    assert res.exit_code == 1


def test_exit_zero_on_skipped_only_with_passes(monkeypatch) -> None:
    # Passes + skips, no failures, no error → success. Skips aren't failures.
    _patch(
        monkeypatch,
        {
            "total_passed": 5,
            "total_assertions": 5,
            "total_failed": 0,
            "total_skipped": 9,
            "error": None,
            "reports": [],
        },
    )
    res = runner.invoke(e2e_app, ["run-viewport", "--json"])
    assert res.exit_code == 0, res.output
