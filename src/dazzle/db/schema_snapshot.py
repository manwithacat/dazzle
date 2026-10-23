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
TableSnap = dict with keys: columns (dict[str, ColSnap]),
                             fks (list[(cols, ref_table, ref_cols)] — composite-aware, #1464),
                             uniques (list[(col, ...)] — column tuples),
                             indexes (list[str] — comma-joined columns, deduped)
Snapshot  = dict[str, TableSnap]   — keyed by table name (verbatim)

All dict keys and lists are sorted for deterministic comparison.
"""

from __future__ import annotations

import logging
import pprint
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any

import sqlalchemy as sa

logger = logging.getLogger(__name__)

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


def _table_fks(table: Any) -> list[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    """Composite-aware FK extraction (#1464).

    Read TABLE-level ForeignKeyConstraints, not per-column ``.foreign_keys``, so a
    shared_schema composite intra-tenant FK ``(tenant_id, fk) → Parent(tenant_id,
    id)`` is captured whole — constrained columns, ref table, and ref columns (in
    order). The per-column model dropped the second leg + the referred columns.
    """
    fks: list[tuple[tuple[str, ...], str, tuple[str, ...]]] = []
    for fkc in table.foreign_key_constraints:
        elements = list(fkc.elements)
        if not elements:
            continue
        fks.append(
            (
                tuple(fkc.column_keys),
                elements[0].column.table.name,
                tuple(e.column.name for e in elements),
            )
        )
    return fks


def _table_uniques(table: Any) -> set[tuple[str, ...]]:
    """Composite-aware UNIQUE extraction (#1464).

    Each UNIQUE is captured as its column TUPLE so ``UNIQUE(tenant_id, id)`` stays
    one composite constraint (was flattened to a column-name set → rendered as two
    bogus single-column uniques, incl. the unusable ``UNIQUE(tenant_id)``).
    """
    uniques: set[tuple[str, ...]] = set()
    for col in table.columns:
        if col.unique:  # inline `unique=True` (None when not set)
            uniques.add((col.name,))
    for constraint in table.constraints:
        if isinstance(constraint, sa.UniqueConstraint):
            cols_t = tuple(c.name for c in constraint.columns)
            if cols_t:
                uniques.add(cols_t)
    return uniques


def _table_index_keys(table: Any) -> set[str]:
    """Index column-keys (comma-joined, columns sorted), de-duplicated.

    Sorting columns means ``(tenant_id, status)`` and ``(status, tenant_id)`` map to
    one key (accepted phase-1 limitation: column-order changes not detected). The set
    de-dupes so two metadata indexes over the same columns don't double-emit
    ``create_index`` → ``DuplicateTable`` at upgrade (#1464).
    """
    return {",".join(sorted(c.name for c in idx.columns)) for idx in table.indexes}


def _table_checks(table: Any) -> list[tuple[str, str]]:
    """Named CHECK constraints as (name, sqltext) sorted (#1620 exclusive FKs)."""
    rows: list[tuple[str, str]] = []
    for constraint in table.constraints:
        if not isinstance(constraint, sa.CheckConstraint):
            continue
        name = getattr(constraint, "name", None)
        if not name:
            continue
        # sqltext may be TextClause / ColumnElement
        sql = getattr(constraint, "sqltext", None)
        if sql is None:
            continue
        rows.append((str(name), str(sql)))
    return sorted(rows)


def project_schema(
    metadata: sa.MetaData,
    table_filter: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    """Introspect *metadata* and return a deterministic plain-dict Snapshot.

    This is a **pure** function: it touches only the in-memory MetaData
    object, never the database or the filesystem.  Unit tests can pass a
    hand-built MetaData; production code passes the result of
    ``load_target_metadata()``.

    *table_filter*, when given, is called with each table name; tables for which
    it returns ``False`` are omitted from the snapshot. The baseline generator
    uses this to exclude framework-owned tables (the framework baseline migration
    creates those) while still producing project-table create ops.

    The Snapshot structure::

        {
            "<TableName>": {
                "columns": {
                    "<col>": {"type": str, "nullable": bool,
                              "default": str | None, "pk": bool},
                    ...
                },
                # #1464: composite-aware. Each FK is (constrained cols, ref table,
                # ref cols); each unique is a column tuple — so shared_schema composite
                # tenant-scoped FKs `(tenant_id, fk) → Parent(tenant_id, id)` and
                # `UNIQUE(tenant_id, id)` round-trip faithfully.
                "fks":     [[["<col>", ...], "<RefTable>", ["<refcol>", ...]], ...],  # sorted
                "uniques": [["<col>", ...], ...],   # sorted column tuples
                "indexes": ["<col>[,<col>]", ...],  # sorted, comma-joined, deduped
            },
            ...
        }
    """
    snapshot: dict[str, Any] = {}

    for table in metadata.sorted_tables:
        if table_filter is not None and not table_filter(table.name):
            continue
        # --- columns ---
        columns: dict[str, Any] = {}
        for col in table.columns:
            columns[col.name] = {
                "type": _sa_type_to_token(col.type),
                "nullable": bool(col.nullable),
                "default": _render_server_default(col.server_default),
                "pk": bool(col.primary_key),
            }

        snapshot[table.name] = {
            "columns": dict(sorted(columns.items())),
            "fks": sorted(_table_fks(table)),
            "uniques": sorted(_table_uniques(table)),
            "indexes": sorted(_table_index_keys(table)),
            # #1620: named CHECK constraints (exclusive-anchor exactly-one)
            "checks": _table_checks(table),
        }

    return dict(sorted(snapshot.items()))


# ---------------------------------------------------------------------------
# Convenience wrapper: project the live project's schema
# ---------------------------------------------------------------------------


def project_current(table_filter: Callable[[str], bool] | None = None) -> dict[str, Any]:
    """Return the Snapshot for the Dazzle project in the current directory.

    Delegates to ``load_target_metadata()`` (the same builder Alembic uses for
    ``--autogenerate``) so the snapshot is always consistent with the real
    schema, including shared_schema ``tenant_id`` / composite-FK / index
    injections — no exclusion list required.

    *table_filter* is forwarded to :func:`project_schema` (the baseline generator
    passes the framework-table exclusion predicate so framework-owned tables —
    created by the framework baseline migration — are not re-created).
    """
    from dazzle.http.alembic.metadata_loader import load_target_metadata

    return project_schema(load_target_metadata(), table_filter=table_filter)


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
    """Introspect a live Postgres DB via SQLAlchemy inspector → rich Snapshot.

    Unlike ``project_schema`` (which reads in-memory MetaData and uses a lossy
    comma-joined column-name list for indexes), this function reads the **actual
    live database** and captures indexes in a richer, name-keyed format that
    preserves the index name, uniqueness flag, and partial-index WHERE predicate.

    This richer format is used exclusively by the three-way framework-baseline
    parity gate (``tests/integration/test_framework_baseline_parity_pg.py``) and
    the committed ``FRAMEWORK_SCHEMA_SNAPSHOT``.  It is intentionally **separate**
    from ``project_schema``'s lossy ``indexes: list[str]`` format, which is used
    by the #1431 app-entity migration-diffing path.  Do not conflate the two.

    Index representation (richer than ``project_schema``):
        ``indexes`` is a ``dict[str, dict]`` keyed by index name::

            {
                "idx_users_email": {"unique": False, "columns": ["email"], "predicate": None},
                "users_email_key": {"unique": True,  "columns": ["email"], "predicate": None},
                "ix_process_runs_due": {
                    "unique": False, "columns": ["deliver_at"],
                    "predicate": "(status = ANY (ARRAY['pending'::text, 'claimed'::text]))",
                },
            }

        Key properties:
        - Keyed by name → dropping one of two same-column indexes registers as a diff.
        - ``unique`` flag → a non-unique→unique promotion is caught.
        - ``predicate`` → any WHERE-clause change is caught.
        - Column order is preserved (not sorted) so that functional-index column
          order changes are not silently collapsed.

    Args:
        conn:
            A SQLAlchemy ``Engine``.  Pass the result of ``sa.create_engine(url)``.
        only:
            Optional set of table names to include.  Tables not in this set
            are silently skipped.  ``None`` means include every table found.

    Returns:
        A deterministic rich ``Snapshot`` dict (sorted keys at every level).
    """
    engine = conn  # accept Engine; inspector works on Engine directly

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

        # ── indexes (rich: name-keyed, captures unique + predicate) ──────────
        # Each entry: {name: {unique: bool, columns: list[str], predicate: str|None}}
        # Using a dict keyed by name so that two indexes on the same column set
        # are distinct entries (prevents the false-green where dropping one of two
        # same-column indexes collapses under a set() comparison).
        indexes: dict[str, Any] = {}
        for idx in insp.get_indexes(tname):
            iname: str = idx["name"]
            col_names: list[str] = [str(c) for c in (idx.get("column_names") or [])]
            if not col_names:
                # Functional/expression indexes with no column_names are skipped
                # (cannot be round-tripped through the column-name representation).
                continue
            is_unique: bool = bool(idx.get("unique", False))
            # Partial-index WHERE predicate is in dialect_options under the key
            # 'postgresql_where'.  None when the index is not partial.
            predicate: str | None = (idx.get("dialect_options") or {}).get("postgresql_where")
            indexes[iname] = {
                "unique": is_unique,
                "columns": col_names,
                "predicate": predicate,
            }

        # ── unique constraints (named table-level uniques) ────────────────────
        unique_cols: set[str] = set()
        for uc in insp.get_unique_constraints(tname):
            for col in uc.get("column_names", []):
                unique_cols.add(col)

        snapshot[tname] = {
            "columns": dict(sorted(columns.items())),
            "fks": dict(sorted(fks.items())),
            "uniques": sorted(unique_cols),
            "indexes": dict(sorted(indexes.items())),
        }

    return dict(sorted(snapshot.items()))


@dataclass(frozen=True)
class SnapshotLocation:
    """Where the engine's previous ``SCHEMA_SNAPSHOT`` was found (#1846).

    Attributes
    ----------
    snapshot:
        The embedded snapshot, or ``{}`` when no project-lineage revision
        reachable from the head carries one.
    revision:
        The revision id that carries *snapshot* (``None`` when none was found).
    head:
        The head the walk started from (``None`` when there are no heads).
    unsnapshotted:
        Project-lineage, non-merge revisions passed over between the head and
        the carrier (hand-authored ``--no-autogenerate`` revisions, or ones whose
        snapshot was stripped). Schema they changed is **not** in *snapshot*, so
        a DSL-modelled change they made reappears in the next diff. Empty in the
        normal engine flow.
    ambiguous:
        True when parents of a merge led to *different* snapshots at the same
        distance (two project branches merged); the first parent's (in
        ``down_revision`` order) is used.
    """

    snapshot: dict[str, Any]
    revision: str | None
    head: str | None
    unsnapshotted: tuple[str, ...] = ()
    ambiguous: bool = False


def _framework_versions_dir() -> Path | None:
    """The framework's own alembic ``versions`` directory (``dazzle/http/alembic/versions``).

    Resolved from this file's location rather than by importing
    ``dazzle.http.alembic`` (keeps ``dazzle.db`` free of an ``http`` import).
    """
    path = Path(__file__).resolve().parents[1] / "http" / "alembic" / "versions"
    return path if path.is_dir() else None


def _is_framework_script(script: Any, framework_dir: Path | None) -> bool:
    """True if *script* is a framework-lineage revision (lives in the framework dir).

    Framework revisions never carry ``SCHEMA_SNAPSHOT`` (the project snapshot is
    written only into the project's ``.dazzle/migrations/versions``), and their
    parents are framework revisions too, so the walk never needs to descend
    into them.
    """
    path = getattr(script, "path", None)
    if framework_dir is None or not isinstance(path, str):
        return False
    return Path(path).resolve().parent == framework_dir


def _parent_ids(script: Any) -> tuple[str, ...]:
    """Parent revision ids of *script*, in ``down_revision`` order."""
    down = getattr(script, "down_revision", None)
    if isinstance(down, str):
        return (down,)
    if isinstance(down, (tuple, list)):
        return tuple(str(d) for d in down if isinstance(d, str) and d)
    return ()


def locate_snapshot(script_dir: Any, start: str) -> SnapshotLocation:
    """Walk down from revision *start* to the nearest revision carrying a snapshot.

    Breadth-first over ``down_revision`` (parents visited in tuple order, so the
    result is deterministic): the first level that holds a snapshot-bearing
    revision wins. Framework-lineage revisions are skipped and not descended
    into — they never carry the project snapshot (#1846: the
    ``reconcile-baseline`` merge revises ``(<framework head>, <project rev>)``
    and carries no snapshot itself, so the walk passes through it to the
    project parent).
    """
    framework_dir = _framework_versions_dir()
    level: list[str] = [start]
    seen: set[str] = set()
    unsnapshotted: list[str] = []
    while level:
        found: list[tuple[str, dict[str, Any]]] = []
        next_level: list[str] = []
        for rev_id in level:
            if rev_id in seen:
                continue
            seen.add(rev_id)
            script = script_dir.get_revision(rev_id)
            if script is None or _is_framework_script(script, framework_dir):
                continue
            snap = snapshot_from_module(script.module)
            if snap:
                found.append((rev_id, snap))
                continue
            parents = _parent_ids(script)
            if len(parents) <= 1:
                unsnapshotted.append(rev_id)
            next_level.extend(p for p in parents if p not in seen)
        if found:
            rev_id, snap = found[0]
            ambiguous = any(other != snap for _, other in found[1:])
            if ambiguous:
                logger.warning(
                    "merge parents carry different SCHEMA_SNAPSHOTs (%s); diffing against %s",
                    ", ".join(r for r, _ in found),
                    rev_id,
                )
            return SnapshotLocation(
                snapshot=snap,
                revision=rev_id,
                head=start,
                unsnapshotted=tuple(unsnapshotted),
                ambiguous=ambiguous,
            )
        level = next_level
    return SnapshotLocation(
        snapshot={}, revision=None, head=start, unsnapshotted=tuple(unsnapshotted)
    )


def find_head_snapshot(script_dir: Any) -> SnapshotLocation:
    """Locate the previous snapshot for the next revision (see :func:`load_head_snapshot`)."""
    heads: list[str] = list(script_dir.get_heads())
    first: SnapshotLocation | None = None
    for head_rev in heads:
        loc = locate_snapshot(script_dir, head_rev)
        if loc.snapshot:
            return loc
        if first is None:
            first = loc
    return first or SnapshotLocation(snapshot={}, revision=None, head=None)


def load_head_snapshot(script_dir: Any) -> dict[str, Any]:
    """Return the project's previous ``SCHEMA_SNAPSHOT`` for the next revision.

    Resolves the head revision(s) from *script_dir* (an
    ``alembic.script.ScriptDirectory`` instance) and, from each head, walks
    down the revision graph to the nearest project-lineage revision whose
    module carries ``SCHEMA_SNAPSHOT`` (:func:`locate_snapshot`).

    **Snapshot-less heads (#1846)**: ``dazzle db reconcile-baseline`` writes a
    merge revision whose ``down_revision`` is ``(<framework head>, <project
    rev>)``. A merge changes no schema, so the snapshot of its project parent
    is the post-merge state; the walk passes through the merge (and through
    hand-authored ``--no-autogenerate`` revisions, which are reported as
    ``unsnapshotted`` by :func:`find_head_snapshot`) to reach it. Framework
    lineage revisions never carry a project snapshot and are not descended.

    **Multi-head (dual-lineage)**: with two independent roots (see
    ``_guard_single_head`` in ``dazzle.cli.db``) the first head whose walk
    finds a snapshot wins.

    Returns ``{}`` when there is no head, or when no reachable project revision
    carries a snapshot (a project that predates the engine and has not run
    ``dazzle db snapshot-baseline``). ``dazzle db revision`` refuses to diff
    against ``{}`` when the database already holds project tables.
    """
    return find_head_snapshot(script_dir).snapshot


def merge_inherited_snapshot(script_dir: Any, heads: list[str]) -> tuple[str | None, str]:
    """The snapshot literal a ``reconcile-baseline`` merge inherits, or why none (#1846).

    Returns ``(literal, "")`` or ``(None, reason)``. A merge changes no schema,
    so its post-state is the union of its parents'. Framework-lineage parents
    carry no project snapshot, so when exactly one parent's walk finds one, with
    no snapshot-less project revision in between (whose changes the snapshot
    would not reflect), that snapshot is the merge's state. Deliberately not the
    live DSL projection: DSL edits not yet migrated must still diff next time.
    """
    found = [loc for loc in (locate_snapshot(script_dir, h) for h in heads) if loc.snapshot]
    if not found:
        return None, (
            "no merged lineage carries one; run `dazzle db snapshot-baseline` before "
            "the next `dazzle db revision`."
        )
    if any(loc.snapshot != found[0].snapshot for loc in found[1:]):
        return None, "more than one merged lineage carries a snapshot, and they differ."
    loc = found[0]
    if loc.ambiguous:
        return None, f"merge parents below {loc.head} carry different snapshots."
    if loc.unsnapshotted:
        return None, (
            f"the nearest one ({loc.revision}) predates revision(s) without a snapshot "
            f"({', '.join(loc.unsnapshotted)}); run `dazzle db snapshot-baseline` while "
            "the DSL matches the database, before the next `dazzle db revision`."
        )
    return render_snapshot_literal(loc.snapshot), ""
