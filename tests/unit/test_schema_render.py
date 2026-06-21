"""Tests for schema_render: SchemaDelta → Alembic UpgradeOps/DowngradeOps.

TDD: each test group covers a SchemaOp type with upgrade assertions
and exact inverse (downgrade) assertions.
"""

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
from dazzle.db.schema_render import render

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


def test_alter_column_type_change_uses_postgresql_using():
    old = {"type": "text", "nullable": True, "default": None, "pk": False}
    new = {"type": "uuid", "nullable": True, "default": None, "pk": False}
    up, down = render([AlterColumn("t", "col", old, new)])
    up_flat = _up_ops(up.ops)
    alter = next(o for o in up_flat if isinstance(o, aops.AlterColumnOp))
    # USING clause injected for TEXT → UUID safe cast
    assert "postgresql_using" in alter.kw
    assert "col" in alter.kw["postgresql_using"]


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
