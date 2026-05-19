"""Auto-instrumentation glue tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.perf.instrument import instrument_app
from dazzle.perf.tracer import configure_tracer, reset_tracer


@pytest.fixture
def trace_db(tmp_path: Path):
    db = tmp_path / "run.db"
    configure_tracer(run_id="r1", db_path=db, batch=False)
    yield db
    reset_tracer()


def test_instrument_app_captures_request_span(trace_db: Path) -> None:
    app = FastAPI()

    @app.get("/hello")
    def hello() -> dict[str, str]:
        return {"ok": "yes"}

    instrument_app(app)
    client = TestClient(app)
    response = client.get("/hello")
    assert response.status_code == 200

    rows = sqlite3.connect(trace_db).execute("SELECT name, status FROM spans").fetchall()
    # FastAPI instrumentation names server spans after the route template.
    assert any("GET /hello" in r[0] for r in rows)
