"""CLI smoke tests for `dazzle perf list` + `dazzle perf show`."""

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
        "VALUES ('20260519-120000-aaaaaaaa', '2026-05-19T12:00:00Z', "
        "        '2026-05-19T12:00:05Z', 'examples/simple_task', 'dazzle perf trace')"
    )
    conn.execute(
        "INSERT INTO spans VALUES "
        "('s1', 't', NULL, '20260519-120000-aaaaaaaa', 'GET /tasks', 'server', "
        " 'ok', 0, 1000, 1000, '{}')"
    )
    conn.commit()
    conn.close()
    return perf_dir


def test_perf_list_shows_run(seeded_perf_dir: Path) -> None:
    result = CliRunner().invoke(app, ["perf", "list"])
    assert result.exit_code == 0
    assert "20260519-120000-aaaaaaaa" in result.stdout
    assert "examples/simple_task" in result.stdout


def test_perf_show_dumps_span_tree(seeded_perf_dir: Path) -> None:
    result = CliRunner().invoke(app, ["perf", "show", "--run", "20260519-120000-aaaaaaaa"])
    assert result.exit_code == 0
    assert "GET /tasks" in result.stdout


def test_perf_show_with_no_run_picks_latest(seeded_perf_dir: Path) -> None:
    result = CliRunner().invoke(app, ["perf", "show"])
    assert result.exit_code == 0
    assert "GET /tasks" in result.stdout
