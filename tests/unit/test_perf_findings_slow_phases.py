"""Slow Dazzle-phase tests — ranks our manually-instrumented spans."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dazzle.perf.exporter import _SCHEMA_PATH
from dazzle.perf.findings.extractor import slow_phases

_DAZZLE_PHASES = (
    "dsl.parse",
    "predicate.compile",
    "aggregate.expression.compile",
    "aggregate.build_sql",
    "repo.aggregate",
    "region.render",
    "fragment.emit",
)


def _seed_phase_spans(db: Path, rows: list[tuple[str, int]]) -> None:
    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, command_line) "
        "VALUES ('r1', '2026-01-01T00:00:00Z', '')"
    )
    for i, (name, dur) in enumerate(rows):
        conn.execute(
            "INSERT INTO spans VALUES (?, 't', NULL, 'r1', ?, 'internal', 'ok', ?, ?, ?, '{}')",
            (f"s{i}", name, i * 1000, i * 1000 + dur, dur),
        )
    conn.commit()
    conn.close()


def test_slow_phases_aggregates_and_ranks(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed_phase_spans(
        db,
        [
            ("aggregate.build_sql", 30_000_000),
            ("aggregate.build_sql", 10_000_000),
            ("predicate.compile", 5_000_000),
        ],
    )
    results = slow_phases(db, "r1", top=10)
    by_name = {r.name: r for r in results}
    assert by_name["aggregate.build_sql"].calls == 2
    assert by_name["aggregate.build_sql"].total_ms == 40.0
    assert by_name["aggregate.build_sql"].max_ms == 30.0
    assert by_name["predicate.compile"].calls == 1


def test_slow_phases_filters_to_known_phase_names(tmp_path: Path) -> None:
    """Non-Dazzle span names (e.g. unrelated auto-instrumentation) are
    excluded so this finding stays focused on framework hot paths."""
    db = tmp_path / "run.db"
    _seed_phase_spans(
        db,
        [
            ("aggregate.build_sql", 10_000_000),
            ("some.other.span", 50_000_000),
        ],
    )
    names = {r.name for r in slow_phases(db, "r1", top=10)}
    assert names == {"aggregate.build_sql"}


def test_known_phase_set_pinned() -> None:
    """The phase set is a public contract — pin it here so a future
    rename or addition is intentional."""
    from dazzle.perf.findings.extractor import DAZZLE_PHASE_NAMES

    assert set(DAZZLE_PHASE_NAMES) == set(_DAZZLE_PHASES)
