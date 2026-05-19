"""Findings heuristics — one function per category, plus the top-level
``build_findings`` that runs them all.

Each heuristic takes a ``db_path`` + ``run_id`` + tuning knobs and
returns its slice of the ``FindingsReport``. The functions are exposed
individually so tests can pin each heuristic in isolation.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from dazzle.perf.findings.types import (
    FindingsReport,
    SlowEndpoint,
)


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

    Currently wires :func:`slow_endpoints`. Subsequent tasks add the
    other heuristics and append them here.
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
    )
