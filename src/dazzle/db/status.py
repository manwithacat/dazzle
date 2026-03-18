# src/dazzle/db/status.py
"""Database status: row counts per entity, database size."""

from __future__ import annotations

from typing import Any

from .sql import quote_id


async def db_status_impl(
    *,
    entities: list[Any],
    conn: Any,
) -> dict[str, Any]:
    """Get row counts per entity and database size.

    Args:
        entities: List of EntitySpec objects.
        conn: asyncpg connection.

    Returns:
        Dict with entity row counts, totals, and database size.
    """
    results: list[dict[str, Any]] = []
    total_rows = 0

    for entity in entities:
        table = quote_id(entity.name)
        try:
            count = await conn.fetchval(f"SELECT count(*) FROM {table}")
            results.append(
                {"name": entity.name, "table": entity.name, "rows": count, "error": None}
            )
            total_rows += count
        except Exception as e:
            results.append({"name": entity.name, "table": entity.name, "rows": 0, "error": str(e)})

    # Database size
    try:
        db_size = await conn.fetchval("SELECT pg_size_pretty(pg_database_size(current_database()))")
    except Exception:
        db_size = "unknown"

    return {
        "entities": results,
        "total_entities": len(entities),
        "total_rows": total_rows,
        "database_size": db_size,
    }
