"""Findings heuristics — one function per category, plus the top-level
``build_findings`` that runs them all.

Each heuristic takes a ``db_path`` + ``run_id`` + tuning knobs and
returns its slice of the ``FindingsReport``. The functions are exposed
individually so tests can pin each heuristic in isolation.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from dazzle.perf.findings.types import (
    BootCost,
    ExceptionFinding,
    FindingsReport,
    NPlusOne,
    RenderFanOut,
    SlowEndpoint,
    SlowPhase,
    SlowQuery,
)

# Only single-quoted strings and numeric literals are normalised.
# Double-quoted text is NOT a string literal in PostgreSQL — it's a
# quoted identifier (table / column name), and SQLAlchemy emits them
# routinely. Collapsing those to ``?`` would erase the table name from
# the slow-query report and over-cluster unrelated tables (#1166).
_LITERAL_PATTERNS = [
    re.compile(r"'(?:[^']|'')*'"),  # single-quoted strings
    re.compile(r"\b\d+(?:\.\d+)?\b"),  # numeric literals
]


def normalise_statement(stmt: str) -> str:
    """Replace single-quoted string + numeric literals with ``?`` and
    collapse whitespace. Double-quoted identifiers are left intact so
    the slow-query report keeps table names."""
    out = stmt
    for pattern in _LITERAL_PATTERNS:
        out = pattern.sub("?", out)
    return re.sub(r"\s+", " ", out).strip()


DAZZLE_PHASE_NAMES: tuple[str, ...] = (
    "dsl.parse",
    "predicate.compile",
    "aggregate.expression.compile",
    "aggregate.build_sql",
    "repo.aggregate",
    "region.render",
    "fragment.emit",
)


def slow_phases(db_path: Path, run_id: str, *, top: int = 10) -> list[SlowPhase]:
    """Aggregate the manually-instrumented Dazzle spans by name and rank
    by total wall time. Span names outside :data:`DAZZLE_PHASE_NAMES`
    are excluded so this finding stays focused on framework hot paths."""
    known_phases = set(DAZZLE_PHASE_NAMES)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                name,
                COUNT(*) AS calls,
                SUM(duration_ns) / 1e6 AS total_ms,
                MAX(duration_ns) / 1e6 AS max_ms
            FROM spans
            WHERE run_id = ? AND kind = 'internal'
            GROUP BY name
            ORDER BY total_ms DESC
            """,
            (run_id,),
        ).fetchall()

    # Filter to known Dazzle phases and rank by total_ms.
    findings = [
        SlowPhase(
            name=row["name"],
            calls=int(row["calls"]),
            total_ms=float(row["total_ms"]),
            max_ms=float(row["max_ms"]),
        )
        for row in rows
        if row["name"] in known_phases
    ]
    return findings[:top]


def slow_queries(db_path: Path, run_id: str, *, top: int = 10) -> list[SlowQuery]:
    """Top-N SQL statements by total wall time, clustered by normalised form."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT duration_ns, attributes_json
            FROM spans
            WHERE run_id = ? AND kind = 'client'
              AND attributes_json LIKE '%"db.statement"%'
            """,
            (run_id,),
        ).fetchall()

    buckets: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        attrs = json.loads(row["attributes_json"])
        raw = attrs.get("db.statement")
        if not isinstance(raw, str):
            continue
        buckets[normalise_statement(raw)].append(int(row["duration_ns"]))

    findings = [
        SlowQuery(
            statement=stmt,
            calls=len(durations),
            total_ms=sum(durations) / 1e6,
        )
        for stmt, durations in buckets.items()
    ]
    findings.sort(key=lambda f: f.total_ms, reverse=True)
    return findings[:top]


def slow_endpoints(db_path: Path, run_id: str, *, top: int = 10) -> list[SlowEndpoint]:
    """Top-N endpoints by total wall time. Computes p95 with SQLite's
    NTILE so we don't load all spans into Python.

    Filters on ``kind = 'server'`` — only FastAPI request spans count as
    endpoints; framework-internal spans are surfaced via
    :func:`slow_phases`.
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            WITH endpoint_calls AS (
                SELECT name, duration_ns
                FROM spans
                WHERE run_id = ? AND kind = 'server'
            ),
            ranked AS (
                SELECT
                    name,
                    duration_ns,
                    NTILE(20) OVER (PARTITION BY name ORDER BY duration_ns) AS bucket
                FROM endpoint_calls
            ),
            p95 AS (
                SELECT name, MAX(duration_ns) AS p95_ns
                FROM ranked
                WHERE bucket <= 19
                GROUP BY name
            )
            SELECT
                e.name AS route,
                COUNT(*) AS calls,
                SUM(e.duration_ns) / 1e6 AS total_ms,
                COALESCE(p95.p95_ns, MAX(e.duration_ns)) / 1e6 AS p95_ms
            FROM endpoint_calls e
            LEFT JOIN p95 USING (name)
            GROUP BY e.name
            ORDER BY total_ms DESC
            LIMIT ?
            """,
            (run_id, top),
        ).fetchall()
    return [
        SlowEndpoint(
            route=row["route"],
            calls=int(row["calls"]),
            total_ms=float(row["total_ms"]),
            p95_ms=float(row["p95_ms"]),
        )
        for row in rows
    ]


def detect_n_plus_one(db_path: Path, run_id: str, *, threshold: int = 3) -> list[NPlusOne]:
    """Flag every (parent_span, normalised_child_statement) pair whose
    repetition count meets ``threshold``."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                parent.name           AS parent_name,
                child.attributes_json AS child_attrs
            FROM spans AS child
            JOIN spans AS parent
              ON parent.span_id = child.parent_span_id
             AND parent.run_id  = child.run_id
            WHERE child.run_id = ?
              AND child.kind = 'client'
              AND child.attributes_json LIKE '%"db.statement"%'
            """,
            (run_id,),
        ).fetchall()

    buckets: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        attrs = json.loads(row["child_attrs"])
        raw = attrs.get("db.statement")
        if not isinstance(raw, str):
            continue
        buckets[(row["parent_name"], normalise_statement(raw))] += 1

    findings = [
        NPlusOne(parent_span=parent, child_statement=stmt, repetitions=count)
        for (parent, stmt), count in buckets.items()
        if count >= threshold
    ]
    findings.sort(key=lambda f: f.repetitions, reverse=True)
    return findings


def render_fanout(db_path: Path, run_id: str, *, top: int = 10) -> list[RenderFanOut]:
    """For each request span, count its descendant ``region.render`` spans
    and sum their durations."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                parent.name                AS route,
                COUNT(child.span_id)       AS region_renders,
                SUM(child.duration_ns) / 1e6 AS total_ms
            FROM spans AS child
            JOIN spans AS parent
              ON parent.span_id = child.parent_span_id
             AND parent.run_id  = child.run_id
            WHERE child.run_id = ?
              AND child.name   = 'region.render'
              AND parent.kind  = 'server'
            GROUP BY parent.name
            ORDER BY region_renders DESC
            LIMIT ?
            """,
            (run_id, top),
        ).fetchall()
    return [
        RenderFanOut(
            route=row["route"],
            region_renders=int(row["region_renders"]),
            total_ms=float(row["total_ms"] or 0.0),
        )
        for row in rows
    ]


def boot_cost(db_path: Path, run_id: str) -> BootCost | None:
    """Sum the parse + route-generation cost from well-known boot span
    names. Returns ``None`` when neither span fired."""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT name, SUM(duration_ns) / 1e6 AS ms
            FROM spans
            WHERE run_id = ? AND name IN ('dsl.parse', 'route.gen')
            GROUP BY name
            """,
            (run_id,),
        ).fetchall()
    if not rows:
        return None
    by_name = {row["name"]: float(row["ms"]) for row in rows}
    parse = by_name.get("dsl.parse", 0.0)
    route = by_name.get("route.gen", 0.0)
    return BootCost(parse_dsl_ms=parse, route_gen_ms=route, total_ms=parse + route)


def exceptions_from_errors(db_path: Path, run_id: str) -> list[ExceptionFinding]:
    """Cluster ``status='error'`` spans by ``(span name, error message)``.

    OpenTelemetry records exceptions as span *events* named ``exception``
    (carrying ``exception.message``), not as top-level span attributes. We
    LEFT JOIN the ``events`` table to read the real message, falling back
    to the span's own ``error.message`` attribute when no event is present.
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                spans.name             AS span_name,
                spans.attributes_json  AS span_attrs,
                events.attributes_json AS event_attrs
            FROM spans
            LEFT JOIN events ON events.span_id = spans.span_id
                            AND events.run_id  = spans.run_id
                            AND events.name    = 'exception'
            WHERE spans.run_id = ? AND spans.status = 'error'
            """,
            (run_id,),
        ).fetchall()
    buckets: dict[tuple[str, str], int] = defaultdict(int)
    for row in rows:
        if row["event_attrs"] is not None:
            event_attrs = json.loads(row["event_attrs"])
            message = str(event_attrs.get("exception.message", "<no message>"))
        else:
            span_attrs = json.loads(row["span_attrs"])
            message = str(span_attrs.get("error.message", "<no message>"))
        buckets[(row["span_name"], message)] += 1
    return [
        ExceptionFinding(span_name=name, message=msg, count=count)
        for (name, msg), count in sorted(buckets.items(), key=lambda kv: kv[1], reverse=True)
    ]


def build_findings(db_path: Path, run_id: str) -> FindingsReport:
    """Run every heuristic and assemble the FindingsReport."""
    from dazzle.perf.storage import get_run

    run = get_run(db_path, run_id)
    if run is None:
        raise ValueError(f"run not found: {run_id}")
    return FindingsReport(
        run_id=run.run_id,
        app_name=run.app_name,
        started_at=run.started_at,
        ended_at=run.ended_at,
        slow_endpoints=slow_endpoints(db_path, run_id),
        slow_queries=slow_queries(db_path, run_id),
        n_plus_one=detect_n_plus_one(db_path, run_id),
        slow_phases=slow_phases(db_path, run_id),
        render_fanout=render_fanout(db_path, run_id),
        boot_cost=boot_cost(db_path, run_id),
        exceptions=exceptions_from_errors(db_path, run_id),
    )
