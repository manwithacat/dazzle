"""Read-side queries over the perf SQLite store.

Pure functions over an immutable schema (see ``schema.sql``). The
findings extractor and CLI report formatter share these helpers — no
side-effects, no caching, one connection per call.
"""

from __future__ import annotations

import dataclasses
import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path


@dataclasses.dataclass(frozen=True)
class Run:
    run_id: str
    started_at: str
    ended_at: str | None
    app_name: str | None
    manifest_path: str | None
    command_line: str


@dataclasses.dataclass(frozen=True)
class Span:
    span_id: str
    trace_id: str
    parent_span_id: str | None
    run_id: str
    name: str
    kind: str
    status: str
    started_ns: int
    ended_ns: int
    duration_ns: int
    attributes: dict[str, object]


@dataclasses.dataclass(frozen=True)
class Event:
    span_id: str
    run_id: str
    name: str
    timestamp_ns: int
    attributes: dict[str, object]


def list_runs(db_path: Path) -> Iterator[Run]:
    """Yield every ``runs`` row, newest first."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT run_id, started_at, ended_at, app_name, manifest_path, "
            "       command_line "
            "FROM runs ORDER BY started_at DESC"
        ).fetchall()
    for row in rows:
        yield Run(**dict(row))


def get_run(db_path: Path, run_id: str) -> Run | None:
    """Return a single ``Run`` or ``None`` when the id doesn't match."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT run_id, started_at, ended_at, app_name, manifest_path, "
            "       command_line "
            "FROM runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    return Run(**dict(row)) if row else None


def iter_spans(db_path: Path, run_id: str) -> Iterator[Span]:
    """Yield every ``Span`` belonging to ``run_id``, oldest first."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT span_id, trace_id, parent_span_id, run_id, name, kind, "
            "       status, started_ns, ended_ns, duration_ns, attributes_json "
            "FROM spans WHERE run_id = ? ORDER BY started_ns",
            (run_id,),
        ).fetchall()
    for row in rows:
        data = dict(row)
        attrs_json = data.pop("attributes_json")
        data["attributes"] = json.loads(attrs_json) if attrs_json else {}
        yield Span(**data)


def iter_events(db_path: Path, run_id: str) -> Iterator[Event]:
    """Yield every ``Event`` belonging to ``run_id``."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT span_id, run_id, name, timestamp_ns, attributes_json "
            "FROM events WHERE run_id = ? ORDER BY timestamp_ns",
            (run_id,),
        ).fetchall()
    for row in rows:
        data = dict(row)
        attrs_json = data.pop("attributes_json")
        data["attributes"] = json.loads(attrs_json) if attrs_json else {}
        yield Event(**data)
