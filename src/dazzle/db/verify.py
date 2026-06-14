"""Database verification: FK integrity checks."""

from typing import Any

from .connection import fetchval
from .graph import get_ref_fields
from .sql import quote_id


def unanchored_invariant_fields(invariant: Any) -> list[str] | None:
    """Recognise the at-least-one-anchor invariant shape (#1364).

    ``invariant: case_ref != null or matter_ref != null`` parses to an
    OR-tree of ``BinaryExpr(op=NE, left=FieldRef, right=Literal(None))``
    nodes in ``invariant_expr``. That narrow shape translates statically to
    one SQL ``WHERE a IS NULL AND b IS NULL`` count; anything else returns
    None (not statically checkable — invariants are enforced at app
    write-time only, so out-of-convention writes can violate them).
    """
    expr = getattr(invariant, "invariant_expr", None)
    if expr is None:
        return None

    fields: list[str] = []

    def _walk(node: Any) -> bool:
        op = getattr(node, "op", None)
        op_value = getattr(op, "value", op)
        if op_value == "or":
            return _walk(node.left) and _walk(node.right)
        if op_value == "!=":
            path = getattr(node.left, "path", None)
            right = node.right
            if (
                path is not None
                and len(path) == 1
                and hasattr(right, "value")
                and right.value is None
            ):
                fields.append(path[0])
                return True
        return False

    if _walk(expr) and len(fields) >= 2:
        return fields
    return None


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
    # #1384: cast both sides to text. A `ref` FK column stored as text against a
    # uuid PK (or vice-versa) otherwise aborts the check with "operator does not
    # exist: uuid = text", which is then demoted to an errored check and the
    # orphan sweep silently under-reports.
    return (
        f"SELECT count(*) FROM {child_table} c "
        f"WHERE c.{fk_column} IS NOT NULL "
        f"AND NOT EXISTS ("
        f"SELECT 1 FROM {parent_table} p WHERE p.{pk_column}::text = c.{fk_column}::text"
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
        conn: psycopg3 async connection.

    Returns:
        Dict with check results and total issue count.
    """
    entity_map = {e.name: e for e in entities}
    checks: list[dict[str, Any]] = []
    total_issues = 0
    warning_count = 0  # #1035: column-mismatch / SQL errors emitted as ! lines
    # #1381: checks that ERRORED before they could evaluate (e.g. "relation does
    # not exist") must not be silently demoted to a clean pass. error_count is
    # distinct from total_issues (real findings) and gates the exit code, so a
    # run where every check errors fails loudly instead of reporting 0 / exit 0.
    error_count = 0

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
                orphan_count = await fetchval(conn, sql)
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
                warning_count += 1
                error_count += 1

    # #1364: required-ref NULL counts. Refs compile to soft (un-constrained)
    # columns by design; `required` is enforced at the app layer only, so
    # out-of-convention writes can leave NULLs the DSL forbids.
    for entity in entities:
        for field in get_ref_fields(entity):
            if not getattr(field, "is_required", False):
                continue
            sql = (
                f"SELECT count(*) FROM {quote_id(entity.name)} WHERE {quote_id(field.name)} IS NULL"
            )
            try:
                null_count = await fetchval(conn, sql)
                checks.append(
                    {
                        "entity": entity.name,
                        "field": field.name,
                        "ref": field.type.ref_entity,
                        "status": "required_null" if null_count > 0 else "ok",
                        "null_count": null_count,
                    }
                )
                total_issues += null_count
            except Exception as e:
                checks.append(
                    {
                        "entity": entity.name,
                        "field": field.name,
                        "ref": field.type.ref_entity,
                        "status": "error",
                        "error": str(e),
                    }
                )
                warning_count += 1
                error_count += 1

    # #1364: unanchored rows — entities whose at-least-one-anchor invariant
    # (`a != null or b != null`) is violated. Only that statically
    # translatable shape is checked; other invariants are app-write-time
    # contracts the DB cannot see.
    for entity in entities:
        for invariant in getattr(entity, "invariants", []) or []:
            anchor_fields = unanchored_invariant_fields(invariant)
            if anchor_fields is None:
                continue
            null_conds = " AND ".join(f"{quote_id(f)} IS NULL" for f in anchor_fields)
            sql = f"SELECT count(*) FROM {quote_id(entity.name)} WHERE {null_conds}"
            try:
                unanchored = await fetchval(conn, sql)
                checks.append(
                    {
                        "entity": entity.name,
                        "field": " / ".join(anchor_fields),
                        "ref": None,
                        "status": "unanchored" if unanchored > 0 else "ok",
                        "unanchored_count": unanchored,
                        "anchor_fields": anchor_fields,
                    }
                )
                total_issues += unanchored
            except Exception as e:
                checks.append(
                    {
                        "entity": entity.name,
                        "field": " / ".join(anchor_fields),
                        "ref": None,
                        "status": "error",
                        "error": str(e),
                    }
                )
                warning_count += 1
                error_count += 1

    return {
        "checks": checks,
        "total_issues": total_issues,
        "warning_count": warning_count,
        "error_count": error_count,
    }
