"""Schema diff operations for DSL-snapshot migrations.

Defines frozen dataclasses representing atomic schema changes,
used to compute and apply migrations between DSL snapshots.
"""

from dataclasses import dataclass
from typing import Any


class RenameResolutionError(Exception):
    """Raised when a rename hint references an old name that cannot be found in prev.

    This indicates a ``was:`` annotation whose referenced old name is neither in
    the previous snapshot (pending rename) nor already absent (already-applied).
    The entity/field name and the unresolvable old name are both included in the
    message to make debugging straightforward.
    """


@dataclass(frozen=True)
class AddTable:
    """Add a new table with columns, foreign keys, indexes, and unique constraints."""

    table: str
    columns: dict[str, Any]
    # #1464: composite-aware. fks = [(cols, ref_table, ref_cols), ...];
    # uniques = [(col, ...), ...]. indexes = ["col[,col]", ...] (comma-joined).
    fks: list[Any]
    indexes: list[str]
    uniques: list[Any]


@dataclass(frozen=True)
class DropTable:
    """Drop a table. Carries prior table snapshot for downgrade."""

    table: str
    snap: dict[str, Any]


@dataclass(frozen=True)
class RenameTable:
    """Rename a table."""

    old: str
    new: str


@dataclass(frozen=True)
class AddColumn:
    """Add a column to a table."""

    table: str
    name: str
    col: dict[str, Any]


@dataclass(frozen=True)
class DropColumn:
    """Drop a column. Carries prior column snapshot for downgrade."""

    table: str
    name: str
    col: dict[str, Any]


@dataclass(frozen=True)
class RenameColumn:
    """Rename a column."""

    table: str
    old: str
    new: str


@dataclass(frozen=True)
class AlterColumn:
    """Alter a column's specification."""

    table: str
    name: str
    old: dict[str, Any]
    new: dict[str, Any]


@dataclass(frozen=True)
class AddForeignKey:
    """Add a (possibly composite) foreign key constraint (#1464)."""

    table: str
    columns: tuple[str, ...]
    ref_table: str
    ref_columns: tuple[str, ...]


@dataclass(frozen=True)
class DropForeignKey:
    """Drop a (possibly composite) foreign key constraint (#1464)."""

    table: str
    columns: tuple[str, ...]
    ref_table: str
    ref_columns: tuple[str, ...]


@dataclass(frozen=True)
class AddIndex:
    """Add an index on a column."""

    table: str
    column: str


@dataclass(frozen=True)
class DropIndex:
    """Drop an index on a column."""

    table: str
    column: str


@dataclass(frozen=True)
class AddUnique:
    """Add a (possibly composite) unique constraint (#1464)."""

    table: str
    columns: tuple[str, ...]


@dataclass(frozen=True)
class DropUnique:
    """Drop a (possibly composite) unique constraint (#1464)."""

    table: str
    columns: tuple[str, ...]


SchemaOp = (
    AddTable
    | DropTable
    | RenameTable
    | AddColumn
    | DropColumn
    | RenameColumn
    | AlterColumn
    | AddForeignKey
    | DropForeignKey
    | AddIndex
    | DropIndex
    | AddUnique
    | DropUnique
)

# ---------------------------------------------------------------------------
# Type aliases mirroring schema_snapshot.py conventions
# ---------------------------------------------------------------------------

#: ColSnap keys: type (str), nullable (bool), default (str|None), pk (bool)
ColSnap = dict[str, Any]

#: TableSnap keys: columns (dict[str, ColSnap]),
#:   fks (list[(cols, ref_table, ref_cols)] — composite-aware, #1464; legacy
#:        dict[col, table] is accepted + upgraded by _coerce_fks),
#:   uniques (list[(col, ...)] — legacy list[str] upgraded by _coerce_uniques),
#:   indexes (list[str] — comma-joined columns)
TableSnap = dict[str, Any]

#: Snapshot: table-name → TableSnap
Snapshot = dict[str, TableSnap]

#: Rename hints passed to diff().
#: ``tables``  maps new_table_name  → old_table_name
#: ``columns`` maps (table_new_name, col_new_name) → col_old_name
RenameHints = dict[str, Any]


def _empty_hints() -> RenameHints:
    return {"tables": {}, "columns": {}}


def _resolve_table_renames(
    prev: Snapshot,
    curr: Snapshot,
    table_hints: dict[str, str],
) -> tuple[list[SchemaOp], dict[str, str]]:
    """Resolve table-level rename hints.

    Returns:
        rename_ops: RenameTable ops for pending renames.
        table_prev_name: mapping of curr_name → prev_name for renamed tables.
    """
    prev_tables = set(prev)
    curr_tables = set(curr)
    rename_ops: list[SchemaOp] = []
    table_prev_name: dict[str, str] = {}

    for new_tname in sorted(curr_tables - prev_tables):
        if new_tname not in table_hints:
            continue
        old_tname = table_hints[new_tname]
        if old_tname in prev_tables:
            rename_ops.append(RenameTable(old=old_tname, new=new_tname))
            table_prev_name[new_tname] = old_tname
        else:
            raise RenameResolutionError(
                f"Table rename hint for '{new_tname}': old name '{old_tname}' "
                f"not found in previous snapshot and '{new_tname}' not already present."
            )

    return rename_ops, table_prev_name


def _resolve_column_renames(
    curr_tname: str,
    prev_cols: dict[str, ColSnap],
    curr_cols: dict[str, ColSnap],
    col_hints: dict[tuple[str, str], str],
) -> tuple[list[SchemaOp], list[SchemaOp], set[str], set[str]]:
    """Resolve column-level rename hints for a single table.

    Returns:
        rename_ops: RenameColumn ops for pending renames.
        alter_ops: AlterColumn ops for renames that also changed type/spec.
        renamed_old_cols: old column names consumed by renames (exclude from drop).
        renamed_new_cols: new column names produced by renames (exclude from add).
    """
    prev_col_names = set(prev_cols)
    curr_col_names = set(curr_cols)
    rename_ops: list[SchemaOp] = []
    alter_ops: list[SchemaOp] = []
    renamed_old_cols: set[str] = set()
    renamed_new_cols: set[str] = set()

    for new_cname in sorted(curr_col_names - prev_col_names):
        hint_key = (curr_tname, new_cname)
        if hint_key not in col_hints:
            continue
        old_cname = col_hints[hint_key]
        if old_cname in prev_col_names:
            rename_ops.append(RenameColumn(table=curr_tname, old=old_cname, new=new_cname))
            renamed_old_cols.add(old_cname)
            renamed_new_cols.add(new_cname)
            # If spec also changed, emit AlterColumn on the NEW name (runs after rename).
            if prev_cols[old_cname] != curr_cols[new_cname]:
                alter_ops.append(
                    AlterColumn(
                        table=curr_tname,
                        name=new_cname,
                        old=prev_cols[old_cname],
                        new=curr_cols[new_cname],
                    )
                )
        elif new_cname in prev_col_names:
            # Already-applied: new col already exists in prev — no-op
            renamed_new_cols.add(new_cname)
        else:
            raise RenameResolutionError(
                f"Column rename hint for '{curr_tname}.{new_cname}': "
                f"old name '{old_cname}' not found in previous snapshot "
                f"and '{new_cname}' not already present."
            )

    return rename_ops, alter_ops, renamed_old_cols, renamed_new_cols


def _diff_columns(
    curr_tname: str,
    prev_cols: dict[str, ColSnap],
    curr_cols: dict[str, ColSnap],
    exclude_old: set[str],
    exclude_new: set[str],
) -> tuple[list[SchemaOp], list[SchemaOp], list[SchemaOp]]:
    """Diff columns for a single table, excluding rename participants.

    Returns:
        add_ops: AddColumn ops for genuinely new columns.
        alter_ops: AlterColumn ops for same-name columns with changed spec.
        drop_ops: DropColumn ops for removed columns.
    """
    prev_col_names = set(prev_cols)
    curr_col_names = set(curr_cols)
    add_ops: list[SchemaOp] = []
    alter_ops: list[SchemaOp] = []
    drop_ops: list[SchemaOp] = []

    for cname in sorted(curr_col_names - prev_col_names):
        if cname not in exclude_new:
            add_ops.append(AddColumn(table=curr_tname, name=cname, col=curr_cols[cname]))

    for cname in sorted(prev_col_names & curr_col_names):
        if prev_cols[cname] != curr_cols[cname]:
            alter_ops.append(
                AlterColumn(
                    table=curr_tname,
                    name=cname,
                    old=prev_cols[cname],
                    new=curr_cols[cname],
                )
            )

    for cname in sorted(prev_col_names - curr_col_names):
        if cname not in exclude_old:
            drop_ops.append(DropColumn(table=curr_tname, name=cname, col=prev_cols[cname]))

    return add_ops, alter_ops, drop_ops


def _coerce_fks(snap: TableSnap) -> set[tuple[tuple[str, ...], str, tuple[str, ...]]]:
    """Normalize a snapshot's ``fks`` to the composite set shape (#1464).

    Accepts both the current composite shape (``[(cols, ref_table, ref_cols), ...]``)
    and the legacy per-column shape (``{col: ref_table}``) embedded in pre-#1464
    baselines — the latter upgrades to single-column FKs referencing the PK ``id``
    (what the old engine always assumed), so an incremental ``db revision`` against
    an old baseline doesn't see a spurious drop+re-add of every FK.
    """
    raw = snap.get("fks", [])
    if isinstance(raw, dict):  # legacy {col: ref_table}
        return {((col,), tbl, ("id",)) for col, tbl in raw.items()}
    return {(tuple(cols), tbl, tuple(refcols)) for cols, tbl, refcols in raw}


def _coerce_uniques(snap: TableSnap) -> set[tuple[str, ...]]:
    """Normalize a snapshot's ``uniques`` to a set of column tuples (#1464).

    Accepts the current shape (``[(col, ...), ...]``) and the legacy flat shape
    (``["col", ...]`` — single-column names), upgrading each bare name to a
    one-column tuple.
    """
    raw = snap.get("uniques", [])
    return {(c,) if isinstance(c, str) else tuple(c) for c in raw}


def _diff_constraints(
    curr_tname: str,
    prev_snap: TableSnap,
    curr_snap: TableSnap,
) -> tuple[list[SchemaOp], list[SchemaOp]]:
    """Diff FK, index, and unique constraints for a single table.

    Returns:
        add_ops: AddForeignKey / AddIndex / AddUnique ops.
        drop_ops: DropForeignKey / DropIndex / DropUnique ops.
    """
    add_ops: list[SchemaOp] = []
    drop_ops: list[SchemaOp] = []

    prev_fk_set = _coerce_fks(prev_snap)
    curr_fk_set = _coerce_fks(curr_snap)
    for cols, ref, refcols in sorted(curr_fk_set - prev_fk_set):
        add_ops.append(
            AddForeignKey(table=curr_tname, columns=cols, ref_table=ref, ref_columns=refcols)
        )
    for cols, ref, refcols in sorted(prev_fk_set - curr_fk_set):
        drop_ops.append(
            DropForeignKey(table=curr_tname, columns=cols, ref_table=ref, ref_columns=refcols)
        )

    prev_indexes = set(prev_snap.get("indexes", []))
    curr_indexes = set(curr_snap.get("indexes", []))
    for col in sorted(curr_indexes - prev_indexes):
        add_ops.append(AddIndex(table=curr_tname, column=col))
    for col in sorted(prev_indexes - curr_indexes):
        drop_ops.append(DropIndex(table=curr_tname, column=col))

    prev_uniques = _coerce_uniques(prev_snap)
    curr_uniques = _coerce_uniques(curr_snap)
    for cols in sorted(curr_uniques - prev_uniques):
        add_ops.append(AddUnique(table=curr_tname, columns=cols))
    for cols in sorted(prev_uniques - curr_uniques):
        drop_ops.append(DropUnique(table=curr_tname, columns=cols))

    return add_ops, drop_ops


def diff(
    prev: Snapshot,
    curr: Snapshot,
    hints: RenameHints | None = None,
) -> list[SchemaOp]:
    """Return a minimal ordered list of SchemaOps to evolve *prev* into *curr*.

    Ordering contract:
        RenameTable
        → AddTable
        → RenameColumn / AddColumn / AddForeignKey / AddIndex / AddUnique
        → AlterColumn
        → DropColumn / DropForeignKey / DropIndex / DropUnique
        → DropTable

    Rename resolution (``hints``):
    - Table rename: ``hints["tables"][new] = old`` where ``old`` in prev AND
      ``new`` in curr AND ``new`` not in prev → emit ``RenameTable(old, new)``
      and diff the table's columns under the new name vs ``prev[old]``.
      Lifecycle: ``old`` not in prev but ``new`` in prev → already-applied
      no-op (skip). Neither case → ``RenameResolutionError``.
    - Column rename: ``hints["columns"][(table, new)] = old`` where ``old`` in
      ``prev[table].columns`` AND ``new`` in ``curr[table].columns`` AND ``new``
      not in ``prev[table].columns`` → emit ``RenameColumn(table, old, new)``
      (no drop+add). Lifecycle: ``old`` not in prev cols but ``new`` in prev
      cols → already-applied no-op. Neither → ``RenameResolutionError``.

    Pure: no DB, no Alembic, no I/O.
    """
    h = hints or _empty_hints()
    table_hints: dict[str, str] = h.get("tables", {})
    col_hints: dict[tuple[str, str], str] = h.get("columns", {})

    prev_tables = set(prev)
    curr_tables = set(curr)

    # --- 1. Resolve table renames -------------------------------------------
    rename_ops, table_prev_name = _resolve_table_renames(prev, curr, table_hints)

    # --- 2. Drop tables (not consumed by rename) ----------------------------
    renamed_old_tables = set(table_prev_name.values())
    drop_tables: list[SchemaOp] = [
        DropTable(table=tname, snap=prev[tname])
        for tname in sorted(prev_tables - curr_tables)
        if tname not in renamed_old_tables
    ]

    # --- 3. Add tables (not resolved via rename) ----------------------------
    # A new table's FKs, indexes and unique constraints are emitted as SEPARATE
    # ops (rendered post-create), NOT inline in the create_table — so the engine
    # creates every table first, then wires constraints/indexes. This makes
    # circular and self-referential FKs work without inline-create special-casing
    # and ensures a baseline reproduces create_all exactly (indexes + uniques are
    # otherwise silently dropped, since _render_add_table renders columns only).
    # These ops are ordered immediately after all AddTable ops (below) so every
    # referenced table exists by the time its FK/index/constraint is added.
    add_tables: list[SchemaOp] = []
    add_table_constraints: list[SchemaOp] = []
    for tname in sorted(curr_tables - prev_tables):
        if tname not in table_prev_name:
            tsnap = curr[tname]
            fk_specs = sorted(_coerce_fks(tsnap))
            unique_specs = sorted(_coerce_uniques(tsnap))
            add_tables.append(
                AddTable(
                    table=tname,
                    columns=dict(tsnap.get("columns", {})),
                    fks=fk_specs,
                    indexes=list(tsnap.get("indexes", [])),
                    uniques=unique_specs,
                )
            )
            for cols, ref, refcols in fk_specs:
                add_table_constraints.append(
                    AddForeignKey(table=tname, columns=cols, ref_table=ref, ref_columns=refcols)
                )
            for idx_cols in sorted(tsnap.get("indexes", [])):
                add_table_constraints.append(AddIndex(table=tname, column=idx_cols))
            for cols in unique_specs:
                add_table_constraints.append(AddUnique(table=tname, columns=cols))

    # --- 4. Diff columns + constraints for common/renamed table pairs -------
    add_details: list[SchemaOp] = []
    alters: list[SchemaOp] = []
    drop_details: list[SchemaOp] = []

    common_pairs: list[tuple[str, str]] = [
        (t, t) for t in sorted(prev_tables & curr_tables)
    ] + sorted(table_prev_name.items())

    for curr_tname, prev_tname in sorted(common_pairs):
        prev_snap = prev[prev_tname]
        curr_snap = curr[curr_tname]
        prev_cols: dict[str, ColSnap] = prev_snap.get("columns", {})
        curr_cols: dict[str, ColSnap] = curr_snap.get("columns", {})

        col_renames, col_rename_alters, renamed_old_cols, renamed_new_cols = (
            _resolve_column_renames(curr_tname, prev_cols, curr_cols, col_hints)
        )
        col_adds, col_alters, col_drops = _diff_columns(
            curr_tname, prev_cols, curr_cols, renamed_old_cols, renamed_new_cols
        )
        constraint_adds, constraint_drops = _diff_constraints(curr_tname, prev_snap, curr_snap)

        add_details.extend(col_renames + col_adds + constraint_adds)
        alters.extend(col_rename_alters + col_alters)
        drop_details.extend(col_drops + constraint_drops)

    return (
        rename_ops
        + add_tables
        + add_table_constraints
        + add_details
        + alters
        + drop_details
        + drop_tables
    )
