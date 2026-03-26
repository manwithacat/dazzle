"""Database verification: FK integrity checks."""

from typing import Any

from .graph import get_ref_fields
from .sql import quote_id


def _build_orphan_query(
    *,
    child_table: str,
    fk_column: str,
    parent_table: str,
    pk_column: str,
) -> str:
    """Build SQL to count orphan rows where FK references a missing parent.

    All arguments must already be quoted identifiers.
    """
    return (
        f"SELECT count(*) FROM {child_table} c "
        f"WHERE c.{fk_column} IS NOT NULL "
        f"AND NOT EXISTS ("
        f"SELECT 1 FROM {parent_table} p WHERE p.{pk_column} = c.{fk_column}"
        f")"
    )


async def db_verify_impl(
    *,
    entities: list[Any],
    conn: Any,
) -> dict[str, Any]:
    """Check FK integrity for all ref fields.

    Args:
        entities: List of EntitySpec objects.
        conn: asyncpg connection.

    Returns:
        Dict with check results and total issue count.
    """
    entity_map = {e.name: e for e in entities}
    checks: list[dict[str, Any]] = []
    total_issues = 0

    for entity in entities:
        ref_fields = get_ref_fields(entity)
        for field in ref_fields:
            ref_name = field.type.ref_entity
            if ref_name not in entity_map:
                continue  # external ref, skip

            child_table = quote_id(entity.name)
            parent_table = quote_id(ref_name)
            fk_column = quote_id(field.name)

            sql = _build_orphan_query(
                child_table=child_table,
                fk_column=fk_column,
                parent_table=parent_table,
                pk_column=quote_id("id"),
            )

            try:
                orphan_count = await conn.fetchval(sql)
                if orphan_count > 0:
                    checks.append(
                        {
                            "entity": entity.name,
                            "field": field.name,
                            "ref": ref_name,
                            "status": "orphans",
                            "orphan_count": orphan_count,
                        }
                    )
                    total_issues += orphan_count
                else:
                    checks.append(
                        {
                            "entity": entity.name,
                            "field": field.name,
                            "ref": ref_name,
                            "status": "ok",
                            "orphan_count": 0,
                        }
                    )
            except Exception as e:
                checks.append(
                    {
                        "entity": entity.name,
                        "field": field.name,
                        "ref": ref_name,
                        "status": "error",
                        "error": str(e),
                    }
                )

    return {
        "checks": checks,
        "total_issues": total_issues,
    }
