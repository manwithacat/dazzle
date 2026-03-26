"""Database cleanup: find and remove FK orphans."""

import logging
from typing import Any

from .graph import get_ref_fields
from .sql import quote_id
from .verify import _build_orphan_query

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 10


def _build_delete_orphans_query(
    *,
    child_table: str,
    fk_column: str,
    parent_table: str,
    pk_column: str,
) -> str:
    """Build SQL to delete orphan rows. All args must be quoted identifiers."""
    return (
        f"DELETE FROM {child_table} "
        f"WHERE {fk_column} IS NOT NULL "
        f"AND NOT EXISTS ("
        f"SELECT 1 FROM {parent_table} p WHERE p.{pk_column} = {child_table}.{fk_column}"
        f")"
    )


async def db_cleanup_impl(
    *,
    entities: list[Any],
    conn: Any,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Find and remove FK orphans iteratively.

    Repeats until no orphans remain or MAX_ITERATIONS is reached.

    Args:
        entities: List of EntitySpec objects.
        conn: asyncpg connection.
        dry_run: If True, count orphans without deleting.

    Returns:
        Dict with cleanup results.
    """
    entity_map = {e.name: e for e in entities}

    # Build list of (entity_name, field, ref_name) checks
    checks: list[tuple[str, Any, str]] = []
    for entity in entities:
        for field in get_ref_fields(entity):
            if field.type.ref_entity in entity_map:
                checks.append((entity.name, field, field.type.ref_entity))

    if dry_run:
        total_would_delete = 0
        findings: list[dict[str, Any]] = []
        for entity_name, field, ref_name in checks:
            child_table = quote_id(entity_name)
            parent_table = quote_id(ref_name)
            fk_column = quote_id(field.name)
            pk_column = quote_id("id")
            sql = _build_orphan_query(
                child_table=child_table,
                fk_column=fk_column,
                parent_table=parent_table,
                pk_column=pk_column,
            )
            try:
                count = await conn.fetchval(sql)
                if count > 0:
                    findings.append(
                        {
                            "entity": entity_name,
                            "field": field.name,
                            "ref": ref_name,
                            "orphan_count": count,
                        }
                    )
                    total_would_delete += count
            except Exception as e:
                logger.warning("Error checking %s.%s: %s", entity_name, field.name, e)

        return {
            "dry_run": True,
            "would_delete": total_would_delete,
            "findings": findings,
        }

    # Iterative cleanup
    total_deleted = 0
    iteration = 0  # Initialize before loop to avoid UnboundLocalError when checks is empty
    all_deletions: list[dict[str, Any]] = []

    if not checks:
        return {
            "total_deleted": 0,
            "iterations": 0,
            "deletions": [],
        }

    for iteration in range(1, MAX_ITERATIONS + 1):
        round_deleted = 0

        for entity_name, field, ref_name in checks:
            child_table = quote_id(entity_name)
            parent_table = quote_id(ref_name)
            fk_column = quote_id(field.name)
            pk_column = quote_id("id")

            count_sql = _build_orphan_query(
                child_table=child_table,
                fk_column=fk_column,
                parent_table=parent_table,
                pk_column=pk_column,
            )
            try:
                count = await conn.fetchval(count_sql)
                if count == 0:
                    continue

                delete_sql = _build_delete_orphans_query(
                    child_table=child_table,
                    fk_column=fk_column,
                    parent_table=parent_table,
                    pk_column=pk_column,
                )
                await conn.execute(delete_sql)
                round_deleted += count
                all_deletions.append(
                    {
                        "entity": entity_name,
                        "field": field.name,
                        "ref": ref_name,
                        "deleted": count,
                        "iteration": iteration,
                    }
                )
            except Exception as e:
                logger.warning("Error cleaning %s.%s: %s", entity_name, field.name, e)

        total_deleted += round_deleted
        if round_deleted == 0:
            break

    return {
        "total_deleted": total_deleted,
        "iterations": iteration,
        "deletions": all_deletions,
    }
