"""MCP handler operations test."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from dazzle.mcp.server.handlers.perf import handle_perf
from dazzle.perf.exporter import _SCHEMA_PATH


@pytest.fixture
def seeded(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    perf_dir = tmp_path / ".dazzle" / "perf"
    perf_dir.mkdir(parents=True)
    db = perf_dir / "20260519-120000-aaaaaaaa.db"
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, ended_at, app_name, command_line) "
        "VALUES ('20260519-120000-aaaaaaaa','2026-05-19T12:00:00Z','2026-05-19T12:00:05Z','app','x')"
    )
    conn.execute(
        "INSERT INTO spans VALUES "
        "('s1','t',NULL,'20260519-120000-aaaaaaaa','GET /x','server','ok',0,1000,1000,'{}')"
    )
    conn.commit()
    conn.close()
    return perf_dir


def test_perf_list_returns_runs(seeded: Path) -> None:
    out = handle_perf({"operation": "list"})
    assert "runs" in out
    assert out["runs"][0]["run_id"] == "20260519-120000-aaaaaaaa"


def test_perf_report_returns_json_findings(seeded: Path) -> None:
    out = handle_perf({"operation": "report"})
    assert "findings" in out
    parsed = json.loads(out["findings"])
    assert parsed["run_id"] == "20260519-120000-aaaaaaaa"


def test_perf_show_returns_span_tree(seeded: Path) -> None:
    out = handle_perf({"operation": "show"})
    assert "spans" in out
    assert any(s["name"] == "GET /x" for s in out["spans"])


def test_perf_unknown_op_errors(seeded: Path) -> None:
    out = handle_perf({"operation": "bogus"})
    assert "error" in out
