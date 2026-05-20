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


def test_instrument_uses_reconfigured_provider(tmp_path: Path) -> None:
    """Auto-instrumented spans follow the *current* provider even after
    the tracer is reconfigured.

    ``trace.set_tracer_provider`` freezes the OTel global to the first
    provider for the life of the process, so resolving the tracer via
    the global would route FastAPI spans to a stale exporter. This is a
    regression guard for that bug (surfaced once CI could run the perf
    suite — multiple ``configure_tracer`` calls in one session).
    """
    first_db = tmp_path / "first.db"
    configure_tracer(run_id="first", db_path=first_db, batch=False)
    reset_tracer()

    second_db = tmp_path / "second.db"
    configure_tracer(run_id="second", db_path=second_db, batch=False)
    try:
        app = FastAPI()

        @app.get("/ping")
        def ping() -> dict[str, str]:
            return {"ok": "yes"}

        instrument_app(app)
        assert TestClient(app).get("/ping").status_code == 200

        rows = sqlite3.connect(second_db).execute("SELECT name FROM spans").fetchall()
        assert any("GET /ping" in r[0] for r in rows)
    finally:
        reset_tracer()
