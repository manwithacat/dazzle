"""Database cleanup: find and remove FK orphans."""

import logging
from typing import Any

from .connection import fetchval
from .graph import get_ref_fields
from .sql import quote_id
from .verify import _build_orphan_query, unanchored_invariant_fields

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 10


def _unanchored_checks(entities: list[Any]) -> list[tuple[str, list[str]]]:
    """(entity_name, anchor_fields) pairs for at-least-one-anchor invariants (#1364)."""
    out: list[tuple[str, list[str]]] = []
    for entity in entities:
        for invariant in getattr(entity, "invariants", []) or []:
            fields = unanchored_invariant_fields(invariant)
            if fields is not None:
                out.append((entity.name, fields))
    return out


def _unanchored_where(anchor_fields: list[str]) -> str:
    return " AND ".join(f"{quote_id(f)} IS NULL" for f in anchor_fields)


def _build_delete_orphans_query(
    *,
    child_table: str,
    fk_column: str,
    parent_table: str,
    pk_column: str,
) -> str:
    """Build SQL to delete orphan rows. All args must be quoted identifiers."""
    # #1384: cast both sides to text so a text FK vs uuid PK (or vice-versa)
    # doesn't abort with "operator does not exist: uuid = text".
    return (
        f"DELETE FROM {child_table} "
        f"WHERE {fk_column} IS NOT NULL "
        f"AND NOT EXISTS ("
        f"SELECT 1 FROM {parent_table} p "
        f"WHERE p.{pk_column}::text = {child_table}.{fk_column}::text"
        f")"
    )


async def db_cleanup_impl(
    *,
    entities: list[Any],
    conn: Any,
    dry_run: bool = False,
    unanchored: bool = False,
) -> dict[str, Any]:
    """Find and remove FK orphans iteratively.

    Repeats until no orphans remain or MAX_ITERATIONS is reached.

    Args:
        entities: List of EntitySpec objects.
        conn: psycopg3 async connection.
        dry_run: If True, count orphans without deleting.
        unanchored: #1364 opt-in — also sweep rows violating an
            at-least-one-anchor invariant (`a != null or b != null`).
            Off by default: unlike orphans (rows pointing at nothing),
            unanchored rows may be mid-flow data a user intends to anchor.

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

    unanchored_checks = _unanchored_checks(entities) if unanchored else []

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
                count = await fetchval(conn, sql)
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

        for entity_name, anchor_fields in unanchored_checks:
            sql = (
                f"SELECT count(*) FROM {quote_id(entity_name)} "
                f"WHERE {_unanchored_where(anchor_fields)}"
            )
            try:
                count = await fetchval(conn, sql)
                if count > 0:
                    findings.append(
                        {
                            "entity": entity_name,
                            "field": " / ".join(anchor_fields),
                            "ref": None,
                            "unanchored_count": count,
                        }
                    )
                    total_would_delete += count
            except Exception as e:
                logger.warning("Error checking unanchored %s: %s", entity_name, e)

        return {
            "dry_run": True,
            "would_delete": total_would_delete,
            "findings": findings,
        }

    # Iterative cleanup
    total_deleted = 0
    iteration = 0  # Initialize before loop to avoid UnboundLocalError when checks is empty
    all_deletions: list[dict[str, Any]] = []

    if not checks and not unanchored_checks:
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
                count = await fetchval(conn, count_sql)
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

        # #1364: unanchored sweep rides inside the same iterative loop —
        # deleting unanchored rows can orphan THEIR children, which the
        # next iteration's orphan pass then reaps.
        for entity_name, anchor_fields in unanchored_checks:
            where = _unanchored_where(anchor_fields)
            count_sql = f"SELECT count(*) FROM {quote_id(entity_name)} WHERE {where}"
            try:
                count = await fetchval(conn, count_sql)
                if count == 0:
                    continue
                # table + column names are quote_id()-sanitised identifiers
                # (not bindable as params); no user-input values.
                _del = f"DELETE FROM {quote_id(entity_name)} WHERE {where}"  # nosemgrep
                await conn.execute(_del)  # nosemgrep
                round_deleted += count
                all_deletions.append(
                    {
                        "entity": entity_name,
                        "field": " / ".join(anchor_fields),
                        "ref": None,
                        "deleted": count,
                        "iteration": iteration,
                        "kind": "unanchored",
                    }
                )
            except Exception as e:
                logger.warning("Error sweeping unanchored %s: %s", entity_name, e)

        total_deleted += round_deleted
        if round_deleted == 0:
            break

    return {
        "total_deleted": total_deleted,
        "iterations": iteration,
        "deletions": all_deletions,
    }
