"""Slow-query heuristic tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from dazzle.perf.exporter import _SCHEMA_PATH
from dazzle.perf.findings.extractor import (
    normalise_statement,
    slow_queries,
)


def test_normalise_statement_strips_literals_and_collapses_whitespace() -> None:
    assert (
        normalise_statement("SELECT  * FROM task WHERE id = 'abc-123'")
        == "SELECT * FROM task WHERE id = ?"
    )
    assert (
        normalise_statement("UPDATE t SET x = 42 WHERE y = 1") == "UPDATE t SET x = ? WHERE y = ?"
    )
    # Double-quoted text is a Postgres identifier, not a string literal —
    # it must survive normalisation so the slow-query report keeps the
    # table / column name (#1166).
    assert (
        normalise_statement('SELECT count(*) FROM "task" WHERE "id" = \'x\'')
        == 'SELECT count(*) FROM "task" WHERE "id" = ?'
    )


def _seed_query_spans(db: Path, queries: list[tuple[str, int]]) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, command_line) "
        "VALUES ('r1', '2026-01-01T00:00:00Z', '')"
    )
    for i, (stmt, dur) in enumerate(queries):
        attrs = json.dumps({"db.statement": stmt})
        conn.execute(
            "INSERT INTO spans "
            "(span_id, trace_id, parent_span_id, run_id, name, kind, status, "
            " started_ns, ended_ns, duration_ns, attributes_json) "
            "VALUES (?, 't', NULL, 'r1', ?, 'client', 'ok', ?, ?, ?, ?)",
            (f"s{i}", "psycopg.query", i * 1000, i * 1000 + dur, dur, attrs),
        )
    conn.commit()
    conn.close()


def test_slow_queries_clusters_by_normalised_statement(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed_query_spans(
        db,
        [
            ("SELECT * FROM task WHERE id = '1'", 1_000_000),
            ("SELECT * FROM task WHERE id = '2'", 2_000_000),
            ("SELECT * FROM user WHERE id = '1'", 5_000_000),
        ],
    )
    results = slow_queries(db, "r1", top=10)
    assert results[0].statement == "SELECT * FROM user WHERE id = ?"
    assert results[1].statement == "SELECT * FROM task WHERE id = ?"
    assert results[1].calls == 2
    assert results[1].total_ms == 3.0
