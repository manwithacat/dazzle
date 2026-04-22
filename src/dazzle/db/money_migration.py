"""Detection + auto-repair of legacy `money(...)` column shapes (#840).

Pre-v0.58 Dazzle stored `money(CCY)` fields as a single ``{name}`` column of
SQL type DOUBLE PRECISION. v0.58+ stores them as a pair — ``{name}_minor``
BIGINT and ``{name}_currency`` TEXT. Alembic autogenerate compares metadata
target (the new pair) against the live DB (the old single column) and emits
two ADD COLUMN ops with zero DROPs, silently leaving the legacy column
intact. Inserts/updates then 500 with ``UndefinedColumn: column
"{name}_minor" does not exist``.

This module provides:

1. ``detect_money_drifts(conn, entities)`` — returns the list of tables that
   still carry a legacy single-column money field. Purely diagnostic — no
   DDL/DML emitted.

2. ``repair_money_drifts(conn, entities, apply=False)`` — for each detected
   drift, emits (or optionally applies) the 5-statement migration pattern:

       ALTER TABLE t ADD COLUMN f_minor BIGINT;
       ALTER TABLE t ADD COLUMN f_currency TEXT;
       UPDATE t SET f_minor = ROUND(f*100)::bigint, f_currency = '<ccy>'
         WHERE f IS NOT NULL;
       ALTER TABLE t DROP COLUMN f;

   When ``apply=True`` the caller's connection/transaction is used to run
   the statements in order; otherwise the SQL is returned for review.

Wired into ``dazzle db verify`` — operators see the drift + exact repair
SQL at diagnostic time and can opt into auto-repair via ``--fix-money``.
"""

from __future__ import annotations

from typing import Any

from .sql import quote_id


def _money_fields(entity: Any) -> list[tuple[str, str]]:
    """Return ``[(field_name, currency_code), ...]`` for money fields on the entity."""
    result: list[tuple[str, str]] = []
    for f in getattr(entity, "fields", []):
        ftype = getattr(f, "type", None)
        if ftype is None:
            continue
        kind = getattr(ftype, "kind", None)
        # FieldKind may be the StrEnum itself, or a raw string — normalise
        # both to "money" for comparison.
        kind_name = getattr(kind, "value", None) or getattr(kind, "name", None) or kind
        if str(kind_name).lower() != "money":
            continue
        ccy = getattr(ftype, "currency_code", None) or "GBP"
        result.append((f.name, ccy))
    return result


async def _live_column_type(conn: Any, table: str, column: str) -> str | None:
    """Return the Postgres column type, or None if the column doesn't exist.

    Uses ``information_schema`` so it works across schemas without requiring
    the caller to pass one in.
    """
    row = await conn.fetchrow(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_name = $1 AND column_name = $2 LIMIT 1",
        table,
        column,
    )
    return row["data_type"] if row else None


async def detect_money_drifts(conn: Any, entities: list[Any]) -> list[dict[str, Any]]:
    """Return drifts for money fields whose DB shape is still the single column.

    A drift is reported when all three hold on the live DB:
      * the legacy ``{name}`` column exists with a numeric/double data_type
      * the new ``{name}_minor`` column does NOT exist
      * the new ``{name}_currency`` column does NOT exist

    Returns a list of ``{entity, field, currency, legacy_type, repair_sql}``
    dicts. Empty list when every money field is already on the new shape.
    """
    drifts: list[dict[str, Any]] = []
    for entity in entities:
        for field_name, currency in _money_fields(entity):
            legacy_type = await _live_column_type(conn, entity.name, field_name)
            if legacy_type is None:
                continue  # already migrated or never existed
            # Tolerate any numeric legacy type — double, numeric, decimal, real.
            if legacy_type.lower() not in {
                "double precision",
                "numeric",
                "real",
                "decimal",
            }:
                continue
            minor_type = await _live_column_type(conn, entity.name, f"{field_name}_minor")
            ccy_type = await _live_column_type(conn, entity.name, f"{field_name}_currency")
            if minor_type is not None or ccy_type is not None:
                # Partial migration — skip so we don't clobber
                drifts.append(
                    {
                        "entity": entity.name,
                        "field": field_name,
                        "currency": currency,
                        "legacy_type": legacy_type,
                        "status": "partial",
                        "repair_sql": "",
                    }
                )
                continue
            drifts.append(
                {
                    "entity": entity.name,
                    "field": field_name,
                    "currency": currency,
                    "legacy_type": legacy_type,
                    "status": "drift",
                    "repair_sql": _build_repair_sql(entity.name, field_name, currency),
                }
            )
    return drifts


def _build_repair_sql(entity_name: str, field_name: str, currency: str) -> str:
    """Emit the 4-statement repair pattern for a single money field."""
    table = quote_id(entity_name)
    legacy = quote_id(field_name)
    minor = quote_id(f"{field_name}_minor")
    ccy = quote_id(f"{field_name}_currency")
    # Currency code is validated against a safe set in the DSL parser; still
    # enforce a length guard here so the literal is always safe to interpolate.
    ccy_literal = _safe_ccy_literal(currency)
    return (
        f"ALTER TABLE {table} ADD COLUMN {minor} BIGINT;\n"
        f"ALTER TABLE {table} ADD COLUMN {ccy} TEXT;\n"
        f"UPDATE {table} SET {minor} = ROUND({legacy}*100)::bigint, "
        f"{ccy} = {ccy_literal} WHERE {legacy} IS NOT NULL;\n"
        f"ALTER TABLE {table} DROP COLUMN {legacy};"
    )


def _safe_ccy_literal(currency: str) -> str:
    """Produce a SQL string literal for a currency code after validation."""
    code = (currency or "GBP").strip().upper()
    if not code.isalpha() or len(code) != 3:
        code = "GBP"
    return f"'{code}'"


async def repair_money_drifts(
    conn: Any,
    entities: list[Any],
    *,
    apply: bool = False,
) -> dict[str, Any]:
    """Detect and optionally apply the money-column repair.

    When ``apply=False`` the returned dict contains the detected drifts and
    the combined SQL — the caller is responsible for executing it manually.

    When ``apply=True`` each drift's repair SQL is run on the supplied
    connection. The caller should wrap the call in a transaction so a
    partial failure rolls back; this function runs the statements one at a
    time without opening its own transaction (asyncpg manages that).
    """
    drifts = await detect_money_drifts(conn, entities)
    applied: list[str] = []
    errors: list[dict[str, Any]] = []

    if apply:
        for drift in drifts:
            if drift["status"] != "drift":
                continue
            for stmt in drift["repair_sql"].rstrip(";\n").split(";\n"):
                stmt = stmt.strip().rstrip(";")
                if not stmt:
                    continue
                try:
                    await conn.execute(stmt)
                    applied.append(stmt)
                except Exception as e:
                    errors.append(
                        {
                            "entity": drift["entity"],
                            "field": drift["field"],
                            "statement": stmt,
                            "error": str(e),
                        }
                    )

    return {
        "drifts": drifts,
        "drift_count": sum(1 for d in drifts if d["status"] == "drift"),
        "partial_count": sum(1 for d in drifts if d["status"] == "partial"),
        "applied_count": len(applied),
        "errors": errors,
    }
