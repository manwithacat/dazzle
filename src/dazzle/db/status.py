# src/dazzle/db/status.py
"""Database status: row counts per entity, database size."""

from typing import Any

from .connection import fetchval
from .sql import quote_id


def _is_missing_relation(err: str) -> bool:
    """Postgres / driver message when a table was never created in this DB."""
    lower = err.lower()
    return "does not exist" in lower and (
        "relation" in lower or "table" in lower or "line 1: select count(*) from" in lower
    )


async def db_status_impl(
    *,
    entities: list[Any],
    conn: Any,
) -> dict[str, Any]:
    """Get row counts per entity and database size.

    Args:
        entities: List of EntitySpec objects.
        conn: psycopg3 async connection.

    Returns:
        Dict with entity row counts, totals, and database size.

    Platform-domain entities (SystemHealth, SystemMetric, …) are injected into
    every AppSpec but only materialise tables when the app's migrate/serve path
    creates them. A missing platform table is **not** a project-data error —
    report ``status=not_materialized`` so MCP ``db.status`` stays agent-readable
    instead of spamming relation-does-not-exist noise (#1629 agent world-model).
    """
    results: list[dict[str, Any]] = []
    total_rows = 0
    not_materialized = 0

    for entity in entities:
        table = quote_id(entity.name)
        try:
            count = await fetchval(conn, f"SELECT count(*) FROM {table}")
            results.append(
                {
                    "name": entity.name,
                    "table": entity.name,
                    "rows": count,
                    "error": None,
                    "status": "ok",
                }
            )
            total_rows += count
        except Exception as e:
            err = str(e)
            domain = getattr(entity, "domain", None)
            if _is_missing_relation(err) and domain == "platform":
                not_materialized += 1
                results.append(
                    {
                        "name": entity.name,
                        "table": entity.name,
                        "rows": 0,
                        "error": None,
                        "status": "not_materialized",
                        "note": (
                            "platform entity table not present in this database "
                            "(not a project data defect)"
                        ),
                    }
                )
            else:
                results.append(
                    {
                        "name": entity.name,
                        "table": entity.name,
                        "rows": 0,
                        "error": err,
                        "status": "error",
                    }
                )

    # Database size
    try:
        db_size = await fetchval(
            conn, "SELECT pg_size_pretty(pg_database_size(current_database()))"
        )
    except Exception:
        db_size = "unknown"

    return {
        "entities": results,
        "total_entities": len(entities),
        "total_rows": total_rows,
        "not_materialized": not_materialized,
        "database_size": db_size,
    }
