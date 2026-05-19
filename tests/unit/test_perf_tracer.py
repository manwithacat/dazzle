"""Tracer configuration + dazzle_span helper tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from pydantic import BaseModel

from dazzle.perf.tracer import configure_tracer, dazzle_span


class _Probe(BaseModel):
    label: str
    count: int


def test_configure_tracer_returns_provider(tmp_path: Path) -> None:
    provider = configure_tracer(run_id="r1", db_path=tmp_path / "run.db", batch=False)
    assert provider is not None


def test_dazzle_span_writes_span_attrs(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    configure_tracer(run_id="r1", db_path=db, batch=False)
    with dazzle_span("phase.op", entity="Task"):
        pass

    (name, attrs_json) = (
        sqlite3.connect(db).execute("SELECT name, attributes_json FROM spans").fetchone()
    )
    assert name == "phase.op"
    assert "entity" in attrs_json
    assert "Task" in attrs_json


def test_dazzle_span_flattens_pydantic_model(tmp_path: Path) -> None:
    db = tmp_path / "run.db"
    configure_tracer(run_id="r1", db_path=db, batch=False)
    with dazzle_span("phase.op", probe=_Probe(label="x", count=3)):
        pass

    (attrs_json,) = sqlite3.connect(db).execute("SELECT attributes_json FROM spans").fetchone()
    assert "probe.label" in attrs_json
    assert "probe.count" in attrs_json


def test_dazzle_span_is_no_op_when_uninitialised() -> None:
    """Importing dazzle_span without calling configure_tracer must not
    crash; spans become no-ops via OTel's default NoOpTracer."""
    from dazzle.perf.tracer import reset_tracer

    reset_tracer()
    with dazzle_span("phase.op", x=1):
        pass  # must not raise
