"""Tests for schema diff operations."""

import dataclasses
from dataclasses import FrozenInstanceError
from typing import Any

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
_PK = {"type": "uuid", "nullable": False, "default": None, "pk": True}


def _tbl(**cols):
    return {"columns": cols, "indexes": [], "uniques": [], "fks": {}}


def _with(table: dict[str, Any], **extra: Any) -> dict[str, Any]:
    return {**table, **extra}


# ---------------------------------------------------------------------------
# diff() — one structural change yields exactly the matching op
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("prev", "curr", "expected"),
    [
        pytest.param(
            {},
            {"t": _tbl(id=_PK)},
            [AddTable(table="t", columns={"id": _PK}, fks=[], indexes=[], uniques=[])],
            id="new-table",
        ),
        # DropTable.snap carries the prior table snapshot (for downgrade).
        pytest.param(
            {"t": _tbl(a=_COL)}, {}, [DropTable(table="t", snap=_tbl(a=_COL))], id="dropped-table"
        ),
        pytest.param(
            {"t": _tbl(a=_COL)},
            {"t": _tbl(a=_COL, b=_COL)},
            [AddColumn(table="t", name="b", col=_COL)],
            id="added-column",
        ),
        pytest.param(
            {"t": _tbl(a=_COL, b=_COL)},
            {"t": _tbl(a=_COL)},
            [DropColumn(table="t", name="b", col=_COL)],
            id="dropped-column",
        ),
        pytest.param(
            {"t": _tbl(a={**_COL, "type": "text"})},
            {"t": _tbl(a={**_COL, "type": "integer"})},
            [
                AlterColumn(
                    table="t",
                    name="a",
                    old={**_COL, "type": "text"},
                    new={**_COL, "type": "integer"},
                )
            ],
            id="altered-column-type",
        ),
        # Legacy {col: table} input is upgraded by _coerce_fks to a composite single-col FK.
        pytest.param(
            {"t": _tbl(a=_COL)},
            {"t": _with(_tbl(a=_COL), fks={"a": "other"})},
            [AddForeignKey(table="t", columns=("a",), ref_table="other", ref_columns=("id",))],
            id="add-fk",
        ),
        pytest.param(
            {"t": _with(_tbl(a=_COL), fks={"a": "other"})},
            {"t": _tbl(a=_COL)},
            [DropForeignKey(table="t", columns=("a",), ref_table="other", ref_columns=("id",))],
            id="drop-fk",
        ),
        pytest.param(
            {"t": _tbl(a=_COL)},
            {"t": _with(_tbl(a=_COL), indexes=["a"])},
            [AddIndex(table="t", column="a")],
            id="add-index",
        ),
        pytest.param(
            {"t": _with(_tbl(a=_COL), indexes=["a"])},
            {"t": _tbl(a=_COL)},
            [DropIndex(table="t", column="a")],
            id="drop-index",
        ),
        pytest.param(
            {"t": _tbl(a=_COL)},
            {"t": _with(_tbl(a=_COL), uniques=["a"])},
            [AddUnique(table="t", columns=("a",))],
            id="add-unique",
        ),
        pytest.param(
            {"t": _with(_tbl(a=_COL), uniques=["a"])},
            {"t": _tbl(a=_COL)},
            [DropUnique(table="t", columns=("a",))],
            id="drop-unique",
        ),
        # AddTable.fks carries the composite FK specs from the snapshot (legacy
        # input upgraded by _coerce_fks), and the FK is also emitted as its own
        # AddForeignKey op (#1464).
        pytest.param(
            {},
            {"new_t": _with(_tbl(owner_id=_COL), fks={"owner_id": "users"})},
            [
                AddTable(
                    table="new_t",
                    columns={"owner_id": _COL},
                    fks=[(("owner_id",), "users", ("id",))],
                    indexes=[],
                    uniques=[],
                ),
                AddForeignKey(
                    table="new_t", columns=("owner_id",), ref_table="users", ref_columns=("id",)
                ),
            ],
            id="add-table-fks-roundtrip-1464",
        ),
    ],
)
def test_diff_emits_exactly_the_matching_op(
    prev: dict[str, Any], curr: dict[str, Any], expected: list[SchemaOp]
) -> None:
    assert diff(prev, curr) == expected


@pytest.mark.parametrize(
    ("prev", "curr", "hints"),
    [
        pytest.param({"t": _tbl(a=_COL)}, {"t": _tbl(a=_COL)}, None, id="no-change"),
        pytest.param(
            {"t": _tbl(new_name=_COL)},
            {"t": _tbl(new_name=_COL)},
            {"tables": {}, "columns": {("t", "new_name"): "old_name"}},
            id="column-rename-already-applied",
        ),
        pytest.param(
            {"new_tbl": _tbl(a=_COL)},
            {"new_tbl": _tbl(a=_COL)},
            {"tables": {"new_tbl": "old_tbl"}, "columns": {}},
            id="table-rename-already-applied",
        ),
    ],
)
def test_diff_is_empty_when_nothing_changed(
    prev: dict[str, Any], curr: dict[str, Any], hints: dict[str, Any] | None
) -> None:
    assert diff(prev, curr, hints) == []


# ---------------------------------------------------------------------------
# diff() — extra cases: composite FK/unique, ordering
# ---------------------------------------------------------------------------


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


@pytest.mark.parametrize(
    ("prev", "curr", "earlier", "later"),
    [
        # A composite FK `(tenant_id, ref) → Zparent(tenant_id, id)` needs
        # Zparent's UNIQUE(tenant_id, id) to exist first, else Postgres raises
        # "no unique constraint matching given keys" — even when the referenced
        # parent sorts AFTER the child (ops are emitted in sorted-table order).
        pytest.param(
            {},
            {
                "Child": {
                    "columns": {"tenant_id": _COL, "ref": _COL},
                    "fks": [(("tenant_id", "ref"), "Zparent", ("tenant_id", "id"))],
                    "indexes": [],
                    "uniques": [("tenant_id", "id")],
                },
                "Zparent": {
                    "columns": {"tenant_id": _COL},
                    "fks": [],
                    "indexes": [],
                    "uniques": [("tenant_id", "id")],
                },
            },
            AddUnique,
            AddForeignKey,
            id="uniques-before-fks-cross-table-1464",
        ),
        # The referenced table must exist when the FK is added (cyclic case).
        pytest.param(
            {},
            {
                "a": _with(_tbl(b_id=_COL), fks={"b_id": "b"}),
                "b": _with(_tbl(a_id=_COL), fks={"a_id": "a"}),
            },
            AddTable,
            AddForeignKey,
            id="new-table-fks-after-all-table-creates",
        ),
        pytest.param(
            {"old": _tbl(a=_COL)},
            {"new": _tbl(b=_COL)},
            AddTable,
            DropTable,
            id="add-table-before-drop-table",
        ),
        pytest.param(
            {"t": _tbl(a=_COL, b=_COL)},
            {"t": _tbl(a=_COL, c=_COL)},
            AddColumn,
            DropColumn,
            id="add-column-before-drop-column",
        ),
    ],
)
def test_diff_orders_every_earlier_op_before_every_later_op(
    prev: dict[str, Any], curr: dict[str, Any], earlier: type, later: type
) -> None:
    ops = diff(prev, curr)
    last_earlier = max(i for i, o in enumerate(ops) if isinstance(o, earlier))
    first_later = min(i for i, o in enumerate(ops) if isinstance(o, later))
    assert last_earlier < first_later


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


# ---------------------------------------------------------------------------
# Op dataclasses: every SchemaOp member stores its fields and is frozen
# ---------------------------------------------------------------------------

_PRIOR_SNAP = {
    "columns": {"id": {"type": "uuid"}, "name": {"type": "varchar"}},
    "fks": {},
    "indexes": [],
    "uniques": [],
}


@pytest.mark.parametrize(
    ("op", "fields", "frozen_attr", "new_value"),
    [
        pytest.param(
            AddTable(
                table="users",
                columns={"id": {"type": "uuid"}, "name": {"type": "varchar"}},
                fks={},
                indexes=[],
                uniques=[],
            ),
            {
                "table": "users",
                "columns": {"id": {"type": "uuid"}, "name": {"type": "varchar"}},
                "fks": {},
                "indexes": [],
                "uniques": [],
            },
            "table",
            "other_users",
            id="AddTable",
        ),
        # DropTable carries the prior table snapshot for downgrade.
        pytest.param(
            DropTable(table="users", snap=_PRIOR_SNAP),
            {"table": "users", "snap": _PRIOR_SNAP},
            "table",
            "other_users",
            id="DropTable",
        ),
        pytest.param(
            RenameTable(old="users", new="accounts"),
            {"old": "users", "new": "accounts"},
            "old",
            "members",
            id="RenameTable",
        ),
        pytest.param(
            AddColumn(table="users", name="email", col={"type": "varchar", "nullable": False}),
            {"table": "users", "name": "email", "col": {"type": "varchar", "nullable": False}},
            "table",
            "accounts",
            id="AddColumn",
        ),
        # DropColumn carries the prior column snapshot for downgrade.
        pytest.param(
            DropColumn(table="users", name="email", col={"type": "varchar", "nullable": True}),
            {"table": "users", "name": "email", "col": {"type": "varchar", "nullable": True}},
            "name",
            "phone",
            id="DropColumn",
        ),
        pytest.param(
            RenameColumn(table="users", old="user_name", new="username"),
            {"table": "users", "old": "user_name", "new": "username"},
            "table",
            "accounts",
            id="RenameColumn",
        ),
        pytest.param(
            AlterColumn(
                table="users",
                name="email",
                old={"type": "varchar", "nullable": True},
                new={"type": "varchar", "nullable": False},
            ),
            {
                "table": "users",
                "name": "email",
                "old": {"type": "varchar", "nullable": True},
                "new": {"type": "varchar", "nullable": False},
            },
            "name",
            "phone",
            id="AlterColumn",
        ),
        pytest.param(
            AddForeignKey(
                table="orders", columns=("user_id",), ref_table="users", ref_columns=("id",)
            ),
            {
                "table": "orders",
                "columns": ("user_id",),
                "ref_table": "users",
                "ref_columns": ("id",),
            },
            "table",
            "invoices",
            id="AddForeignKey-1464",
        ),
        pytest.param(
            DropForeignKey(
                table="orders", columns=("user_id",), ref_table="users", ref_columns=("id",)
            ),
            {
                "table": "orders",
                "columns": ("user_id",),
                "ref_table": "users",
                "ref_columns": ("id",),
            },
            "columns",
            ("account_id",),
            id="DropForeignKey-1464",
        ),
        pytest.param(
            AddIndex(table="users", column="email"),
            {"table": "users", "column": "email"},
            "table",
            "accounts",
            id="AddIndex",
        ),
        pytest.param(
            DropIndex(table="users", column="email"),
            {"table": "users", "column": "email"},
            "column",
            "username",
            id="DropIndex",
        ),
        pytest.param(
            AddUnique(table="users", columns=("email",)),
            {"table": "users", "columns": ("email",)},
            "table",
            "accounts",
            id="AddUnique-1464",
        ),
        pytest.param(
            DropUnique(table="users", columns=("email",)),
            {"table": "users", "columns": ("email",)},
            "columns",
            ("username",),
            id="DropUnique-1464",
        ),
    ],
)
def test_schema_op_stores_fields_and_is_frozen(
    op: SchemaOp, fields: dict[str, Any], frozen_attr: str, new_value: Any
) -> None:
    assert isinstance(op, SchemaOp)
    assert {f.name: getattr(op, f.name) for f in dataclasses.fields(op)} == fields

    with pytest.raises(FrozenInstanceError):
        setattr(op, frozen_attr, new_value)


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
