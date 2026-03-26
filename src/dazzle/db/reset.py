"""Database reset: truncate entity tables in dependency order."""

import logging
from typing import Any

from .graph import leaves_first
from .sql import quote_id

logger = logging.getLogger(__name__)

# Internal auth/config tables that should never be truncated.
# Stored as PascalCase entity names (matching table names).
AUTH_TABLES = frozenset(
    {
        "dazzle_user",
        "dazzle_session",
        "dazzle_role",
        "alembic_version",
    }
)


def _build_count_query(*, table: str) -> str:
    """Build SQL to count rows in a table.

    Args:
        table: Already-quoted table identifier.
    """
    return "SELECT count(*) FROM " + table


def _build_truncate_query(*, table: str) -> str:
    """Build SQL to truncate a table with cascade.

    Args:
        table: Already-quoted table identifier.
    """
    return "TRUNCATE TABLE " + table + " CASCADE"


async def db_reset_impl(
    *,
    entities: list[Any],
    conn: Any,
    preserve: set[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Truncate entity tables in leaf-first order.

    Args:
        entities: List of EntitySpec objects.
        conn: asyncpg connection.
        preserve: Set of entity names to skip (PascalCase).
        dry_run: If True, report what would be truncated without doing it.

    Returns:
        Dict with truncation results.
    """
    preserve_names: set[str] = set()
    if preserve:
        preserve_names |= preserve

    order = leaves_first(entities)
    truncated: list[dict[str, Any]] = []
    preserved: list[str] = []
    total_rows = 0

    for name in order:
        if name in preserve_names:
            preserved.append(name)
            continue

        table = quote_id(name)
        count_sql = _build_count_query(table=table)
        truncate_sql = _build_truncate_query(table=table)

        try:
            row_count = await conn.fetchval(count_sql)
        except Exception:
            row_count = 0

        if dry_run:
            truncated.append({"name": name, "table": name, "rows": row_count})
            total_rows += row_count
            continue

        try:
            await conn.execute(truncate_sql)
            truncated.append({"name": name, "table": name, "rows": row_count})
            total_rows += row_count
        except Exception as e:
            logger.warning("Failed to truncate %s: %s", name, e)
            truncated.append({"name": name, "table": name, "rows": 0, "error": str(e)})

    if dry_run:
        return {
            "dry_run": True,
            "would_truncate": len(truncated),
            "total_rows": total_rows,
            "tables": truncated,
            "preserved": preserved,
        }

    return {
        "truncated": len(truncated),
        "total_rows": total_rows,
        "tables": truncated,
        "preserved": preserved,
    }
