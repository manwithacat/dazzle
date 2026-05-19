"""dazzle perf report — Markdown + JSON output paths."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dazzle.cli import app
from dazzle.perf.exporter import _SCHEMA_PATH


@pytest.fixture
def seeded_perf_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    perf_dir = tmp_path / ".dazzle" / "perf"
    perf_dir.mkdir(parents=True)
    db = perf_dir / "20260519-120000-aaaaaaaa.db"
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, ended_at, app_name, command_line) "
        "VALUES ('20260519-120000-aaaaaaaa','2026-05-19T12:00:00Z',"
        " '2026-05-19T12:00:05Z','examples/simple_task','dazzle perf trace')"
    )
    conn.execute(
        "INSERT INTO spans VALUES "
        "('s1','t',NULL,'20260519-120000-aaaaaaaa','GET /tasks','server','ok',"
        " 0, 5000000, 5000000, '{}')"
    )
    conn.commit()
    conn.close()
    return perf_dir


def test_report_default_is_markdown(seeded_perf_dir: Path) -> None:
    result = CliRunner().invoke(app, ["perf", "report"])
    assert result.exit_code == 0
    assert "# Perf report" in result.stdout
    assert "GET /tasks" in result.stdout


def test_report_json_format(seeded_perf_dir: Path) -> None:
    result = CliRunner().invoke(app, ["perf", "report", "--format", "json"])
    assert result.exit_code == 0
    assert '"run_id"' in result.stdout


def test_report_no_runs_returns_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["perf", "report"])
    assert result.exit_code != 0
