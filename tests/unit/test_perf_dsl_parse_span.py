"""Pin the dsl.parse span fires when tracer initialises before parsing (#1158)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dazzle.perf.tracer import configure_tracer, reset_tracer


def test_dsl_parse_span_lands_when_tracer_preconfigured(
    tmp_path: Path,
) -> None:
    """dsl.parse span lands in the SQLite store when the tracer is wired
    before parse_dsl is called — the fix for #1158.

    Uses ``batch=False`` (SimpleSpanProcessor) so spans flush
    synchronously and are readable immediately after the context manager
    exits, matching the test-isolation convention described in
    ``configure_tracer``'s docstring.
    """
    db = tmp_path / "run.db"
    configure_tracer(run_id="r1", db_path=db, batch=False, command_line="pytest")
    try:
        from dazzle.core.dsl_parser_impl import parse_dsl

        # Minimal valid DSL — module header is enough to trigger the
        # dazzle_span("dsl.parse", ...) context manager inside parse_dsl.
        parse_dsl('module test\napp t "T"\n', Path("/tmp/t.dsl"))
    finally:
        reset_tracer()

    rows = sqlite3.connect(db).execute("SELECT name FROM spans WHERE name = 'dsl.parse'").fetchall()
    assert rows, "dsl.parse span did not land in the trace store"
