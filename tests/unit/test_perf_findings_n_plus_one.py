"""N+1 detection tests — at least 3 identical normalised child queries
under one parent span flag the parent."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from dazzle.perf.exporter import _SCHEMA_PATH
from dazzle.perf.findings.extractor import detect_n_plus_one


def _seed(db: Path, parent_name: str, child_statements: list[str]) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, command_line) "
        "VALUES ('r1', '2026-01-01T00:00:00Z', '')"
    )
    conn.execute(
        "INSERT INTO spans VALUES ('p', 't', NULL, 'r1', ?, 'server', 'ok', 0, 100, 100, '{}')",
        (parent_name,),
    )
    for i, stmt in enumerate(child_statements):
        attrs = json.dumps({"db.statement": stmt})
        conn.execute(
            "INSERT INTO spans VALUES "
            "(?, 't', 'p', 'r1', 'psycopg.query', 'client', 'ok', "
            " ?, ?, ?, ?)",
            (f"c{i}", i, i + 10, 10, attrs),
        )
    conn.commit()
    conn.close()


def test_three_identical_queries_flagged(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed(
        db,
        "GET /tasks",
        [
            "SELECT FROM user WHERE id = '1'",
            "SELECT FROM user WHERE id = '2'",
            "SELECT FROM user WHERE id = '3'",
        ],
    )
    findings = detect_n_plus_one(db, "r1", threshold=3)
    assert len(findings) == 1
    assert findings[0].parent_span == "GET /tasks"
    assert findings[0].repetitions == 3


def test_below_threshold_ignored(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed(
        db,
        "GET /tasks",
        [
            "SELECT FROM user WHERE id = '1'",
            "SELECT FROM user WHERE id = '2'",
        ],
    )
    assert detect_n_plus_one(db, "r1", threshold=3) == []


def test_distinct_statements_not_clustered(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed(
        db,
        "GET /tasks",
        [
            "SELECT FROM user WHERE id = '1'",
            "SELECT FROM tag WHERE id = '1'",
            "SELECT FROM role WHERE id = '1'",
        ],
    )
    assert detect_n_plus_one(db, "r1", threshold=3) == []
