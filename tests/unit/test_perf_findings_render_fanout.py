"""Render fan-out heuristic — count region.render spans under each request."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dazzle.perf.exporter import _SCHEMA_PATH
from dazzle.perf.findings.extractor import render_fanout


def _seed(db: Path, route: str, region_count: int) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, command_line) "
        "VALUES ('r1', '2026-01-01T00:00:00Z', '')"
    )
    conn.execute(
        "INSERT INTO spans VALUES ('p', 't', NULL, 'r1', ?, 'server', 'ok', 0, 1000, 1000, '{}')",
        (route,),
    )
    for i in range(region_count):
        conn.execute(
            "INSERT INTO spans VALUES "
            "(?, 't', 'p', 'r1', 'region.render', 'internal', 'ok', "
            " ?, ?, 50, '{}')",
            (f"r{i}", i, i + 50),
        )
    conn.commit()
    conn.close()


def test_render_fanout_counts_per_request(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed(db, "GET /dashboard", region_count=18)
    results = render_fanout(db, "r1", top=10)
    assert results[0].route == "GET /dashboard"
    assert results[0].region_renders == 18
