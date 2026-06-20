"""Pin the manual-span instrumentation against every hot path.

Each test triggers the production code path and asserts a named span
appears in the trace store. Uses ``configure_tracer(batch=False)`` so
spans are flushed synchronously inside the test body.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from dazzle.perf.tracer import configure_tracer, reset_tracer


@pytest.fixture
def trace_db(tmp_path: Path):
    db = tmp_path / "run.db"
    configure_tracer(run_id="r1", db_path=db, batch=False)
    yield db
    reset_tracer()


def _names(db: Path) -> set[str]:
    return {r[0] for r in sqlite3.connect(db).execute("SELECT name FROM spans")}


def test_aggregate_expression_compile_emits_span(trace_db: Path) -> None:
    from dazzle.core.ir import AggregateExpr
    from dazzle.http.runtime.aggregate_expression import (
        compile_aggregate_expression,
    )

    compile_aggregate_expression(AggregateExpr(column_name="score"))
    assert "aggregate.expression.compile" in _names(trace_db)


def test_build_aggregate_sql_emits_span(trace_db: Path) -> None:
    from dazzle.http.runtime.aggregate import build_aggregate_sql

    build_aggregate_sql(
        table_name="t",
        placeholder_style="%s",
        dimensions=[],
        measures={"primary": "count"},
        filters=None,
    )
    assert "aggregate.build_sql" in _names(trace_db)
