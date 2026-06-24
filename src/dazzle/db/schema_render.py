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
from dazzle.http.runtime.query_builder import quote_identifier
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


def _token_to_pg_type_name(token: str) -> str:
    """Map a canonical snapshot token to its Postgres column-type DDL name.

    Used to render a raw ``ALTER COLUMN ... TYPE <pg_type> USING ...`` statement
    (see ``_render_alter_column``). The names are the literal Postgres type names
    accepted in a ``TYPE`` clause. ``numeric(p,s)`` carries its precision/scale
    through. Unknown tokens fall back to ``text`` (mirrors ``_token_to_sa_type``).
    """
    t = token.strip().lower()
    simple = {
        "text": "text",
        "integer": "integer",
        "bigint": "bigint",
        "boolean": "boolean",
        "float": "double precision",
        "date": "date",
        "timestamptz": "timestamptz",
        "uuid": "uuid",
        "json": "jsonb",
        "numeric": "numeric",
    }
    if t in simple:
        return simple[t]
    m = _NUMERIC_RE.match(t)
    if m:
        p = m.group(1)
        s = m.group(2)
        return f"numeric({p},{s})" if s is not None else f"numeric({p})"
    return "text"


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


def _fk_name(table: str, columns: tuple[str, ...]) -> str:
    return f"fk_{table}_{'_'.join(columns)}"


def _idx_name(table: str, column: str) -> str:
    # ``column`` may be a comma-joined multi-column key ("a,b") from the snapshot;
    # commas are illegal in an identifier, so join the parts with an underscore.
    return f"ix_{table}_{column.replace(',', '_')}"


def _idx_columns(column: str) -> list[str]:
    """Split a snapshot index key ("a" or "a,b") into its column list."""
    return column.split(",")


def _uq_name(table: str, columns: tuple[str, ...]) -> str:
    return f"uq_{table}_{'_'.join(columns)}"


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


def _type_change_disposition(
    old_type_token: str, new_type_token: str, column_name: str
) -> tuple[str | None, bool]:
    """Classify a type-token change and return ``(using_clause, unsafe)``.

    Returns:
        using_clause: Non-empty string → emit as ``ExecuteSQLOp`` with USING.
                      Empty string / None → no USING needed (safe widening or no change).
        unsafe:       True when the pair is absent from SAFE_CASTS entirely
                      (a data-seam scaffold is required).

    A non-empty ``using_clause`` takes precedence: the change is emitted via
    ``ExecuteSQLOp`` regardless of ``unsafe`` (the USING clause is the cast).
    """
    # SAFE_CASTS keys on Postgres type names (e.g. "JSONB"), not DSL tokens
    # (e.g. "json"). Normalise both ends through the token→pg-name map before
    # the lookup, else a token whose name differs from its pg type (json→jsonb)
    # never matches its safe-cast entry and falls through to the unsafe seam.
    old_pg = _token_to_pg_type_name(old_type_token).upper()
    new_pg = _token_to_pg_type_name(new_type_token).upper()
    using = get_using_clause(old_pg, new_pg, column_name)
    type_via_execute = bool(using)
    unsafe = not type_via_execute and not is_safe_cast(old_pg, new_pg)
    return using, unsafe


def _build_alter_column_op(
    table: str,
    name: str,
    existing_type: sa.types.TypeEngine[Any],
    existing_nullable: bool | None,
    existing_default: str | None,
    *,
    modify_type: sa.types.TypeEngine[Any] | None = None,
    modify_nullable: bool | None = None,
    modify_default: str | None = None,
    has_default_change: bool = False,
) -> tuple[aops.AlterColumnOp, bool]:
    """Build an ``AlterColumnOp`` plus a flag indicating it carries real work.

    Returns ``(op, has_work)`` where ``has_work`` is True when at least one
    ``modify_*`` kwarg is populated (otherwise wrapping in ``ModifyTableOps``
    would produce a no-op alter that confuses Alembic's renderer).
    """
    kw: dict[str, Any] = {
        "existing_type": existing_type,
        "existing_nullable": existing_nullable,
        "existing_server_default": sa.text(existing_default)
        if existing_default is not None
        else None,
    }
    has_work = False
    if modify_type is not None:
        kw["modify_type"] = modify_type
        has_work = True
    if modify_nullable is not None:
        kw["modify_nullable"] = modify_nullable
        has_work = True
    if has_default_change:
        kw["modify_server_default"] = (
            sa.text(modify_default) if modify_default is not None else None
        )
        has_work = True
    return aops.AlterColumnOp(table, name, **kw), has_work


def _render_type_via_execute(
    op: AlterColumn,
    using: str,
    up_alter: aops.AlterColumnOp,
    up_alter_has_work: bool,
    down_alter: aops.AlterColumnOp,
    down_alter_has_work: bool,
) -> tuple[list[aops.MigrateOperation], list[aops.MigrateOperation]]:
    """Emit a type change via raw SQL ``ExecuteSQLOp`` so the USING clause survives
    Alembic's file serialisation (``AlterColumnOp`` silently drops
    ``postgresql_using`` when writing the ``.py`` revision file).

    The nullable/default ``AlterColumnOp`` (if it carries work) is emitted after
    the type-change SQL in the upgrade; downgrade reverses the order.
    """
    new_pg = _token_to_pg_type_name(op.new["type"])
    old_pg = _token_to_pg_type_name(op.old["type"])

    # Look up the reverse cast on pg type names (new_pg/old_pg), not raw tokens —
    # get_using_clause uppercases internally, so a jsonb→text reverse matches.
    reverse_using = get_using_clause(new_pg, old_pg, op.name)
    if not reverse_using:
        reverse_using = f"{quote_identifier(op.name)}::{old_pg}"

    up_ops: list[aops.MigrateOperation] = [
        _type_change_execute_op(op.table, op.name, new_pg, using)
    ]
    if up_alter_has_work:
        up_ops.append(aops.ModifyTableOps(op.table, [up_alter]))

    down_ops: list[aops.MigrateOperation] = []
    if down_alter_has_work:
        down_ops.append(aops.ModifyTableOps(op.table, [down_alter]))
    down_ops.append(_type_change_execute_op(op.table, op.name, old_pg, reverse_using))

    return up_ops, down_ops


def _render_alter_column(
    op: AlterColumn,
) -> tuple[list[aops.MigrateOperation], list[aops.MigrateOperation]]:
    old, new = op.old, op.new

    old_type = _token_to_sa_type(old["type"])
    new_type = _token_to_sa_type(new["type"])
    old_nullable = old.get("nullable")
    new_nullable = new.get("nullable")
    old_default = old.get("default")
    new_default = new.get("default")

    type_changed = old["type"] != new["type"]
    nullable_changed = old_nullable != new_nullable
    default_changed = old_default != new_default

    # Classify the type change: needs USING expression, unsafe, or plain alter.
    using, unsafe_type_change = (
        _type_change_disposition(old["type"], new["type"], op.name)
        if type_changed
        else (None, False)
    )
    type_via_execute = bool(using)

    # The AlterColumnOp carries nullable/default aspects (which DO serialize) plus
    # the type change only when rendered through AlterColumnOp (not via ExecuteSQLOp).
    # Existing-type tracks the column's type as the op sees it: when the type was
    # already changed by a preceding ExecuteSQLOp, existing_type must be the NEW type.
    up_alter, up_alter_has_work = _build_alter_column_op(
        op.table,
        op.name,
        existing_type=new_type if type_via_execute else old_type,
        existing_nullable=old_nullable,
        existing_default=old_default,
        modify_type=new_type if (type_changed and not type_via_execute) else None,
        modify_nullable=new_nullable if nullable_changed else None,
        modify_default=new_default if default_changed else None,
        has_default_change=default_changed,
    )

    down_alter, down_alter_has_work = _build_alter_column_op(
        op.table,
        op.name,
        existing_type=old_type if type_via_execute else new_type,
        existing_nullable=new_nullable,
        existing_default=new_default,
        modify_type=old_type if (type_changed and not type_via_execute) else None,
        modify_nullable=old_nullable if nullable_changed else None,
        modify_default=old_default if default_changed else None,
        has_default_change=default_changed,
    )

    if type_via_execute:
        assert using is not None  # narrows for mypy; type_via_execute == bool(using)
        return _render_type_via_execute(
            op, using, up_alter, up_alter_has_work, down_alter, down_alter_has_work
        )

    if unsafe_type_change:
        # Seam first: hand-authored data prep must run before the bare ALTER.
        # Downgrade reverses the type with no seam.
        return (
            [_seam_op(), aops.ModifyTableOps(op.table, [up_alter])],
            [aops.ModifyTableOps(op.table, [down_alter])],
        )

    return (
        [aops.ModifyTableOps(op.table, [up_alter])],
        [aops.ModifyTableOps(op.table, [down_alter])],
    )


def _type_change_execute_op(
    table: str, column: str, pg_type: str, using_expr: str
) -> aops.ExecuteSQLOp:
    """A raw ``ALTER TABLE ... ALTER COLUMN ... TYPE ... USING ...`` op.

    Carries the full statement (including the USING clause) as ExecuteSQLOp
    sqltext, which Alembic serializes verbatim — the only reliable way to get a
    USING clause into the generated revision file (AlterColumnOp drops it).
    """
    sql = (
        f"ALTER TABLE {quote_identifier(table)} "
        f"ALTER COLUMN {quote_identifier(column)} TYPE {pg_type} USING {using_expr}"
    )
    return aops.ExecuteSQLOp(sql)


def _render_add_fk(
    op: AddForeignKey,
) -> tuple[aops.MigrateOperation, aops.MigrateOperation]:
    name = _fk_name(op.table, op.columns)
    create_op = aops.CreateForeignKeyOp(
        name,
        op.table,
        op.ref_table,
        list(op.columns),
        list(op.ref_columns),
    )
    drop_op = aops.DropConstraintOp(name, op.table, type_="foreignkey")
    return create_op, drop_op


def _render_drop_fk(
    op: DropForeignKey,
) -> tuple[aops.MigrateOperation, aops.MigrateOperation]:
    name = _fk_name(op.table, op.columns)
    drop_op = aops.DropConstraintOp(name, op.table, type_="foreignkey")
    recreate_op = aops.CreateForeignKeyOp(
        name,
        op.table,
        op.ref_table,
        list(op.columns),
        list(op.ref_columns),
    )
    return drop_op, recreate_op


def _render_add_index(
    op: AddIndex,
) -> tuple[aops.MigrateOperation, aops.MigrateOperation]:
    name = _idx_name(op.table, op.column)
    create_op = aops.CreateIndexOp(name, op.table, _idx_columns(op.column))
    drop_op = aops.DropIndexOp(name, op.table)
    return create_op, drop_op


def _render_drop_index(
    op: DropIndex,
) -> tuple[aops.MigrateOperation, aops.MigrateOperation]:
    name = _idx_name(op.table, op.column)
    drop_op = aops.DropIndexOp(name, op.table)
    recreate_op = aops.CreateIndexOp(name, op.table, _idx_columns(op.column))
    return drop_op, recreate_op


def _render_add_unique(
    op: AddUnique,
) -> tuple[aops.MigrateOperation, aops.MigrateOperation]:
    name = _uq_name(op.table, op.columns)
    create_op = aops.CreateUniqueConstraintOp(name, op.table, list(op.columns))
    drop_op = aops.DropConstraintOp(name, op.table, type_="unique")
    return create_op, drop_op


def _render_drop_unique(
    op: DropUnique,
) -> tuple[aops.MigrateOperation, aops.MigrateOperation]:
    name = _uq_name(op.table, op.columns)
    drop_op = aops.DropConstraintOp(name, op.table, type_="unique")
    recreate_op = aops.CreateUniqueConstraintOp(name, op.table, list(op.columns))
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
