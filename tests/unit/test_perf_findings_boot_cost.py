"""Boot cost — sum of dsl.parse + route-generation spans (well-known names)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dazzle.perf.exporter import _SCHEMA_PATH
from dazzle.perf.findings.extractor import boot_cost


def test_boot_cost_sums_known_phases(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, command_line) "
        "VALUES ('r1', '2026-01-01T00:00:00Z', '')"
    )
    conn.executescript(
        """
        INSERT INTO spans VALUES
          ('a', 't', NULL, 'r1', 'dsl.parse',  'internal', 'ok',  0,  240000000, 240000000, '{}'),
          ('b', 't', NULL, 'r1', 'route.gen',  'internal', 'ok',  240000000, 320000000, 80000000, '{}');
        """
    )
    conn.commit()
    conn.close()

    cost = boot_cost(db, "r1")
    assert cost is not None
    assert cost.parse_dsl_ms == 240.0
    assert cost.route_gen_ms == 80.0
    assert cost.total_ms == 320.0


def test_boot_cost_returns_none_when_no_boot_spans(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, command_line) "
        "VALUES ('r1', '2026-01-01T00:00:00Z', '')"
    )
    conn.commit()
    conn.close()
    assert boot_cost(db, "r1") is None
