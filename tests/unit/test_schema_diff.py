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
    RenameResolutionError,
    RenameTable,
    SchemaOp,
    diff,
)

pytestmark = pytest.mark.migration_engine

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_COL = {"type": "text", "nullable": True, "default": None, "pk": False}


def _tbl(**cols):
    return {"columns": cols, "indexes": [], "uniques": [], "fks": {}}


# ---------------------------------------------------------------------------
# diff() — brief tests (TDD RED→GREEN)
# ---------------------------------------------------------------------------


def test_new_table_is_add_table():
    ops = diff({}, {"t": _tbl(id={"type": "uuid", "nullable": False, "default": None, "pk": True})})
    assert any(isinstance(o, AddTable) and o.table == "t" for o in ops)


def test_added_column():
    prev = {"t": _tbl(a=_COL)}
    curr = {"t": _tbl(a=_COL, b=_COL)}
    ops = diff(prev, curr)
    assert [o for o in ops if isinstance(o, AddColumn)][0].name == "b"


def test_dropped_column():
    ops = diff({"t": _tbl(a=_COL, b=_COL)}, {"t": _tbl(a=_COL)})
    assert [o for o in ops if isinstance(o, DropColumn)][0].name == "b"


def test_altered_column_type():
    prev = {"t": _tbl(a={**_COL, "type": "text"})}
    curr = {"t": _tbl(a={**_COL, "type": "integer"})}
    ops = diff(prev, curr)
    alt = [o for o in ops if isinstance(o, AlterColumn)][0]
    assert alt.old["type"] == "text" and alt.new["type"] == "integer"


def test_dropped_table():
    ops = diff({"t": _tbl(a=_COL)}, {})
    assert any(isinstance(o, DropTable) and o.table == "t" for o in ops)


def test_no_change_empty_delta():
    assert diff({"t": _tbl(a=_COL)}, {"t": _tbl(a=_COL)}) == []


# ---------------------------------------------------------------------------
# diff() — extra cases: FK, index, unique, ordering
# ---------------------------------------------------------------------------


def test_add_fk():
    # Legacy {col: table} input is upgraded by _coerce_fks to a composite single-col FK.
    prev = {"t": _tbl(a=_COL)}
    curr = {"t": {**_tbl(a=_COL), "fks": {"a": "other"}}}
    ops = diff(prev, curr)
    assert any(
        isinstance(o, AddForeignKey)
        and o.columns == ("a",)
        and o.ref_table == "other"
        and o.ref_columns == ("id",)
        for o in ops
    )


def test_drop_fk():
    prev = {"t": {**_tbl(a=_COL), "fks": {"a": "other"}}}
    curr = {"t": _tbl(a=_COL)}
    ops = diff(prev, curr)
    assert any(isinstance(o, DropForeignKey) and o.columns == ("a",) for o in ops)


def test_composite_fk_and_unique_roundtrip():
    """#1464: composite FK + composite UNIQUE survive the diff as single ops."""
    prev = {"Project": _tbl(tenant_id=_COL, owner=_COL)}
    curr = {
        "Project": {
            **_tbl(tenant_id=_COL, owner=_COL),
            "fks": [(("tenant_id", "owner"), "Member", ("tenant_id", "id"))],
            "uniques": [("tenant_id", "id")],
        }
    }
    ops = diff(prev, curr)
    assert any(
        isinstance(o, AddForeignKey)
        and o.columns == ("tenant_id", "owner")
        and o.ref_table == "Member"
        and o.ref_columns == ("tenant_id", "id")
        for o in ops
    )
    assert any(isinstance(o, AddUnique) and o.columns == ("tenant_id", "id") for o in ops)


def test_diff_add_index():
    prev = {"t": _tbl(a=_COL)}
    curr = {"t": {**_tbl(a=_COL), "indexes": ["a"]}}
    ops = diff(prev, curr)
    assert any(isinstance(o, AddIndex) and o.column == "a" for o in ops)


def test_diff_drop_index():
    prev = {"t": {**_tbl(a=_COL), "indexes": ["a"]}}
    curr = {"t": _tbl(a=_COL)}
    ops = diff(prev, curr)
    assert any(isinstance(o, DropIndex) and o.column == "a" for o in ops)


def test_diff_add_unique():
    prev = {"t": _tbl(a=_COL)}
    curr = {"t": {**_tbl(a=_COL), "uniques": ["a"]}}
    ops = diff(prev, curr)
    assert any(isinstance(o, AddUnique) and o.columns == ("a",) for o in ops)


def test_diff_drop_unique():
    prev = {"t": {**_tbl(a=_COL), "uniques": ["a"]}}
    curr = {"t": _tbl(a=_COL)}
    ops = diff(prev, curr)
    assert any(isinstance(o, DropUnique) and o.columns == ("a",) for o in ops)


def test_ordering_add_before_drop():
    """AddTable ops precede DropTable ops in the returned list."""
    prev = {"old": _tbl(a=_COL)}
    curr = {"new": _tbl(b=_COL)}
    ops = diff(prev, curr)
    add_pos = next(i for i, o in enumerate(ops) if isinstance(o, AddTable))
    drop_pos = next(i for i, o in enumerate(ops) if isinstance(o, DropTable))
    assert add_pos < drop_pos


def test_ordering_add_col_before_drop_col():
    """AddColumn precedes DropColumn within same table diff."""
    prev = {"t": _tbl(a=_COL, b=_COL)}
    curr = {"t": _tbl(a=_COL, c=_COL)}
    ops = diff(prev, curr)
    add_pos = next(i for i, o in enumerate(ops) if isinstance(o, AddColumn))
    drop_pos = next(i for i, o in enumerate(ops) if isinstance(o, DropColumn))
    assert add_pos < drop_pos


def test_drop_table_carries_snap():
    """DropTable.snap carries the prior table snapshot."""
    snap = _tbl(a=_COL)
    ops = diff({"t": snap}, {})
    dt = next(o for o in ops if isinstance(o, DropTable))
    assert dt.snap == snap


def test_add_table_fks_roundtrip():
    """AddTable.fks carries the composite FK specs from the snapshot (#1464)."""
    snap = {
        "new_t": {
            "columns": {"owner_id": _COL},
            "fks": {"owner_id": "users"},  # legacy input, upgraded by _coerce_fks
            "indexes": [],
            "uniques": [],
        }
    }
    ops = diff({}, snap)
    at = next(o for o in ops if isinstance(o, AddTable))
    assert at.fks == [(("owner_id",), "users", ("id",))]


def test_new_table_fks_emitted_as_separate_addforeignkey_ops():
    """A new table's FKs become separate AddForeignKey ops (rendered as post-create
    op.create_foreign_key), so cyclic / self-referential FKs work without inline
    create-table FKs. Regression: the engine previously dropped new-table FKs
    entirely (only AddTable, no AddForeignKey)."""
    snap = {
        "new_t": {
            "columns": {"owner_id": _COL, "parent_id": _COL},
            "fks": {"owner_id": "users", "parent_id": "new_t"},  # incl. self-ref
            "indexes": [],
            "uniques": [],
        }
    }
    ops = diff({}, snap)
    fk_ops = [o for o in ops if isinstance(o, AddForeignKey)]
    assert {(o.columns, o.ref_table) for o in fk_ops} == {
        (("owner_id",), "users"),
        (("parent_id",), "new_t"),
    }


def test_new_table_fks_ordered_after_all_table_creates():
    """Every AddTable must precede every new-table AddForeignKey so the referenced
    table exists when the FK is added (covers the cyclic case)."""
    snap = {
        "a": {"columns": {"b_id": _COL}, "fks": {"b_id": "b"}, "indexes": [], "uniques": []},
        "b": {"columns": {"a_id": _COL}, "fks": {"a_id": "a"}, "indexes": [], "uniques": []},
    }
    ops = diff({}, snap)
    last_add_table = max(i for i, o in enumerate(ops) if isinstance(o, AddTable))
    first_fk = min(i for i, o in enumerate(ops) if isinstance(o, AddForeignKey))
    assert first_fk > last_add_table


def test_add_table_frozen():
    """AddTable is frozen and fields are accessible."""
    op = AddTable(
        table="users",
        columns={"id": {"type": "uuid"}, "name": {"type": "varchar"}},
        fks={},
        indexes=[],
        uniques=[],
    )
    assert op.table == "users"
    assert op.columns == {"id": {"type": "uuid"}, "name": {"type": "varchar"}}
    assert op.fks == {}
    assert op.indexes == []
    assert op.uniques == []

    # Assert frozen
    with pytest.raises(FrozenInstanceError):
        op.table = "other_users"


def test_drop_table_with_snap():
    """DropTable carries prior table snapshot for downgrade."""
    prior_snap = {
        "columns": {"id": {"type": "uuid"}, "name": {"type": "varchar"}},
        "fks": {},
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
    """AddForeignKey specifies table, columns, ref table, and ref columns (#1464)."""
    op = AddForeignKey(table="orders", columns=("user_id",), ref_table="users", ref_columns=("id",))
    assert op.table == "orders"
    assert op.columns == ("user_id",)
    assert op.ref_table == "users"
    assert op.ref_columns == ("id",)

    # Assert frozen
    with pytest.raises(FrozenInstanceError):
        op.table = "invoices"


def test_drop_foreign_key():
    """DropForeignKey specifies table, columns, ref table, and ref columns (#1464)."""
    op = DropForeignKey(
        table="orders", columns=("user_id",), ref_table="users", ref_columns=("id",)
    )
    assert op.table == "orders"
    assert op.columns == ("user_id",)
    assert op.ref_table == "users"

    # Assert frozen
    with pytest.raises(FrozenInstanceError):
        op.columns = ("account_id",)


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
    """AddUnique specifies table and columns (#1464)."""
    op = AddUnique(table="users", columns=("email",))
    assert op.table == "users"
    assert op.columns == ("email",)

    # Assert frozen
    with pytest.raises(FrozenInstanceError):
        op.table = "accounts"


def test_drop_unique():
    """DropUnique specifies table and columns (#1464)."""
    op = DropUnique(table="users", columns=("email",))
    assert op.table == "users"
    assert op.columns == ("email",)

    # Assert frozen
    with pytest.raises(FrozenInstanceError):
        op.columns = ("username",)


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
        AddForeignKey("t8", ("c5",), "t_ref", ("id",)),
        DropForeignKey("t9", ("c6",), "t_ref", ("id",)),
        AddIndex("t10", "c7"),
        DropIndex("t11", "c8"),
        AddUnique("t12", ("c9",)),
        DropUnique("t13", ("c10",)),
    ]
    assert len(ops) == 13


# ---------------------------------------------------------------------------
# Task 4.3: rename resolution via hints
# ---------------------------------------------------------------------------


def test_was_hint_renders_rename_not_drop_add():
    prev = {"t": _tbl(old_name=_COL)}
    curr = {"t": _tbl(new_name=_COL)}
    hints = {"tables": {}, "columns": {("t", "new_name"): "old_name"}}
    ops = diff(prev, curr, hints)
    assert any(
        isinstance(o, RenameColumn) and o.old == "old_name" and o.new == "new_name" for o in ops
    )
    # Must NOT produce drop+add for the renamed pair
    assert not any(isinstance(o, DropColumn) and o.name == "old_name" for o in ops)
    assert not any(isinstance(o, AddColumn) and o.name == "new_name" for o in ops)


def test_already_applied_rename_is_noop():
    prev = {"t": _tbl(new_name=_COL)}  # already renamed
    curr = {"t": _tbl(new_name=_COL)}
    hints = {"tables": {}, "columns": {("t", "new_name"): "old_name"}}
    assert diff(prev, curr, hints) == []


def test_dangling_rename_raises():
    prev = {"t": _tbl(a=_COL)}
    curr = {"t": _tbl(b=_COL)}
    hints = {"tables": {}, "columns": {("t", "b"): "nonexistent"}}
    with pytest.raises(RenameResolutionError):
        diff(prev, curr, hints)


def test_table_rename_hint():
    prev = {"old_tbl": _tbl(a=_COL)}
    curr = {"new_tbl": _tbl(a=_COL)}
    hints = {"tables": {"new_tbl": "old_tbl"}, "columns": {}}
    ops = diff(prev, curr, hints)
    assert any(
        isinstance(o, RenameTable) and o.old == "old_tbl" and o.new == "new_tbl" for o in ops
    )
    assert not any(isinstance(o, AddTable) and o.table == "new_tbl" for o in ops)
    assert not any(isinstance(o, DropTable) and o.table == "old_tbl" for o in ops)


def test_table_rename_already_applied_noop():
    prev = {"new_tbl": _tbl(a=_COL)}
    curr = {"new_tbl": _tbl(a=_COL)}
    hints = {"tables": {"new_tbl": "old_tbl"}, "columns": {}}
    assert diff(prev, curr, hints) == []


# ---------------------------------------------------------------------------
# Task 4.3 follow-on: rename + simultaneous type change in one diff (#1431)
# ---------------------------------------------------------------------------


def test_rename_and_retype_emits_rename_then_alter():
    """Column renamed AND retyped in one diff → RenameColumn + AlterColumn, in that order."""
    prev = {"t": _tbl(old_name={**_COL, "type": "text"})}
    curr = {"t": _tbl(new_name={**_COL, "type": "integer"})}
    hints = {"tables": {}, "columns": {("t", "new_name"): "old_name"}}
    ops = diff(prev, curr, hints)

    rename_ops = [o for o in ops if isinstance(o, RenameColumn)]
    alter_ops = [o for o in ops if isinstance(o, AlterColumn)]

    # Both ops must be present
    assert len(rename_ops) == 1, f"Expected 1 RenameColumn, got {rename_ops}"
    assert len(alter_ops) == 1, f"Expected 1 AlterColumn, got {alter_ops}"

    rename = rename_ops[0]
    alter = alter_ops[0]

    assert rename.old == "old_name"
    assert rename.new == "new_name"
    assert alter.name == "new_name"
    assert alter.old["type"] == "text"
    assert alter.new["type"] == "integer"

    # RenameColumn must precede AlterColumn
    rename_pos = ops.index(rename)
    alter_pos = ops.index(alter)
    assert rename_pos < alter_pos, "RenameColumn must come before AlterColumn"

    # Must NOT produce spurious DropColumn/AddColumn for the renamed column
    assert not any(isinstance(o, DropColumn) and o.name == "old_name" for o in ops)
    assert not any(isinstance(o, AddColumn) and o.name == "new_name" for o in ops)
    assert not any(isinstance(o, AddColumn) and o.name == "old_name" for o in ops)
    assert not any(isinstance(o, DropColumn) and o.name == "new_name" for o in ops)


def test_pure_rename_no_spurious_alter():
    """Column renamed with no spec change → only RenameColumn, no AlterColumn."""
    prev = {"t": _tbl(old_name=_COL)}
    curr = {"t": _tbl(new_name=_COL)}
    hints = {"tables": {}, "columns": {("t", "new_name"): "old_name"}}
    ops = diff(prev, curr, hints)

    assert any(
        isinstance(o, RenameColumn) and o.old == "old_name" and o.new == "new_name" for o in ops
    )
    assert not any(isinstance(o, AlterColumn) for o in ops)
