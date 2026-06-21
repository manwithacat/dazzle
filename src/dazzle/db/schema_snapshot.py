"""Pure introspection of a SQLAlchemy MetaData → a plain-dict Snapshot.

The Snapshot captures table structure as it is defined in the SQLAlchemy
MetaData, which is the single source of truth built by
``dazzle.http.alembic.metadata_loader.load_target_metadata``.  That builder
already encodes entity→table naming (verbatim ``entity.name``), FK columns
(verbatim ``field.name``), and shared_schema additions (``tenant_id``,
composite FKs, tenant_id-leading indexes).  The snapshot therefore inherits
all of those conventions without re-deriving them.

Types
-----
ColSnap  = dict with keys: type (str), nullable (bool), default (str|None), pk (bool)
TableSnap = dict with keys: columns (dict[str, ColSnap]), fks (dict[str, str]),
                             uniques (list[str]), indexes (list[str])
Snapshot  = dict[str, TableSnap]   — keyed by table name (verbatim)

All dict keys and lists are sorted for deterministic comparison.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa

# ---------------------------------------------------------------------------
# Type token mapping
# ---------------------------------------------------------------------------


def _sa_type_to_token(sa_type: Any) -> str:
    """Map a SQLAlchemy type instance to a canonical string token.

    Covers the type set used by ``sa_schema.build_metadata``.  Unknown types
    fall back to ``str(sa_type).lower()``.
    """
    if isinstance(sa_type, sa.Text):
        return "text"
    if isinstance(sa_type, sa.BigInteger):
        # BigInteger is a subclass of Integer — check it first.
        return "bigint"
    if isinstance(sa_type, sa.Integer):
        return "integer"
    if isinstance(sa_type, sa.Boolean):
        return "boolean"
    if isinstance(sa_type, sa.Float):
        # Float is a subclass of Numeric — check it first.
        return "float"
    if isinstance(sa_type, sa.Numeric):
        p, s = sa_type.precision, sa_type.scale
        if p is not None and s is not None:
            return f"numeric({p},{s})"
        if p is not None:
            return f"numeric({p})"
        return "numeric"
    if isinstance(sa_type, sa.DateTime):
        return "timestamptz"
    if isinstance(sa_type, sa.Date):
        return "date"
    if isinstance(sa_type, sa.Uuid):
        return "uuid"
    if isinstance(sa_type, sa.JSON):
        return "json"
    return str(sa_type).lower()


# ---------------------------------------------------------------------------
# Server-default rendering
# ---------------------------------------------------------------------------


def _render_server_default(server_default: Any) -> str | None:
    """Return the SQL text of a DefaultClause, or None."""
    if server_default is None:
        return None
    arg = server_default.arg
    if isinstance(arg, str):
        return arg
    # TextClause or similar — compile to string without a dialect.
    return str(arg)


# ---------------------------------------------------------------------------
# Core projection
# ---------------------------------------------------------------------------


def project_schema(metadata: sa.MetaData) -> dict[str, Any]:
    """Introspect *metadata* and return a deterministic plain-dict Snapshot.

    This is a **pure** function: it touches only the in-memory MetaData
    object, never the database or the filesystem.  Unit tests can pass a
    hand-built MetaData; production code passes the result of
    ``load_target_metadata()``.

    The Snapshot structure::

        {
            "<TableName>": {
                "columns": {
                    "<col>": {"type": str, "nullable": bool,
                              "default": str | None, "pk": bool},
                    ...
                },
                "fks":     {"<col>": "<ReferencedTable>", ...},
                "uniques": ["<col>", ...],          # sorted
                "indexes": ["<col>[,<col>]", ...],  # sorted, comma-joined per index
            },
            ...
        }
    """
    snapshot: dict[str, Any] = {}

    for table in metadata.sorted_tables:
        # --- columns ---
        columns: dict[str, Any] = {}
        for col in table.columns:
            columns[col.name] = {
                "type": _sa_type_to_token(col.type),
                "nullable": bool(col.nullable),
                "default": _render_server_default(col.server_default),
                "pk": bool(col.primary_key),
            }

        # --- foreign keys (one FK per column; multi-FK columns pick first) ---
        fks: dict[str, str] = {}
        for col in table.columns:
            for fk in col.foreign_keys:
                fks[col.name] = fk.column.table.name
                break  # one FK per column is the norm; take first

        # --- unique columns ---
        unique_cols: set[str] = set()
        # col.unique is True when declared inline; None when not set
        for col in table.columns:
            if col.unique:
                unique_cols.add(col.name)
        # UniqueConstraints declared as table-level args
        for constraint in table.constraints:
            if isinstance(constraint, sa.UniqueConstraint):
                for col in constraint.columns:
                    unique_cols.add(col.name)

        # --- indexes ---
        # Column names within each index are sorted so that (tenant_id, status)
        # and (status, tenant_id) produce the same key.  This is an accepted
        # phase-1 limitation: index column-order changes are not detected.
        index_keys: list[str] = []
        for idx in table.indexes:
            cols_in_idx = [c.name for c in idx.columns]
            index_keys.append(",".join(sorted(cols_in_idx)))

        snapshot[table.name] = {
            "columns": dict(sorted(columns.items())),
            "fks": dict(sorted(fks.items())),
            "uniques": sorted(unique_cols),
            "indexes": sorted(index_keys),
        }

    return dict(sorted(snapshot.items()))


# ---------------------------------------------------------------------------
# Convenience wrapper: project the live project's schema
# ---------------------------------------------------------------------------


def project_current() -> dict[str, Any]:
    """Return the Snapshot for the Dazzle project in the current directory.

    Delegates to ``load_target_metadata()`` (the same builder Alembic uses for
    ``--autogenerate``) so the snapshot is always consistent with the real
    schema, including shared_schema ``tenant_id`` / composite-FK / index
    injections — no exclusion list required.
    """
    from dazzle.http.alembic.metadata_loader import load_target_metadata

    return project_schema(load_target_metadata())
