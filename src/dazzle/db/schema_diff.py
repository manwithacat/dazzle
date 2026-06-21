"""Schema diff operations for DSL-snapshot migrations.

Defines frozen dataclasses representing atomic schema changes,
used to compute and apply migrations between DSL snapshots.
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class AddTable:
    """Add a new table with columns, foreign keys, indexes, and unique constraints."""

    table: str
    columns: dict[str, Any]
    fks: list[str]
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

#: Opaque rename hints (consumed by Task 4.x; ignored here)
RenameHints = dict[str, Any]


def diff(
    prev: Snapshot,
    curr: Snapshot,
    hints: RenameHints | None = None,  # noqa: ARG001  (used in Task 4.x)
) -> list[SchemaOp]:
    """Return a minimal ordered list of SchemaOps to evolve *prev* into *curr*.

    Ordering contract (renames not yet produced here):
        RenameTable / RenameColumn  (future)
        → AddTable
        → AddColumn / AddForeignKey / AddIndex / AddUnique
        → AlterColumn
        → DropColumn / DropForeignKey / DropIndex / DropUnique
        → DropTable

    Pure: no DB, no Alembic, no I/O.
    ``hints`` is accepted but ignored until Task 4.x rename resolution.
    """
    add_tables: list[SchemaOp] = []
    add_details: list[SchemaOp] = []  # AddColumn / AddFK / AddIndex / AddUnique
    alters: list[SchemaOp] = []
    drop_details: list[SchemaOp] = []  # DropColumn / DropFK / DropIndex / DropUnique
    drop_tables: list[SchemaOp] = []

    prev_tables = set(prev)
    curr_tables = set(curr)

    # --- new tables ---------------------------------------------------------
    for tname in sorted(curr_tables - prev_tables):
        tsnap = curr[tname]
        add_tables.append(
            AddTable(
                table=tname,
                columns=dict(tsnap.get("columns", {})),
                fks=list(tsnap.get("fks", {}).keys()),
                indexes=list(tsnap.get("indexes", [])),
                uniques=list(tsnap.get("uniques", [])),
            )
        )

    # --- dropped tables -----------------------------------------------------
    for tname in sorted(prev_tables - curr_tables):
        drop_tables.append(DropTable(table=tname, snap=prev[tname]))

    # --- tables present in both: column + index + fk + unique diffs --------
    for tname in sorted(prev_tables & curr_tables):
        prev_snap = prev[tname]
        curr_snap = curr[tname]

        prev_cols: dict[str, ColSnap] = prev_snap.get("columns", {})
        curr_cols: dict[str, ColSnap] = curr_snap.get("columns", {})

        prev_col_names = set(prev_cols)
        curr_col_names = set(curr_cols)

        # added columns
        for cname in sorted(curr_col_names - prev_col_names):
            add_details.append(AddColumn(table=tname, name=cname, col=curr_cols[cname]))

        # altered columns (same name, different spec)
        for cname in sorted(prev_col_names & curr_col_names):
            if prev_cols[cname] != curr_cols[cname]:
                alters.append(
                    AlterColumn(
                        table=tname,
                        name=cname,
                        old=prev_cols[cname],
                        new=curr_cols[cname],
                    )
                )

        # dropped columns
        for cname in sorted(prev_col_names - curr_col_names):
            drop_details.append(DropColumn(table=tname, name=cname, col=prev_cols[cname]))

        # FK diffs: fks is dict[col → ref_table]
        prev_fks: dict[str, str] = prev_snap.get("fks", {})
        curr_fks: dict[str, str] = curr_snap.get("fks", {})
        prev_fk_set = set(prev_fks.items())
        curr_fk_set = set(curr_fks.items())

        for col, ref in sorted(curr_fk_set - prev_fk_set):
            add_details.append(AddForeignKey(table=tname, column=col, ref_table=ref))
        for col, ref in sorted(prev_fk_set - curr_fk_set):
            drop_details.append(DropForeignKey(table=tname, column=col, ref_table=ref))

        # index diffs: indexes is list[str] (column names)
        prev_indexes = set(prev_snap.get("indexes", []))
        curr_indexes = set(curr_snap.get("indexes", []))

        for col in sorted(curr_indexes - prev_indexes):
            add_details.append(AddIndex(table=tname, column=col))
        for col in sorted(prev_indexes - curr_indexes):
            drop_details.append(DropIndex(table=tname, column=col))

        # unique diffs: uniques is list[str] (column names)
        prev_uniques = set(prev_snap.get("uniques", []))
        curr_uniques = set(curr_snap.get("uniques", []))

        for col in sorted(curr_uniques - prev_uniques):
            add_details.append(AddUnique(table=tname, column=col))
        for col in sorted(prev_uniques - curr_uniques):
            drop_details.append(DropUnique(table=tname, column=col))

    return add_tables + add_details + alters + drop_details + drop_tables
