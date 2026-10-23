"""Report framework objects missing from a live database (#1850).

The committed ``FRAMEWORK_SCHEMA_SNAPSHOT`` declares every table, column and index
the framework orchestrator builds (it is pinned three ways to ``alembic upgrade head``
and the orchestrator by the parity gate). ``dazzle db verify`` compares the live
``public`` schema with it, so a database that lacks an object a development boot
would have created — the drift #1850 found in production — is reported, with the
remedy ``dazzle db upgrade head``. Extra objects (a table a removed subsystem left
behind) are not reported.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from dazzle.http.runtime.framework_schema_snapshot import FRAMEWORK_SCHEMA_SNAPSHOT

from .connection import fetchall

_LIVE_COLUMNS_SQL = (
    "SELECT table_name, column_name FROM information_schema.columns WHERE table_schema = 'public'"
)
_LIVE_INDEXES_SQL = "SELECT tablename, indexname FROM pg_indexes WHERE schemaname = 'public'"


def compare_framework_schema(
    expected: Mapping[str, Mapping[str, Any]],
    live_columns: Mapping[str, set[str]],
    live_indexes: Mapping[str, set[str]],
) -> list[dict[str, Any]]:
    """Diff the declared framework schema against the live one (missing objects only)."""
    drifts: list[dict[str, Any]] = []
    for table in sorted(expected):
        snap = expected[table]
        if table not in live_columns:
            drifts.append({"table": table, "missing_table": True, "columns": [], "indexes": []})
            continue
        columns = sorted(set(snap.get("columns") or {}) - live_columns[table])
        indexes = sorted(set(snap.get("indexes") or {}) - live_indexes.get(table, set()))
        if columns or indexes:
            drifts.append(
                {"table": table, "missing_table": False, "columns": columns, "indexes": indexes}
            )
    return drifts


async def detect_framework_drift(conn: Any) -> list[dict[str, Any]]:
    """Framework tables, columns and indexes the live database lacks."""
    live_columns: dict[str, set[str]] = {}
    for row in await fetchall(conn, _LIVE_COLUMNS_SQL):
        live_columns.setdefault(row["table_name"], set()).add(row["column_name"])
    live_indexes: dict[str, set[str]] = {}
    for row in await fetchall(conn, _LIVE_INDEXES_SQL):
        live_indexes.setdefault(row["tablename"], set()).add(row["indexname"])
    expected = cast(Mapping[str, Mapping[str, Any]], FRAMEWORK_SCHEMA_SNAPSHOT)
    return compare_framework_schema(expected, live_columns, live_indexes)
