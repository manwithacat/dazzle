"""Exception finding tests — surface spans with status=error."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from dazzle.perf.exporter import _SCHEMA_PATH
from dazzle.perf.findings.extractor import exceptions_from_errors


def _seed(db: Path) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, command_line) "
        "VALUES ('r1', '2026-01-01T00:00:00Z', '')"
    )
    attrs = json.dumps({"error.message": "bad SQL"})
    conn.execute(
        "INSERT INTO spans VALUES "
        "('s1', 't', NULL, 'r1', 'repo.aggregate', 'internal', 'error', "
        " 0, 1, 1, ?)",
        (attrs,),
    )
    conn.execute(
        "INSERT INTO spans VALUES "
        "('s2', 't', NULL, 'r1', 'repo.aggregate', 'internal', 'error', "
        " 2, 3, 1, ?)",
        (attrs,),
    )
    conn.commit()
    conn.close()


def test_exceptions_clusters_by_span_name_and_message(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed(db)
    results = exceptions_from_errors(db, "r1")
    assert len(results) == 1
    assert results[0].span_name == "repo.aggregate"
    assert results[0].message == "bad SQL"
    assert results[0].count == 2
