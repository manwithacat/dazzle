"""Safe cast registry for Alembic type change migrations.

Maps (from_pg_type, to_pg_type) to USING clause templates. Casts in this
registry are known to be lossless and can be applied automatically during
auto-migration. Unknown casts are skipped with a warning.
"""

from __future__ import annotations

from dazzle_back.runtime.query_builder import quote_identifier

# (from_type, to_type) → USING template or "" for no-op widening.
# Types are uppercase Postgres type names as returned by information_schema.
SAFE_CASTS: dict[tuple[str, str], str] = {
    ("TEXT", "UUID"): "{col}::uuid",
    ("TEXT", "DATE"): "{col}::date",
    ("TEXT", "TIMESTAMPTZ"): "{col}::timestamptz",
    ("TEXT", "JSONB"): "{col}::jsonb",
    ("TEXT", "BOOLEAN"): "{col}::boolean",
    ("TEXT", "INTEGER"): "{col}::integer",
    ("DOUBLE PRECISION", "NUMERIC"): "",
    ("CHARACTER VARYING", "TEXT"): "",
}


def is_safe_cast(from_type: str, to_type: str) -> bool:
    """Return True if converting from_type to to_type is known-safe."""
    return (from_type.upper(), to_type.upper()) in SAFE_CASTS


def get_using_clause(from_type: str, to_type: str, column_name: str) -> str | None:
    """Return the USING clause for a safe cast, or None if not safe/needed.

    Returns None for unknown casts and for no-op widenings where USING
    is not needed. Returns a string like '"col"::uuid' for casts that
    require explicit USING.
    """
    template = SAFE_CASTS.get((from_type.upper(), to_type.upper()))
    if template is None:
        return None
    if not template:
        return None  # no-op widening
    return template.format(col=quote_identifier(column_name))
