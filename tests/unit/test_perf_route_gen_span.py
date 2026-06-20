"""Pin route.gen span fires during framework boot (#1159)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dazzle.perf.tracer import configure_tracer, reset_tracer


def test_route_gen_span_lands_during_app_build(tmp_path: Path) -> None:
    """When the tracer is pre-configured (per #1158), the route-generation
    step fires a ``route.gen`` span that the SQLite exporter captures.

    Uses ``batch=False`` (SimpleSpanProcessor) so spans flush synchronously
    and are readable immediately after the context manager exits.

    Calls ``RouteGenerator.generate_all_routes`` directly with an empty
    endpoint list — the span wraps the entire method body so even zero
    endpoints produce a recorded span.
    """
    db = tmp_path / "run.db"
    configure_tracer(run_id="r1", db_path=db, batch=False)
    try:
        from dazzle.http.runtime.route_generator import RouteGenerator

        rg = RouteGenerator(services={}, models={})
        rg.generate_all_routes([])
    finally:
        reset_tracer()

    rows = sqlite3.connect(db).execute("SELECT name FROM spans WHERE name = 'route.gen'").fetchall()
    assert rows, "route.gen span did not land in the trace store"
