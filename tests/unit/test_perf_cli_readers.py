"""`dazzle perf list | show | report` read a seeded run database."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from dazzle.perf.exporter import _SCHEMA_PATH
from tests.unit.helpers.cli import run_cli

_RUN_ID = "20260519-120000-aaaaaaaa"


@pytest.fixture
def seeded_perf_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    perf_dir = tmp_path / ".dazzle" / "perf"
    perf_dir.mkdir(parents=True)
    conn = sqlite3.connect(perf_dir / f"{_RUN_ID}.db")
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, ended_at, app_name, command_line) "
        f"VALUES ('{_RUN_ID}', '2026-05-19T12:00:00Z', "
        "        '2026-05-19T12:00:05Z', 'examples/simple_task', 'dazzle perf trace')"
    )
    conn.execute(
        "INSERT INTO spans VALUES "
        f"('s1', 't', NULL, '{_RUN_ID}', 'GET /tasks', 'server', "
        " 'ok', 0, 5000000, 5000000, '{}')"
    )
    conn.commit()
    conn.close()
    return perf_dir


@pytest.mark.parametrize(
    ("args", "fragments"),
    [
        pytest.param(["perf", "list"], [_RUN_ID, "examples/simple_task"], id="list_shows_run"),
        pytest.param(["perf", "show", "--run", _RUN_ID], ["GET /tasks"], id="show_named_run"),
        pytest.param(["perf", "show"], ["GET /tasks"], id="show_defaults_to_latest_run"),
        pytest.param(["perf", "report"], ["# Perf report", "GET /tasks"], id="report_markdown"),
    ],
)
def test_perf_reader_output(seeded_perf_dir: Path, args: list[str], fragments: list[str]) -> None:
    out = run_cli(args)
    for fragment in fragments:
        assert fragment in out


def test_report_json_format(seeded_perf_dir: Path) -> None:
    payload = json.loads(run_cli(["perf", "report", "--format", "json"]))
    assert payload["run_id"] == _RUN_ID


def test_report_no_runs_returns_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_cli(["perf", "report"], exit_code=1)
