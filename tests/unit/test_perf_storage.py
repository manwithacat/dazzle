"""Storage read-side helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dazzle.perf.storage import (
    Span,
    get_run,
    iter_events,
    iter_spans,
    list_runs,
)


def _seed(db: Path, *, run_id: str) -> None:
    """Hand-craft a small trace to exercise the readers."""
    from dazzle.perf.exporter import _SCHEMA_PATH

    conn = sqlite3.connect(db)
    conn.executescript(_SCHEMA_PATH.read_text())
    conn.execute(
        "INSERT INTO runs (run_id, started_at, ended_at, app_name, command_line) "
        "VALUES (?, '2026-05-19T20:30:00Z', '2026-05-19T20:30:05Z', 'app', 'cmd')",
        (run_id,),
    )
    conn.execute(
        "INSERT INTO spans "
        "(span_id, trace_id, parent_span_id, run_id, name, kind, status, "
        " started_ns, ended_ns, duration_ns, attributes_json) "
        "VALUES "
        "('s1', 't1', NULL, ?, 'root', 'internal', 'ok',  0, 100, 100, '{}'),"
        "('s2', 't1', 's1',  ?, 'child','internal', 'ok', 10,  80,  70, '{\"k\": 1}')",
        (run_id, run_id),
    )
    conn.execute(
        "INSERT INTO events (span_id, run_id, name, timestamp_ns, attributes_json) "
        "VALUES ('s1', ?, 'milestone', 50, '{}')",
        (run_id,),
    )
    conn.commit()
    conn.close()


def test_list_runs_returns_runs(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed(db, run_id="r1")
    runs = list(list_runs(db))
    assert len(runs) == 1
    assert runs[0].run_id == "r1"
    assert runs[0].app_name == "app"


def test_get_run_returns_single(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed(db, run_id="r1")
    run = get_run(db, "r1")
    assert run is not None
    assert run.run_id == "r1"
    assert get_run(db, "nope") is None


def test_iter_spans_returns_typed_rows(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed(db, run_id="r1")
    spans = list(iter_spans(db, "r1"))
    by_name = {s.name: s for s in spans}
    assert {"root", "child"} == set(by_name)
    assert by_name["child"].parent_span_id == "s1"
    assert by_name["child"].duration_ns == 70
    assert by_name["child"].attributes == {"k": 1}


def test_iter_events_returns_rows(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    _seed(db, run_id="r1")
    events = list(iter_events(db, "r1"))
    assert len(events) == 1
    assert events[0].name == "milestone"


def test_span_dataclass_is_immutable(tmp_path: Path) -> None:
    import dataclasses

    import pytest

    s = Span(
        span_id="s",
        trace_id="t",
        parent_span_id=None,
        run_id="r",
        name="n",
        kind="internal",
        status="ok",
        started_ns=0,
        ended_ns=1,
        duration_ns=1,
        attributes={},
    )
    assert dataclasses.is_dataclass(s)
    with pytest.raises(dataclasses.FrozenInstanceError):
        s.name = "x"  # type: ignore[misc]
