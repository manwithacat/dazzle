"""Tests for schema_render: SchemaDelta → Alembic UpgradeOps/DowngradeOps.

TDD: each test group covers a SchemaOp type with upgrade assertions
and exact inverse (downgrade) assertions.
"""

import pytest
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
)
from dazzle.db.schema_render import SEAM_MARKER, render
from dazzle.http.runtime.safe_casts import is_safe_cast

pytestmark = pytest.mark.migration_engine

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_TEXT_COL = {"type": "text", "nullable": True, "default": None, "pk": False}
_UUID_PK = {"type": "uuid", "nullable": False, "default": None, "pk": True}
_INT_COL = {"type": "integer", "nullable": False, "default": None, "pk": False}
_BOOL_COL = {"type": "boolean", "nullable": True, "default": "false", "pk": False}


def _up_ops(ops_list: list) -> list:
    """Flatten all ops (including ModifyTableOps sub-ops) into a flat list."""
    result = []
    for o in ops_list:
        if isinstance(o, aops.ModifyTableOps):
            result.extend(o.ops)
        else:
            result.append(o)
    return result


# ---------------------------------------------------------------------------
# AddTable / DropTable (from brief)
# ---------------------------------------------------------------------------


def test_add_table_renders_create_table():
    up, down = render([AddTable("t", {"id": _UUID_PK}, {}, [], [])])
    assert any(isinstance(o, aops.CreateTableOp) and o.table_name == "t" for o in up.ops)
    # downgrade drops it
    assert any(isinstance(o, aops.DropTableOp) and o.table_name == "t" for o in down.ops)


def test_add_column_renders_add_and_inverse_drop():
    up, down = render([AddColumn("t", "b", _TEXT_COL)])
    add = [o for o in up.ops if isinstance(o, aops.ModifyTableOps)][0]
    assert any(isinstance(s, aops.AddColumnOp) for s in add.ops)
    drop = [o for o in down.ops if isinstance(o, aops.ModifyTableOps)][0]
    assert any(isinstance(s, aops.DropColumnOp) for s in drop.ops)


# ---------------------------------------------------------------------------
# DropTable → inverse is CreateTable
# ---------------------------------------------------------------------------


def test_drop_table_renders_drop_and_inverse_create():
    snap = {
        "columns": {"id": _UUID_PK, "name": _TEXT_COL},
        "fks": {},
        "indexes": [],
        "uniques": [],
    }
    up, down = render([DropTable("t", snap)])
    assert any(isinstance(o, aops.DropTableOp) and o.table_name == "t" for o in up.ops)
    assert any(isinstance(o, aops.CreateTableOp) and o.table_name == "t" for o in down.ops)


# ---------------------------------------------------------------------------
# DropColumn → inverse re-adds from carried col
# ---------------------------------------------------------------------------


def test_drop_column_renders_drop_and_inverse_add():
    up, down = render([DropColumn("t", "name", _TEXT_COL)])
    up_flat = _up_ops(up.ops)
    assert any(isinstance(o, aops.DropColumnOp) and o.column_name == "name" for o in up_flat)
    down_flat = _up_ops(down.ops)
    assert any(isinstance(o, aops.AddColumnOp) and o.column.name == "name" for o in down_flat)


# ---------------------------------------------------------------------------
# AlterColumn — no type change
# ---------------------------------------------------------------------------


def test_alter_column_nullable_change():
    old = {"type": "text", "nullable": True, "default": None, "pk": False}
    new = {"type": "text", "nullable": False, "default": None, "pk": False}
    up, down = render([AlterColumn("t", "col", old, new)])
    up_flat = _up_ops(up.ops)
    alter = next(o for o in up_flat if isinstance(o, aops.AlterColumnOp))
    assert alter.modify_nullable is False
    assert alter.existing_nullable is True
    # downgrade restores old nullable
    down_flat = _up_ops(down.ops)
    restore = next(o for o in down_flat if isinstance(o, aops.AlterColumnOp))
    assert restore.modify_nullable is True
    assert restore.existing_nullable is False


# ---------------------------------------------------------------------------
# AlterColumn — type change with USING clause
# ---------------------------------------------------------------------------


def test_alter_column_type_change_emits_execute_sql_with_using():
    """A type change WITH a non-empty USING (TEXT→UUID) renders a raw ExecuteSQLOp.

    Alembic's file renderer drops ``kw["postgresql_using"]`` from an AlterColumnOp,
    so the type change is emitted as a raw ``ALTER COLUMN ... TYPE ... USING ...``
    statement (ExecuteSQLOp), whose SQL survives serialization verbatim.
    """
    old = {"type": "text", "nullable": True, "default": None, "pk": False}
    new = {"type": "uuid", "nullable": True, "default": None, "pk": False}
    up, down = render([AlterColumn("t", "col", old, new)])
    up_flat = _up_ops(up.ops)

    # No plain AlterColumnOp carries the (dropped) postgresql_using.
    assert not any(isinstance(o, aops.AlterColumnOp) for o in up_flat), (
        "type-change-with-USING must NOT use AlterColumnOp (Alembic drops the USING)"
    )
    # A raw ExecuteSQLOp with both TYPE and USING is present.
    execs = [o for o in up_flat if isinstance(o, aops.ExecuteSQLOp)]
    assert len(execs) == 1, "exactly one ExecuteSQLOp for the type change"
    sql = execs[0].sqltext
    assert "TYPE uuid" in sql, f"type change must target uuid; got: {sql}"
    assert "USING" in sql, f"the USING clause is the whole point; got: {sql}"
    assert "col" in sql, f"the column must appear in the USING expr; got: {sql}"

    # Downgrade reverses the type with a matching ExecuteSQLOp (uuid→text cast).
    down_flat = _up_ops(down.ops)
    down_execs = [o for o in down_flat if isinstance(o, aops.ExecuteSQLOp)]
    assert len(down_execs) == 1, "exactly one ExecuteSQLOp for the downgrade type revert"
    down_sql = down_execs[0].sqltext
    assert "TYPE text" in down_sql, f"downgrade must revert to text; got: {down_sql}"
    assert "USING" in down_sql, f"downgrade must carry a reverse cast; got: {down_sql}"


# ---------------------------------------------------------------------------
# Task 5.1 — unsafe-change expand/contract scaffold + data seam
# ---------------------------------------------------------------------------


def _seam_ops(up_flat: list) -> list:
    """The ExecuteSQLOp seam markers present in a flat upgrade-op list."""
    return [o for o in up_flat if isinstance(o, aops.ExecuteSQLOp) and o.sqltext == SEAM_MARKER]


def test_add_not_null_no_default_scaffolds_expand_seam_contract():
    """Unsafe AddColumn(nullable=False, default=None) → add-nullable, seam, finalize."""
    unsafe = {"type": "text", "nullable": False, "default": None, "pk": False}
    up, down = render([AddColumn("t", "x", unsafe)])
    up_flat = _up_ops(up.ops)

    # 1. add-column NULLABLE first (the expand step — non-blocking)
    add = next(o for o in up_flat if isinstance(o, aops.AddColumnOp))
    assert add.column.name == "x"
    assert add.column.nullable is True, "expand step must add the column NULLABLE"

    # 2. a data-migration seam marker is present between expand and contract
    seams = _seam_ops(up_flat)
    assert len(seams) == 1, "exactly one data-migration seam marker expected"

    # 3. finalize — alter_column(nullable=False) (the contract step)
    alter = next(o for o in up_flat if isinstance(o, aops.AlterColumnOp))
    assert alter.column_name == "x"
    assert alter.modify_nullable is False

    # Ordering: add (expand) → seam → alter (contract)
    add_i = up_flat.index(add)
    seam_i = up_flat.index(seams[0])
    alter_i = up_flat.index(alter)
    assert add_i < seam_i < alter_i

    # Downgrade just drops the added column (no seam).
    down_flat = _up_ops(down.ops)
    assert any(isinstance(o, aops.DropColumnOp) and o.column_name == "x" for o in down_flat)
    assert not _seam_ops(down_flat), "downgrade carries no seam marker"


def test_add_nullable_does_not_scaffold():
    """A NULLABLE AddColumn is safe — plain add, no seam."""
    safe = {"type": "text", "nullable": True, "default": None, "pk": False}
    up, _ = render([AddColumn("t", "x", safe)])
    up_flat = _up_ops(up.ops)
    assert not _seam_ops(up_flat)
    assert not any(isinstance(o, aops.AlterColumnOp) for o in up_flat)
    add = next(o for o in up_flat if isinstance(o, aops.AddColumnOp))
    assert add.column.nullable is True


def test_add_not_null_with_default_does_not_scaffold():
    """NOT NULL but with a server default is safe (backfill is automatic) — plain add."""
    safe = {"type": "boolean", "nullable": False, "default": "false", "pk": False}
    up, _ = render([AddColumn("t", "x", safe)])
    up_flat = _up_ops(up.ops)
    assert not _seam_ops(up_flat)
    add = next(o for o in up_flat if isinstance(o, aops.AddColumnOp))
    assert add.column.nullable is False, "safe path keeps the single NOT NULL add"


def test_safe_type_change_does_not_scaffold():
    """A safe type change with USING (TEXT→UUID) does NOT emit a data seam.

    It renders as a raw type-change ExecuteSQLOp (carrying USING) — NOT the
    hand-author data-migration seam marker.
    """
    old = {"type": "text", "nullable": True, "default": None, "pk": False}
    new = {"type": "uuid", "nullable": True, "default": None, "pk": False}
    up, _ = render([AlterColumn("t", "col", old, new)])
    up_flat = _up_ops(up.ops)
    assert not _seam_ops(up_flat), "safe cast must not emit a data-migration seam"
    # The type change is a raw ExecuteSQLOp carrying the USING clause.
    execs = [o for o in up_flat if isinstance(o, aops.ExecuteSQLOp)]
    assert len(execs) == 1 and "USING" in execs[0].sqltext


def test_text_to_json_is_safe_cast_not_seam():
    """Regression (#1434): the DSL ``json`` token canonicalises to pg ``jsonb``.

    SAFE_CASTS keys on the pg type name (``("TEXT","JSONB")``), so the lookup
    must normalise ``json``→``jsonb`` before matching — otherwise ``text → json``
    falls through to the unsafe data-migration seam instead of an automatic
    ``::jsonb`` USING cast.
    """
    old = {"type": "text", "nullable": True, "default": None, "pk": False}
    new = {"type": "json", "nullable": True, "default": None, "pk": False}
    up, down = render([AlterColumn("t", "payload", old, new)])
    up_flat = _up_ops(up.ops)

    assert not _seam_ops(up_flat), "text→json is a safe cast — must not scaffold a seam"
    execs = [o for o in up_flat if isinstance(o, aops.ExecuteSQLOp)]
    assert len(execs) == 1, "exactly one ExecuteSQLOp for the type change"
    sql = execs[0].sqltext
    assert "TYPE jsonb" in sql, f"json token must render the jsonb pg type; got: {sql}"
    assert "::jsonb" in sql, f"the safe USING cast must be ::jsonb; got: {sql}"

    # Downgrade reverts jsonb→text with a matching reverse cast.
    down_flat = _up_ops(down.ops)
    down_execs = [o for o in down_flat if isinstance(o, aops.ExecuteSQLOp)]
    assert len(down_execs) == 1, "exactly one ExecuteSQLOp for the downgrade revert"
    assert "TYPE text" in down_execs[0].sqltext


def test_unsafe_type_change_scaffolds_seam():
    """A type change with NO safe USING cast (TEXT→INTEGER is safe; INTEGER→DATE is not).

    Uses INTEGER→DATE which is absent from SAFE_CASTS → no USING → unsafe → scaffold.
    """
    old = {"type": "integer", "nullable": True, "default": None, "pk": False}
    new = {"type": "date", "nullable": True, "default": None, "pk": False}
    up, down = render([AlterColumn("t", "col", old, new)])
    up_flat = _up_ops(up.ops)
    seams = _seam_ops(up_flat)
    assert len(seams) == 1, "unsafe type change must emit a data-migration seam"
    # The alter still occurs (wrapped by the seam) and carries no USING clause.
    alter = next(o for o in up_flat if isinstance(o, aops.AlterColumnOp))
    assert "postgresql_using" not in alter.kw
    # Seam precedes the alter (hand-authored data prep runs before the cast).
    assert up_flat.index(seams[0]) < up_flat.index(alter)
    # Downgrade restores the old type and carries no seam.
    down_flat = _up_ops(down.ops)
    assert not _seam_ops(down_flat)
    restore = next(o for o in down_flat if isinstance(o, aops.AlterColumnOp))
    assert restore.modify_type is not None


def test_safe_no_op_widening_does_not_scaffold():
    """A safe widening with an empty USING template must NOT emit a data seam.

    The empty-template entry ``("DOUBLE PRECISION","NUMERIC")`` is reachable from
    the real snapshot token ``float`` (#1434): ``_type_change_disposition`` now
    normalises each token through ``_token_to_pg_type_name`` before the SAFE_CASTS
    lookup, so ``float→numeric`` → ``("DOUBLE PRECISION","NUMERIC")`` → an empty
    USING template → a plain ``AlterColumnOp``, NOT a data-migration seam.
    """
    from dazzle.http.runtime.safe_casts import get_using_clause

    # Pre-condition: the empty-template pair IS in SAFE_CASTS and yields no USING.
    assert is_safe_cast("DOUBLE PRECISION", "NUMERIC"), "empty-template entry must be safe"
    assert not get_using_clause("DOUBLE PRECISION", "NUMERIC", "col"), (
        "empty-template entry must return falsy from get_using_clause (old bug trigger)"
    )

    # float → numeric: the snapshot tokens normalise to the empty-template entry.
    old = {"type": "float", "nullable": True, "default": None, "pk": False}
    new = {"type": "numeric", "nullable": True, "default": None, "pk": False}
    up, down = render([AlterColumn("t", "col", old, new)])
    up_flat = _up_ops(up.ops)

    # The fix: no seam emitted for a safe widening.
    seams = _seam_ops(up_flat)
    assert not seams, (
        "safe no-op widening float→numeric must NOT emit a data-migration seam; "
        f"got {len(seams)} seam(s)"
    )
    # A plain AlterColumnOp is produced.
    assert any(isinstance(o, aops.AlterColumnOp) for o in up_flat)


# ---------------------------------------------------------------------------
# RenameColumn
# ---------------------------------------------------------------------------


def test_rename_column_and_inverse():
    up, down = render([RenameColumn("t", "old_name", "new_name")])
    up_flat = _up_ops(up.ops)
    alter = next(o for o in up_flat if isinstance(o, aops.AlterColumnOp))
    assert alter.modify_name == "new_name"
    assert alter.column_name == "old_name"
    # downgrade renames back
    down_flat = _up_ops(down.ops)
    restore = next(o for o in down_flat if isinstance(o, aops.AlterColumnOp))
    assert restore.modify_name == "old_name"
    assert restore.column_name == "new_name"


# ---------------------------------------------------------------------------
# RenameTable
# ---------------------------------------------------------------------------


def test_rename_table_and_inverse():
    # RenameTableOp stores old name as .table_name, new name as .new_table_name
    up, down = render([RenameTable("old_t", "new_t")])
    assert any(
        isinstance(o, aops.RenameTableOp)
        and o.table_name == "old_t"
        and o.new_table_name == "new_t"
        for o in up.ops
    )
    assert any(
        isinstance(o, aops.RenameTableOp)
        and o.table_name == "new_t"
        and o.new_table_name == "old_t"
        for o in down.ops
    )


# ---------------------------------------------------------------------------
# AddForeignKey / DropForeignKey
# ---------------------------------------------------------------------------


def test_add_foreign_key_and_inverse():
    up, down = render([AddForeignKey("orders", "user_id", "users")])
    assert any(isinstance(o, aops.CreateForeignKeyOp) for o in up.ops)
    assert any(isinstance(o, aops.DropConstraintOp) for o in down.ops)


def test_drop_foreign_key_and_inverse():
    up, down = render([DropForeignKey("orders", "user_id", "users")])
    assert any(isinstance(o, aops.DropConstraintOp) for o in up.ops)
    assert any(isinstance(o, aops.CreateForeignKeyOp) for o in down.ops)


# ---------------------------------------------------------------------------
# AddIndex / DropIndex
# ---------------------------------------------------------------------------


def test_add_index_and_inverse():
    up, down = render([AddIndex("t", "email")])
    assert any(isinstance(o, aops.CreateIndexOp) for o in up.ops)
    assert any(isinstance(o, aops.DropIndexOp) for o in down.ops)


def test_drop_index_and_inverse():
    up, down = render([DropIndex("t", "email")])
    assert any(isinstance(o, aops.DropIndexOp) for o in up.ops)
    assert any(isinstance(o, aops.CreateIndexOp) for o in down.ops)


# ---------------------------------------------------------------------------
# AddUnique / DropUnique
# ---------------------------------------------------------------------------


def test_add_unique_and_inverse():
    up, down = render([AddUnique("t", "email")])
    assert any(isinstance(o, aops.CreateUniqueConstraintOp) for o in up.ops)
    assert any(isinstance(o, aops.DropConstraintOp) for o in down.ops)


def test_drop_unique_and_inverse():
    up, down = render([DropUnique("t", "email")])
    assert any(isinstance(o, aops.DropConstraintOp) for o in up.ops)
    assert any(isinstance(o, aops.CreateUniqueConstraintOp) for o in down.ops)


# ---------------------------------------------------------------------------
# Multiple ops in one render call — grouping
# ---------------------------------------------------------------------------


def test_multiple_ops_all_present():
    """Mixed ops: AddTable + AddColumn for a different table — both appear."""
    ops_list = [
        AddTable("new_table", {"id": _UUID_PK}, {}, [], []),
        AddColumn("other_table", "score", _INT_COL),
    ]
    up, down = render(ops_list)
    assert any(isinstance(o, aops.CreateTableOp) and o.table_name == "new_table" for o in up.ops)
    assert any(isinstance(o, aops.ModifyTableOps) and o.table_name == "other_table" for o in up.ops)
    # downgrade has both inverses
    assert any(isinstance(o, aops.DropTableOp) and o.table_name == "new_table" for o in down.ops)
    assert any(
        isinstance(o, aops.ModifyTableOps) and o.table_name == "other_table" for o in down.ops
    )


# ---------------------------------------------------------------------------
# Token-to-SA type coverage
# ---------------------------------------------------------------------------


def test_all_col_tokens_produce_sa_column():
    """Every canonical token from schema_snapshot produces a valid SA column."""
    tokens = [
        "text",
        "integer",
        "bigint",
        "boolean",
        "numeric",
        "numeric(10,2)",
        "numeric(10)",
        "float",
        "date",
        "timestamptz",
        "uuid",
        "json",
    ]
    import sqlalchemy as sa

    for token in tokens:
        col_snap = {"type": token, "nullable": True, "default": None, "pk": False}
        up, down = render([AddColumn("t", "c", col_snap)])
        up_flat = _up_ops(up.ops)
        add_op = next(o for o in up_flat if isinstance(o, aops.AddColumnOp))
        assert isinstance(add_op.column, sa.Column), f"Token {token!r} did not produce sa.Column"
