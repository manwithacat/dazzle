"""Tests for schema diff operations."""

from dataclasses import FrozenInstanceError

import pytest

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


def test_add_table_frozen():
    """AddTable is frozen and fields are accessible."""
    op = AddTable(
        table="users",
        columns={"id": {"type": "uuid"}, "name": {"type": "varchar"}},
        fks=[],
        indexes=[],
        uniques=[],
    )
    assert op.table == "users"
    assert op.columns == {"id": {"type": "uuid"}, "name": {"type": "varchar"}}
    assert op.fks == []
    assert op.indexes == []
    assert op.uniques == []

    # Assert frozen
    with pytest.raises(FrozenInstanceError):
        op.table = "other_users"


def test_drop_table_with_snap():
    """DropTable carries prior table snapshot for downgrade."""
    prior_snap = {
        "columns": {"id": {"type": "uuid"}, "name": {"type": "varchar"}},
        "fks": [],
        "indexes": [],
        "uniques": [],
    }
    op = DropTable(table="users", snap=prior_snap)
    assert op.table == "users"
    assert op.snap == prior_snap

    # Assert frozen
    with pytest.raises(FrozenInstanceError):
        op.table = "other_users"


def test_rename_table():
    """RenameTable has old and new table names."""
    op = RenameTable(old="users", new="accounts")
    assert op.old == "users"
    assert op.new == "accounts"

    # Assert frozen
    with pytest.raises(FrozenInstanceError):
        op.old = "members"


def test_add_column():
    """AddColumn specifies table, column name, and column spec."""
    col_spec = {"type": "varchar", "nullable": False}
    op = AddColumn(table="users", name="email", col=col_spec)
    assert op.table == "users"
    assert op.name == "email"
    assert op.col == col_spec

    # Assert frozen
    with pytest.raises(FrozenInstanceError):
        op.table = "accounts"


def test_drop_column_with_snap():
    """DropColumn carries prior column snapshot for downgrade."""
    col_snap = {"type": "varchar", "nullable": True}
    op = DropColumn(table="users", name="email", col=col_snap)
    assert op.table == "users"
    assert op.name == "email"
    assert op.col == col_snap

    # Assert frozen
    with pytest.raises(FrozenInstanceError):
        op.name = "phone"


def test_rename_column():
    """RenameColumn specifies table and old/new column names."""
    op = RenameColumn(table="users", old="user_name", new="username")
    assert op.table == "users"
    assert op.old == "user_name"
    assert op.new == "username"

    # Assert frozen
    with pytest.raises(FrozenInstanceError):
        op.table = "accounts"


def test_alter_column():
    """AlterColumn specifies table, column, and old/new specs."""
    old_spec = {"type": "varchar", "nullable": True}
    new_spec = {"type": "varchar", "nullable": False}
    op = AlterColumn(table="users", name="email", old=old_spec, new=new_spec)
    assert op.table == "users"
    assert op.name == "email"
    assert op.old == old_spec
    assert op.new == new_spec

    # Assert frozen
    with pytest.raises(FrozenInstanceError):
        op.name = "phone"


def test_add_foreign_key():
    """AddForeignKey specifies table, column, and referenced table."""
    op = AddForeignKey(table="orders", column="user_id", ref_table="users")
    assert op.table == "orders"
    assert op.column == "user_id"
    assert op.ref_table == "users"

    # Assert frozen
    with pytest.raises(FrozenInstanceError):
        op.table = "invoices"


def test_drop_foreign_key():
    """DropForeignKey specifies table, column, and referenced table."""
    op = DropForeignKey(table="orders", column="user_id", ref_table="users")
    assert op.table == "orders"
    assert op.column == "user_id"
    assert op.ref_table == "users"

    # Assert frozen
    with pytest.raises(FrozenInstanceError):
        op.column = "account_id"


def test_add_index():
    """AddIndex specifies table and column."""
    op = AddIndex(table="users", column="email")
    assert op.table == "users"
    assert op.column == "email"

    # Assert frozen
    with pytest.raises(FrozenInstanceError):
        op.table = "accounts"


def test_drop_index():
    """DropIndex specifies table and column."""
    op = DropIndex(table="users", column="email")
    assert op.table == "users"
    assert op.column == "email"

    # Assert frozen
    with pytest.raises(FrozenInstanceError):
        op.column = "username"


def test_add_unique():
    """AddUnique specifies table and column."""
    op = AddUnique(table="users", column="email")
    assert op.table == "users"
    assert op.column == "email"

    # Assert frozen
    with pytest.raises(FrozenInstanceError):
        op.table = "accounts"


def test_drop_unique():
    """DropUnique specifies table and column."""
    op = DropUnique(table="users", column="email")
    assert op.table == "users"
    assert op.column == "email"

    # Assert frozen
    with pytest.raises(FrozenInstanceError):
        op.column = "username"


def test_schema_op_union_types():
    """SchemaOp accepts all op types."""
    ops: list[SchemaOp] = [
        AddTable("t1", {}, [], [], []),
        DropTable("t2", {}),
        RenameTable("t3", "t3_renamed"),
        AddColumn("t4", "c1", {}),
        DropColumn("t5", "c2", {}),
        RenameColumn("t6", "c3", "c3_renamed"),
        AlterColumn("t7", "c4", {}, {}),
        AddForeignKey("t8", "c5", "t_ref"),
        DropForeignKey("t9", "c6", "t_ref"),
        AddIndex("t10", "c7"),
        DropIndex("t11", "c8"),
        AddUnique("t12", "c9"),
        DropUnique("t13", "c10"),
    ]
    assert len(ops) == 13
