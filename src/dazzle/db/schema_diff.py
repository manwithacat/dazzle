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
    fks: dict[str, str]
    indexes: list[str]
    uniques: list[str]


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
    """Add a foreign key constraint."""

    table: str
    column: str
    ref_table: str


@dataclass(frozen=True)
class DropForeignKey:
    """Drop a foreign key constraint."""

    table: str
    column: str
    ref_table: str


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
    """Add a unique constraint on a column."""

    table: str
    column: str


@dataclass(frozen=True)
class DropUnique:
    """Drop a unique constraint on a column."""

    table: str
    column: str


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

#: TableSnap keys: columns (dict[str, ColSnap]), fks (dict[str, str]),
#:                 indexes (list[str]), uniques (list[str])
TableSnap = dict[str, Any]

#: Snapshot: table-name → TableSnap
Snapshot = dict[str, TableSnap]

#: Rename hints passed to diff().
#: ``tables``  maps new_table_name  → old_table_name
#: ``columns`` maps (table_new_name, col_new_name) → col_old_name
RenameHints = dict[str, Any]


def _empty_hints() -> RenameHints:
    return {"tables": {}, "columns": {}}


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

    rename_ops: list[SchemaOp] = []
    add_tables: list[SchemaOp] = []
    add_details: list[SchemaOp] = []  # AddColumn / AddFK / AddIndex / AddUnique
    alters: list[SchemaOp] = []
    drop_details: list[SchemaOp] = []  # DropColumn / DropFK / DropIndex / DropUnique
    drop_tables: list[SchemaOp] = []

    # --- resolve table renames first ----------------------------------------
    # Build a mapping: curr_table_name → prev_table_name (after rename resolution)
    # Tables that are "matched" via rename are excluded from add/drop sets.
    table_prev_name: dict[str, str] = {}  # new_name → name to look up in prev

    prev_tables = set(prev)
    curr_tables = set(curr)

    # Tables appearing in curr but not prev — check if a rename hint resolves them
    for new_tname in sorted(curr_tables - prev_tables):
        if new_tname in table_hints:
            old_tname = table_hints[new_tname]
            if old_tname in prev_tables:
                # Pending rename: old exists in prev, new not in prev
                rename_ops.append(RenameTable(old=old_tname, new=new_tname))
                table_prev_name[new_tname] = old_tname
            else:
                # No already-applied branch here: this loop only sees tables in
                # (curr - prev), so new_tname is by construction NOT in prev. The
                # already-applied table rename (new already in both prev & curr)
                # falls through to the common-table path below, where it diffs to
                # an empty delta — a correct no-op.
                raise RenameResolutionError(
                    f"Table rename hint for '{new_tname}': old name '{old_tname}' "
                    f"not found in previous snapshot and '{new_tname}' not already present."
                )
        else:
            # Genuine new table — will be handled in add_tables loop below
            pass

    # Tables in prev but not curr — check if they were consumed by a rename
    renamed_old_tables = set(table_prev_name.values())

    for tname in sorted(prev_tables - curr_tables):
        if tname not in renamed_old_tables:
            drop_tables.append(DropTable(table=tname, snap=prev[tname]))

    # New tables (not resolved via rename)
    for tname in sorted(curr_tables - prev_tables):
        if tname not in table_prev_name:
            tsnap = curr[tname]
            add_tables.append(
                AddTable(
                    table=tname,
                    columns=dict(tsnap.get("columns", {})),
                    fks=dict(tsnap.get("fks", {})),
                    indexes=list(tsnap.get("indexes", [])),
                    uniques=list(tsnap.get("uniques", [])),
                )
            )

    # --- tables present in both (including renamed tables) ------------------
    # For renamed tables, diff curr[new] vs prev[old].
    # For unchanged-name tables, diff curr[t] vs prev[t].

    # Build the set of (curr_name, prev_name) pairs to diff
    common_pairs: list[tuple[str, str]] = []
    for tname in sorted(prev_tables & curr_tables):
        common_pairs.append((tname, tname))
    for new_tname, old_tname in sorted(table_prev_name.items()):
        common_pairs.append((new_tname, old_tname))

    for curr_tname, prev_tname in sorted(common_pairs):
        prev_snap = prev[prev_tname]
        curr_snap = curr[curr_tname]

        prev_cols: dict[str, ColSnap] = prev_snap.get("columns", {})
        curr_cols: dict[str, ColSnap] = curr_snap.get("columns", {})

        prev_col_names = set(prev_cols)
        curr_col_names = set(curr_cols)

        # --- resolve column renames within this table -----------------------
        # col_hints keys use the *current* table name
        renamed_old_cols: set[str] = set()
        renamed_new_cols: set[str] = set()

        for new_cname in sorted(curr_col_names - prev_col_names):
            hint_key = (curr_tname, new_cname)
            if hint_key in col_hints:
                old_cname = col_hints[hint_key]
                if old_cname in prev_col_names:
                    # Pending rename
                    add_details.append(RenameColumn(table=curr_tname, old=old_cname, new=new_cname))
                    renamed_old_cols.add(old_cname)
                    renamed_new_cols.add(new_cname)
                    # If the column spec also changed (type/nullable/default/pk),
                    # emit AlterColumn on the NEW name so it runs after the rename.
                    prev_col_snap = prev_cols[old_cname]
                    curr_col_snap = curr_cols[new_cname]
                    if prev_col_snap != curr_col_snap:
                        alters.append(
                            AlterColumn(
                                table=curr_tname,
                                name=new_cname,
                                old=prev_col_snap,
                                new=curr_col_snap,
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

        # added columns (excluding rename targets)
        for cname in sorted(curr_col_names - prev_col_names):
            if cname not in renamed_new_cols:
                add_details.append(AddColumn(table=curr_tname, name=cname, col=curr_cols[cname]))

        # altered columns (same name, different spec)
        for cname in sorted(prev_col_names & curr_col_names):
            if prev_cols[cname] != curr_cols[cname]:
                alters.append(
                    AlterColumn(
                        table=curr_tname,
                        name=cname,
                        old=prev_cols[cname],
                        new=curr_cols[cname],
                    )
                )

        # dropped columns (excluding rename sources)
        for cname in sorted(prev_col_names - curr_col_names):
            if cname not in renamed_old_cols:
                drop_details.append(DropColumn(table=curr_tname, name=cname, col=prev_cols[cname]))

        # FK diffs: fks is dict[col → ref_table]
        prev_fks: dict[str, str] = prev_snap.get("fks", {})
        curr_fks: dict[str, str] = curr_snap.get("fks", {})
        prev_fk_set = set(prev_fks.items())
        curr_fk_set = set(curr_fks.items())

        for col, ref in sorted(curr_fk_set - prev_fk_set):
            add_details.append(AddForeignKey(table=curr_tname, column=col, ref_table=ref))
        for col, ref in sorted(prev_fk_set - curr_fk_set):
            drop_details.append(DropForeignKey(table=curr_tname, column=col, ref_table=ref))

        # index diffs: indexes is list[str] (column names)
        prev_indexes = set(prev_snap.get("indexes", []))
        curr_indexes = set(curr_snap.get("indexes", []))

        for col in sorted(curr_indexes - prev_indexes):
            add_details.append(AddIndex(table=curr_tname, column=col))
        for col in sorted(prev_indexes - curr_indexes):
            drop_details.append(DropIndex(table=curr_tname, column=col))

        # unique diffs: uniques is list[str] (column names)
        prev_uniques = set(prev_snap.get("uniques", []))
        curr_uniques = set(curr_snap.get("uniques", []))

        for col in sorted(curr_uniques - prev_uniques):
            add_details.append(AddUnique(table=curr_tname, column=col))
        for col in sorted(prev_uniques - curr_uniques):
            drop_details.append(DropUnique(table=curr_tname, column=col))

    return rename_ops + add_tables + add_details + alters + drop_details + drop_tables
