"""Render a list of SchemaOps into Alembic UpgradeOps + DowngradeOps.

This is the Task 3.1 renderer: pure data-transformation, no DB I/O,
no Alembic context required.  Wire-up into `db revision` is Task 3.3.

Usage::

    from dazzle.db.schema_diff import diff
    from dazzle.db.schema_render import render

    up, down = render(diff(prev_snap, curr_snap))
    # up.ops / down.ops are Alembic MigrateOperation lists

Design notes
------------
* Column-bearing ops go inside a ``ModifyTableOps(table_name, ops=[...])``.
  Table ops (CreateTableOp / DropTableOp / RenameTableOp) are top-level.
* FK, index, and unique constraint ops are top-level (Alembic convention).
* Inverse construction uses the prior-state data carried by each destructive op:
  - ``DropTable.snap``   → rebuilds CreateTableOp for downgrade
  - ``DropColumn.col``   → rebuilds AddColumnOp  for downgrade
  - ``AlterColumn.old``  → exact mirror AlterColumnOp for downgrade
* ``AlterColumn`` type changes inject ``postgresql_using`` via
  ``dazzle.http.runtime.safe_casts.get_using_clause``.
* Downgrade ops are produced in reverse order of the upgrade list so that
  inter-op dependencies are naturally respected (e.g. AddColumn added last
  is dropped first on rollback).
"""

from __future__ import annotations

import re
from typing import Any

import sqlalchemy as sa
from alembic.operations import ops as aops

from dazzle.db.schema_diff import (
    AddColumn,
    AddForeignKey,
    AddIndex,
    AddTable,
    AddUnique,
    AlterColumn,
    DropColumn,
    DropForeignKey,
    DropIndex,
    DropTable,
    DropUnique,
    RenameColumn,
    RenameTable,
    SchemaOp,
)
from dazzle.http.runtime.safe_casts import get_using_clause, is_safe_cast

# ---------------------------------------------------------------------------
# Public type aliases (mirrors schema_diff conventions)
# ---------------------------------------------------------------------------

ColSnap = dict[str, Any]

# ---------------------------------------------------------------------------
# Data-migration seam marker (Task 5.1)
# ---------------------------------------------------------------------------

#: Unique sqltext carried by the placeholder ``ExecuteSQLOp`` the renderer emits
#: at each unsafe-change data seam. Alembic renders this as a single
#: ``op.execute('<SEAM_MARKER>')`` line in the generated ``upgrade()`` body;
#: ``dazzle db revision`` post-write-replaces that line with the human-readable
#: ``# === DATA MIGRATION (hand-author) ===`` … block (see ``cli/db.py``).
#: Chosen so the renderer stays a pure op-tree transform (unit-testable on the
#: op stream) while the actual comment block lands verbatim in the file. The
#: token is deliberately distinctive so the post-write substitution is exact and
#: never collides with a real hand-authored ``op.execute``.
SEAM_MARKER = "__DAZZLE_DATA_MIGRATION_SEAM__"


def _seam_op() -> aops.ExecuteSQLOp:
    """A top-level placeholder op marking a hand-author data-migration seam."""
    return aops.ExecuteSQLOp(SEAM_MARKER)


# ---------------------------------------------------------------------------
# Token → SA type mapping (inverse of schema_snapshot._sa_type_to_token)
# ---------------------------------------------------------------------------

_NUMERIC_RE = re.compile(r"^numeric\((\d+)(?:,(\d+))?\)$")


def _token_to_sa_type(token: str) -> sa.types.TypeEngine[Any]:
    """Map a canonical string token (from schema_snapshot) to an SA type instance.

    Covers the full token set produced by ``_sa_type_to_token``:
    text / integer / bigint / boolean / numeric(p,s) / numeric(p) / numeric /
    float / date / timestamptz / uuid / json.

    Unknown tokens fall back to ``sa.Text()``.
    """
    t = token.strip().lower()
    if t == "text":
        return sa.Text()
    if t == "integer":
        return sa.Integer()
    if t == "bigint":
        return sa.BigInteger()
    if t == "boolean":
        return sa.Boolean()
    if t == "float":
        return sa.Float()
    if t == "date":
        return sa.Date()
    if t == "timestamptz":
        return sa.DateTime(timezone=True)
    if t == "uuid":
        return sa.Uuid()
    if t == "json":
        return sa.JSON()
    if t == "numeric":
        return sa.Numeric()
    m = _NUMERIC_RE.match(t)
    if m:
        p = int(m.group(1))
        s = int(m.group(2)) if m.group(2) is not None else None
        return sa.Numeric(precision=p, scale=s)
    # Unknown token: fall back to Text so we never raise at render time.
    return sa.Text()


# ---------------------------------------------------------------------------
# ColSnap → sa.Column builder
# ---------------------------------------------------------------------------


def _col_snap_to_sa_column(name: str, snap: ColSnap) -> sa.Column[Any]:
    """Build an ``sa.Column`` from a ColSnap dict.

    Keys: type (str), nullable (bool), default (str | None), pk (bool).
    """
    sa_type = _token_to_sa_type(snap["type"])
    raw_default = snap.get("default")
    server_default: sa.sql.elements.TextClause | None = (
        sa.text(raw_default) if raw_default is not None else None
    )
    return sa.Column(
        name,
        sa_type,
        nullable=snap.get("nullable", True),
        server_default=server_default,
        primary_key=snap.get("pk", False),
    )


# ---------------------------------------------------------------------------
# Constraint / index name helpers
# ---------------------------------------------------------------------------


def _fk_name(table: str, column: str) -> str:
    return f"fk_{table}_{column}"


def _idx_name(table: str, column: str) -> str:
    return f"ix_{table}_{column}"


def _uq_name(table: str, column: str) -> str:
    return f"uq_{table}_{column}"


# ---------------------------------------------------------------------------
# Per-op renderers — each returns (upgrade_op, downgrade_op)
# ---------------------------------------------------------------------------


def _render_add_table(
    op: AddTable,
) -> tuple[aops.MigrateOperation, aops.MigrateOperation]:
    columns: list[sa.Column[Any]] = [
        _col_snap_to_sa_column(cname, csnap) for cname, csnap in op.columns.items()
    ]
    create_op = aops.CreateTableOp(op.table, columns)
    drop_op = aops.DropTableOp(op.table)
    return create_op, drop_op


def _render_drop_table(
    op: DropTable,
) -> tuple[aops.MigrateOperation, aops.MigrateOperation]:
    drop_op = aops.DropTableOp(op.table)
    # Rebuild from the carried snapshot for downgrade
    snap_cols = op.snap.get("columns", {})
    columns: list[sa.Column[Any]] = [
        _col_snap_to_sa_column(cname, csnap) for cname, csnap in snap_cols.items()
    ]
    recreate_op = aops.CreateTableOp(op.table, columns)
    return drop_op, recreate_op


def _render_rename_table(
    op: RenameTable,
) -> tuple[aops.MigrateOperation, aops.MigrateOperation]:
    up_op = aops.RenameTableOp(op.old, op.new)
    down_op = aops.RenameTableOp(op.new, op.old)
    return up_op, down_op


def _is_unsafe_add(col: ColSnap) -> bool:
    """True when adding *col* would block on a populated table.

    Adding a ``NOT NULL`` column with no server ``default`` to a table that
    already has rows fails outright (Postgres can't fill the existing rows). That
    is the canonical expand→backfill→contract case. A nullable column, or one
    carrying a server default (Postgres backfills automatically), is safe.
    """
    return (col.get("nullable", True) is False) and col.get("default") is None


def _render_add_column(
    op: AddColumn,
) -> tuple[list[aops.MigrateOperation], list[aops.MigrateOperation]]:
    """Render an AddColumn — plain add, or the expand/contract scaffold if unsafe.

    Safe (nullable, or NOT NULL with a default): a single add + inverse drop.

    Unsafe (NOT NULL, no default): the expand→seam→contract scaffold —
      1. add the column **NULLABLE** (non-blocking expand),
      2. a marked data-migration seam (hand-author backfill),
      3. ``alter_column(nullable=False)`` to finalize (contract).
    The downgrade is just the inverse drop (dropping the column reverts the whole
    scaffold), so no seam is emitted on the way down.
    """
    if not _is_unsafe_add(op.col):
        col = _col_snap_to_sa_column(op.name, op.col)
        add_op = aops.AddColumnOp(op.table, col)
        drop_op = aops.DropColumnOp(op.table, op.name)
        return (
            [aops.ModifyTableOps(op.table, [add_op])],
            [aops.ModifyTableOps(op.table, [drop_op])],
        )

    # Unsafe: expand (add NULLABLE) → seam → contract (set NOT NULL).
    nullable_snap = {**op.col, "nullable": True}
    nullable_col = _col_snap_to_sa_column(op.name, nullable_snap)
    add_nullable = aops.AddColumnOp(op.table, nullable_col)
    target_type = _token_to_sa_type(op.col["type"])
    finalize = aops.AlterColumnOp(
        op.table,
        op.name,
        existing_type=target_type,
        existing_nullable=True,
        modify_nullable=False,
    )
    drop_op = aops.DropColumnOp(op.table, op.name)
    return (
        [
            aops.ModifyTableOps(op.table, [add_nullable]),
            _seam_op(),
            aops.ModifyTableOps(op.table, [finalize]),
        ],
        [aops.ModifyTableOps(op.table, [drop_op])],
    )


def _render_drop_column(
    op: DropColumn,
) -> tuple[aops.ModifyTableOps, aops.ModifyTableOps]:
    drop_op = aops.DropColumnOp(op.table, op.name)
    # Rebuild from the carried col snapshot for downgrade
    col = _col_snap_to_sa_column(op.name, op.col)
    add_op = aops.AddColumnOp(op.table, col)
    return (
        aops.ModifyTableOps(op.table, [drop_op]),
        aops.ModifyTableOps(op.table, [add_op]),
    )


def _render_rename_column(
    op: RenameColumn,
) -> tuple[aops.ModifyTableOps, aops.ModifyTableOps]:
    up_alter = aops.AlterColumnOp(op.table, op.old, modify_name=op.new)
    down_alter = aops.AlterColumnOp(op.table, op.new, modify_name=op.old)
    return (
        aops.ModifyTableOps(op.table, [up_alter]),
        aops.ModifyTableOps(op.table, [down_alter]),
    )


def _render_alter_column(
    op: AlterColumn,
) -> tuple[list[aops.MigrateOperation], list[aops.MigrateOperation]]:
    old, new = op.old, op.new

    # Build the forward (upgrade) AlterColumnOp kwargs
    old_type = _token_to_sa_type(old["type"])
    new_type = _token_to_sa_type(new["type"])
    old_nullable = old.get("nullable")
    new_nullable = new.get("nullable")
    old_default = old.get("default")
    new_default = new.get("default")

    type_changed = old["type"] != new["type"]
    nullable_changed = old_nullable != new_nullable
    default_changed = old_default != new_default

    up_alter_kw: dict[str, Any] = {
        "existing_type": old_type,
        "existing_nullable": old_nullable,
        "existing_server_default": sa.text(old_default) if old_default is not None else None,
    }
    if type_changed:
        up_alter_kw["modify_type"] = new_type
    if nullable_changed:
        up_alter_kw["modify_nullable"] = new_nullable
    if default_changed:
        up_alter_kw["modify_server_default"] = (
            sa.text(new_default) if new_default is not None else None
        )

    up_alter = aops.AlterColumnOp(op.table, op.name, **up_alter_kw)

    # Inject USING clause for safe type casts. A type change is unsafe only when
    # the (from, to) pair is absent from SAFE_CASTS entirely — i.e. not a known
    # safe cast. Safe no-op widenings (USING template = "") are in SAFE_CASTS but
    # return no USING string; they must NOT trigger the data seam scaffold.
    unsafe_type_change = False
    if type_changed:
        using = get_using_clause(old["type"].upper(), new["type"].upper(), op.name)
        if using:
            up_alter.kw["postgresql_using"] = using
        unsafe_type_change = not is_safe_cast(old["type"].upper(), new["type"].upper())

    # Build the inverse (downgrade) AlterColumnOp
    down_alter_kw: dict[str, Any] = {
        "existing_type": new_type,
        "existing_nullable": new_nullable,
        "existing_server_default": sa.text(new_default) if new_default is not None else None,
    }
    if type_changed:
        down_alter_kw["modify_type"] = old_type
    if nullable_changed:
        down_alter_kw["modify_nullable"] = old_nullable
    if default_changed:
        down_alter_kw["modify_server_default"] = (
            sa.text(old_default) if old_default is not None else None
        )

    down_alter = aops.AlterColumnOp(op.table, op.name, **down_alter_kw)

    up_ops: list[aops.MigrateOperation]
    if unsafe_type_change:
        # Seam first: the hand-authored data prep (e.g. populate a staging value,
        # validate every row casts) must run before the bare ALTER attempts the
        # cast. Downgrade reverses the type with no seam.
        up_ops = [_seam_op(), aops.ModifyTableOps(op.table, [up_alter])]
    else:
        up_ops = [aops.ModifyTableOps(op.table, [up_alter])]

    return (
        up_ops,
        [aops.ModifyTableOps(op.table, [down_alter])],
    )


def _render_add_fk(
    op: AddForeignKey,
) -> tuple[aops.MigrateOperation, aops.MigrateOperation]:
    name = _fk_name(op.table, op.column)
    create_op = aops.CreateForeignKeyOp(
        name,
        op.table,
        op.ref_table,
        [op.column],
        ["id"],
    )
    drop_op = aops.DropConstraintOp(name, op.table, type_="foreignkey")
    return create_op, drop_op


def _render_drop_fk(
    op: DropForeignKey,
) -> tuple[aops.MigrateOperation, aops.MigrateOperation]:
    name = _fk_name(op.table, op.column)
    drop_op = aops.DropConstraintOp(name, op.table, type_="foreignkey")
    recreate_op = aops.CreateForeignKeyOp(
        name,
        op.table,
        op.ref_table,
        [op.column],
        ["id"],
    )
    return drop_op, recreate_op


def _render_add_index(
    op: AddIndex,
) -> tuple[aops.MigrateOperation, aops.MigrateOperation]:
    name = _idx_name(op.table, op.column)
    create_op = aops.CreateIndexOp(name, op.table, [op.column])
    drop_op = aops.DropIndexOp(name, op.table)
    return create_op, drop_op


def _render_drop_index(
    op: DropIndex,
) -> tuple[aops.MigrateOperation, aops.MigrateOperation]:
    name = _idx_name(op.table, op.column)
    drop_op = aops.DropIndexOp(name, op.table)
    recreate_op = aops.CreateIndexOp(name, op.table, [op.column])
    return drop_op, recreate_op


def _render_add_unique(
    op: AddUnique,
) -> tuple[aops.MigrateOperation, aops.MigrateOperation]:
    name = _uq_name(op.table, op.column)
    create_op = aops.CreateUniqueConstraintOp(name, op.table, [op.column])
    drop_op = aops.DropConstraintOp(name, op.table, type_="unique")
    return create_op, drop_op


def _render_drop_unique(
    op: DropUnique,
) -> tuple[aops.MigrateOperation, aops.MigrateOperation]:
    name = _uq_name(op.table, op.column)
    drop_op = aops.DropConstraintOp(name, op.table, type_="unique")
    recreate_op = aops.CreateUniqueConstraintOp(name, op.table, [op.column])
    return drop_op, recreate_op


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render(ops: list[SchemaOp]) -> tuple[aops.UpgradeOps, aops.DowngradeOps]:
    """Render a list of SchemaOps into Alembic UpgradeOps and DowngradeOps.

    Each SchemaOp becomes one or more Alembic ``MigrateOperation`` objects.
    The downgrade is the exact inverse of the upgrade: destructive ops
    (DropTable, DropColumn) restore prior state using the snapshot data they
    carry; AlterColumn restores the old spec exactly.

    Downgrade ops are in reverse order so that inter-op dependencies are
    naturally respected during rollback.

    Column-bearing ops (AddColumn, DropColumn, RenameColumn, AlterColumn)
    are wrapped in ``ModifyTableOps``; all others are top-level.
    """
    up_ops: list[aops.MigrateOperation] = []
    down_ops: list[aops.MigrateOperation] = []

    for op in ops:
        # AddColumn / AlterColumn may scaffold (expand→seam→contract) and so
        # return op *lists*; every other renderer returns a single (up, down)
        # pair. Normalise both shapes to lists before extending.
        up_part: list[aops.MigrateOperation]
        down_part: list[aops.MigrateOperation]

        if isinstance(op, AddColumn):
            up_part, down_part = _render_add_column(op)
        elif isinstance(op, AlterColumn):
            up_part, down_part = _render_alter_column(op)
        else:
            single = _render_single(op)
            if single is None:
                # Future ops — skip rather than raise so the engine stays
                # forward-compatible.
                continue
            up_one, down_one = single
            up_part, down_part = [up_one], [down_one]

        up_ops.extend(up_part)
        # Reverse each op-group's internal order so the group's downgrade runs
        # last-added-first, then the groups themselves rollback in reverse below.
        down_ops.extend(reversed(down_part))

    return (
        aops.UpgradeOps(ops=up_ops),
        aops.DowngradeOps(ops=list(reversed(down_ops))),
    )


def _render_single(
    op: SchemaOp,
) -> tuple[aops.MigrateOperation, aops.MigrateOperation] | None:
    """Render a non-scaffolding SchemaOp to a single (upgrade, downgrade) pair.

    Returns ``None`` for unknown future ops so ``render`` can skip them.
    """
    if isinstance(op, AddTable):
        return _render_add_table(op)
    if isinstance(op, DropTable):
        return _render_drop_table(op)
    if isinstance(op, RenameTable):
        return _render_rename_table(op)
    if isinstance(op, DropColumn):
        return _render_drop_column(op)
    if isinstance(op, RenameColumn):
        return _render_rename_column(op)
    if isinstance(op, AddForeignKey):
        return _render_add_fk(op)
    if isinstance(op, DropForeignKey):
        return _render_drop_fk(op)
    if isinstance(op, AddIndex):
        return _render_add_index(op)
    if isinstance(op, DropIndex):
        return _render_drop_index(op)
    if isinstance(op, AddUnique):
        return _render_add_unique(op)
    if isinstance(op, DropUnique):
        return _render_drop_unique(op)
    return None
