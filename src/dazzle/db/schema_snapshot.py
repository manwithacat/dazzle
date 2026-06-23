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

import pprint
from types import ModuleType
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


# ---------------------------------------------------------------------------
# Serialization and deserialization
# ---------------------------------------------------------------------------


def render_snapshot_literal(snapshot: dict[str, Any]) -> str:
    """Return a deterministic Python source literal of the snapshot dict.

    Uses ``pprint.pformat()`` with sorted keys and stable formatting
    (width=88) so that the same input always produces identical output,
    suitable for embedding as ``SCHEMA_SNAPSHOT = <literal>`` in a migration
    file.

    The returned string is valid Python that can be ``eval()``'d back to
    the original dict (in test contexts only; in production, use
    ``snapshot_from_module()`` to import it).
    """
    return pprint.pformat(snapshot, sort_dicts=True, width=88)


def snapshot_from_module(module: ModuleType) -> dict[str, Any]:
    """Extract the SCHEMA_SNAPSHOT attribute from a module.

    Returns the snapshot dict if present, or an empty dict if the module
    has no ``SCHEMA_SNAPSHOT`` attribute. This is the canonical way to load
    a snapshot that was rendered via ``render_snapshot_literal()`` into a
    migration module.
    """
    return getattr(module, "SCHEMA_SNAPSHOT", {})


def introspect_schema(
    conn: Any,
    *,
    only: set[str] | None = None,
) -> dict[str, Any]:
    """Introspect a live Postgres DB via SQLAlchemy inspector → Snapshot.

    Produces the same ``Snapshot`` / ``TableSnap`` / ``ColSnap`` shape as
    ``project_schema`` so the two outputs are directly comparable and can be
    fed to ``schema_diff.diff``.

    Unlike ``project_schema`` (which reads in-memory MetaData), this function
    reads the **actual live database** — making it suitable for the three-way
    parity gate (alembic-head ≡ orchestrator ≡ committed snapshot).

    Args:
        conn:
            A SQLAlchemy ``Connection`` or ``Engine``, or a psycopg connection
            that has been wrapped by ``sqlalchemy.inspect``.  Concretely:
            pass the result of ``sa.create_engine(url)`` or
            ``engine.connect().__enter__()``.
        only:
            Optional set of table names to include.  Tables not in this set
            are silently skipped.  Use this to restrict to the in-scope
            framework tables and exclude ops-DB, event-bus-prefixed, and
            app-entity tables.  ``None`` means include every table found.

    Returns:
        A deterministic ``Snapshot`` dict (sorted keys at every level), ready
        for ``render_snapshot_literal`` or ``diff``.

    Type-normalisation:
        Column types from the inspector are SA dialect objects (TEXT, JSONB,
        TIMESTAMP, BOOLEAN, BIGINT, INTEGER, UUID …).  We reuse
        ``_sa_type_to_token`` — the same mapper used by ``project_schema`` —
        so that the same logical type compares equal regardless of build path.

    FK representation:
        The inspector's ``get_foreign_keys`` returns constraint dicts.  We
        capture ``col → referred_table`` (one entry per constrained column),
        matching ``project_schema``'s ``fks`` convention.

    Index representation:
        Each index becomes a comma-joined, sorted string of its column names
        (e.g. ``"tenant_id,user_id"``), matching ``project_schema``'s
        ``indexes`` convention.  Unique indexes are also emitted here;
        dedicated unique-constraint columns are captured in ``uniques``.

    Unique representation:
        ``get_unique_constraints`` returns named unique constraints.  We
        collapse each to the set of constrained column names, then record
        each column in ``uniques`` (matching ``project_schema``).  Columns
        marked ``unique=True`` inline are captured via the indexes list above
        (they appear as unique indexes in Postgres).
    """
    if isinstance(conn, sa.engine.Engine):
        engine = conn
        _owned = False
    else:
        # Assume it's already an inspectable connection
        engine = conn
        _owned = False

    insp = sa.inspect(engine)
    table_names = insp.get_table_names()

    snapshot: dict[str, Any] = {}

    for tname in table_names:
        if only is not None and tname not in only:
            continue

        # ── columns ──────────────────────────────────────────────────────────
        raw_cols = insp.get_columns(tname)
        pk_constraint = insp.get_pk_constraint(tname)
        pk_cols: set[str] = set(pk_constraint.get("constrained_columns", []))

        columns: dict[str, Any] = {}
        for c in raw_cols:
            # Inspector stores server default under 'default' key
            default_val: str | None = c.get("default")
            columns[c["name"]] = {
                "type": _sa_type_to_token(c["type"]),
                "nullable": bool(c["nullable"]),
                "default": default_val,
                "pk": c["name"] in pk_cols,
            }

        # ── foreign keys ──────────────────────────────────────────────────────
        fks: dict[str, str] = {}
        for fk_info in insp.get_foreign_keys(tname):
            ref_table = fk_info["referred_table"]
            for col in fk_info.get("constrained_columns", []):
                fks[col] = ref_table

        # ── indexes ───────────────────────────────────────────────────────────
        index_keys: list[str] = []
        for idx in insp.get_indexes(tname):
            col_names = idx.get("column_names") or []
            if col_names:
                index_keys.append(",".join(sorted(str(c) for c in col_names)))

        # ── unique constraints (named table-level uniques) ────────────────────
        unique_cols: set[str] = set()
        for uc in insp.get_unique_constraints(tname):
            for col in uc.get("column_names", []):
                unique_cols.add(col)

        snapshot[tname] = {
            "columns": dict(sorted(columns.items())),
            "fks": dict(sorted(fks.items())),
            "uniques": sorted(unique_cols),
            "indexes": sorted(index_keys),
        }

    return dict(sorted(snapshot.items()))


def load_head_snapshot(script_dir: Any) -> dict[str, Any]:
    """Return the SCHEMA_SNAPSHOT embedded in the project-lineage head revision.

    Resolves the head revision(s) from *script_dir* (an
    ``alembic.script.ScriptDirectory`` instance), loads their Python modules
    via ``Script.module``, and returns ``snapshot_from_module()`` for the head
    that carries ``SCHEMA_SNAPSHOT``.

    Returns ``{}`` in three safe-fallback cases:

    * No head exists (empty or uninitialised versions directory).
    * The head revision module has no ``SCHEMA_SNAPSHOT`` attribute — meaning
      the migration pre-dates the engine (Task 1.1) and adoption via the
      baseline-stamp command (Task 6.2) has not yet run.

    **Multi-head (dual-lineage) rule**: ``dazzle db`` chains the framework
    versions directory and the project versions directory into one
    ``ScriptDirectory``, yielding two heads when both lineages have
    independent roots (see ``_guard_single_head`` in ``dazzle.cli.db``).
    Only the project-lineage head carries ``SCHEMA_SNAPSHOT``; the framework
    head never does.  Resolution strategy: iterate all heads, return the
    ``SCHEMA_SNAPSHOT`` of the *first* head whose module exposes it, or
    ``{}`` if none does.  A merge migration (single head) is the normal
    post-``reconcile-baseline`` state and is handled by the same path.
    """
    heads: list[str] = list(script_dir.get_heads())
    for head_rev in heads:
        script = script_dir.get_revision(head_rev)
        if script is None:
            continue
        snap = snapshot_from_module(script.module)
        if snap:
            return snap
    return {}
