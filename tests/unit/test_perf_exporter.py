"""SQLite span exporter round-trip tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor

from dazzle.perf.exporter import SQLiteSpanExporter


def _make_provider(db_path: Path, run_id: str) -> TracerProvider:
    provider = TracerProvider()
    exporter = SQLiteSpanExporter(db_path=db_path, run_id=run_id)
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    return provider


def test_exporter_writes_root_span(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    provider = _make_provider(db, "test-run-1")
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("root.op") as span:
        span.set_attribute("foo", "bar")

    provider.force_flush()
    rows = sqlite3.connect(db).execute("SELECT name, status, attributes_json FROM spans").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "root.op"
    assert rows[0][1] == "ok"
    assert json.loads(rows[0][2]) == {"foo": "bar"}


def test_exporter_records_parent_child(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    provider = _make_provider(db, "test-run-2")
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("root"):
        with tracer.start_as_current_span("child"):
            pass
    provider.force_flush()

    rows = (
        sqlite3.connect(db)
        .execute("SELECT name, parent_span_id IS NULL FROM spans ORDER BY started_ns")
        .fetchall()
    )
    assert rows[0] == ("root", 1)  # root has no parent
    assert rows[1] == ("child", 0)  # child has a parent


def test_exporter_records_error_status(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    provider = _make_provider(db, "test-run-3")
    tracer = provider.get_tracer("test")
    try:
        with tracer.start_as_current_span("boom"):
            raise RuntimeError("kaboom")
    except RuntimeError:
        pass
    provider.force_flush()

    (status,) = sqlite3.connect(db).execute("SELECT status FROM spans").fetchone()
    assert status == "error"


def test_exporter_records_events(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    provider = _make_provider(db, "test-run-4")
    tracer = provider.get_tracer("test")
    with tracer.start_as_current_span("op") as span:
        span.add_event("milestone", {"k": "v"})
    provider.force_flush()

    rows = sqlite3.connect(db).execute("SELECT name, attributes_json FROM events").fetchall()
    assert rows == [("milestone", json.dumps({"k": "v"}))]


def test_exporter_writes_run_row_with_metadata(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    exporter = SQLiteSpanExporter(
        db_path=db,
        run_id="r1",
        app_name="examples/simple_task",
        manifest_path="/tmp/dazzle.toml",
        command_line="dazzle perf trace --url /tasks",
    )
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    provider.get_tracer("t").start_as_current_span("op").__enter__().end()
    provider.force_flush()

    row = (
        sqlite3.connect(db)
        .execute("SELECT app_name, manifest_path, command_line FROM runs")
        .fetchone()
    )
    assert row == (
        "examples/simple_task",
        "/tmp/dazzle.toml",
        "dazzle perf trace --url /tasks",
    )


def test_exporter_force_flush_finalises_ended_at(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    exporter = SQLiteSpanExporter(db_path=db, run_id="r1")
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    provider.get_tracer("t").start_as_current_span("op").__enter__().end()
    exporter.shutdown()

    (ended,) = sqlite3.connect(db).execute("SELECT ended_at FROM runs").fetchone()
    assert ended is not None
