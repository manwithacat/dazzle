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
    FindingsReport,
    SlowEndpoint,
    SlowQuery,
)

_LITERAL_PATTERNS = [
    re.compile(r"'(?:[^']|'')*'"),  # single-quoted strings
    re.compile(r'"(?:[^"]|"")*"'),  # double-quoted strings
    re.compile(r"\b\d+(?:\.\d+)?\b"),  # numeric literals
]


def normalise_statement(stmt: str) -> str:
    """Replace string + numeric literals with ``?`` and collapse whitespace."""
    out = stmt
    for pattern in _LITERAL_PATTERNS:
        out = pattern.sub("?", out)
    return re.sub(r"\s+", " ", out).strip()


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


def build_findings(db_path: Path, run_id: str) -> FindingsReport:
    """Run every heuristic and assemble the FindingsReport.

    Currently wires :func:`slow_endpoints` and :func:`slow_queries`.
    Subsequent tasks add the other heuristics and append them here.
    """
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
    )
