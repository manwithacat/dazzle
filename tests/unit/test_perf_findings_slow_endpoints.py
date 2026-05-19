"""Slow-endpoint heuristic tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dazzle.perf.exporter import _SCHEMA_PATH
from dazzle.perf.findings.extractor import slow_endpoints


def _seed_endpoint_spans(db: Path, calls: list[tuple[str, int]]) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, command_line) "
        "VALUES ('r1', '2026-01-01T00:00:00Z', '')"
    )
    for i, (name, duration_ns) in enumerate(calls):
        conn.execute(
            "INSERT INTO spans "
            "(span_id, trace_id, parent_span_id, run_id, name, kind, status, "
            " started_ns, ended_ns, duration_ns, attributes_json) "
            "VALUES (?, 't', NULL, 'r1', ?, 'server', 'ok', ?, ?, ?, '{}')",
            (f"s{i}", name, i * 1000, i * 1000 + duration_ns, duration_ns),
        )
    conn.commit()
    conn.close()


def test_slow_endpoints_ranks_by_total(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed_endpoint_spans(
        db,
        [
            ("GET /tasks", 1_000_000),  # 1ms
            ("GET /tasks", 2_000_000),  # 2ms
            ("GET /users", 5_000_000),  # 5ms
        ],
    )
    results = slow_endpoints(db, "r1", top=10)
    assert results[0].route == "GET /users"
    assert results[0].total_ms == 5.0
    assert results[1].route == "GET /tasks"
    assert results[1].calls == 2
    assert results[1].total_ms == 3.0


def test_slow_endpoints_only_server_kind(tmp_path: Path) -> None:
    """``kind="internal"`` spans are not endpoints — must be filtered out."""
    db = tmp_path / "run.db"
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, command_line) "
        "VALUES ('r1', '2026-01-01T00:00:00Z', '')"
    )
    conn.execute(
        "INSERT INTO spans VALUES "
        "('s1','t',NULL,'r1','internal_op','internal','ok',0,1000,1000,'{}')"
    )
    conn.commit()
    conn.close()

    assert slow_endpoints(db, "r1", top=10) == []


def test_slow_endpoints_top_n_caps_results(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed_endpoint_spans(
        db,
        [(f"GET /r{i}", 1000) for i in range(20)],
    )
    results = slow_endpoints(db, "r1", top=5)
    assert len(results) == 5
