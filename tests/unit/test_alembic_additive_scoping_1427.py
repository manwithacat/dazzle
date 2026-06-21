"""#1427: autogenerate is scoped to additive ops (no destructive whole-schema rewrite).

`dazzle db revision --autogenerate` diffs the DSL→SQLAlchemy metadata against the
live DB; a type-mapping mismatch (text↔uuid PKs) or any schema drift otherwise
becomes a destructive rewrite (alter PK type, drop live columns, drop tables).
`scope_upgrade_to_additive` strips the data-destructive ops so a routine revision
can only ever CREATE / ADD, and logs what it suppressed.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic.operations import ops as alembic_ops

from dazzle.http.alembic.directive_scoping import scope_upgrade_to_additive


def _mixed_upgrade() -> alembic_ops.UpgradeOps:
    """An upgrade tree like the #1427 repro: one genuinely-new table (additive),
    plus destructive drift on existing tables (PK type churn, dropped live column,
    a dropped table)."""
    return alembic_ops.UpgradeOps(
        ops=[
            # additive — a new entity's table (must survive)
            alembic_ops.CreateTableOp(
                "invoices",
                [sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("total", sa.Integer())],
            ),
            # destructive drift on a pre-existing table
            alembic_ops.ModifyTableOps(
                "customers",
                ops=[
                    # additive sub-op (must survive)
                    alembic_ops.AddColumnOp("customers", sa.Column("vip", sa.Boolean())),
                    # text→uuid PK churn (must be stripped)
                    alembic_ops.AlterColumnOp(
                        "customers", "id", existing_type=sa.Text(), modify_type=sa.Uuid()
                    ),
                    # live column drop (must be stripped)
                    alembic_ops.DropColumnOp("customers", sa.Column("legacy_note", sa.Text())),
                ],
            ),
            # a table whose only changes are destructive → whole modify dropped
            alembic_ops.ModifyTableOps(
                "orders",
                ops=[alembic_ops.DropColumnOp("orders", sa.Column("old_col", sa.Text()))],
            ),
            # drop a whole live table (must be stripped)
            alembic_ops.DropTableOp("audit_legacy"),
        ]
    )


def test_destructive_ops_stripped_additive_kept() -> None:
    up = _mixed_upgrade()
    scope_upgrade_to_additive(up)

    # Only the additive ops survive: the new table + the AddColumn-bearing modify.
    assert len(up.ops) == 2
    assert isinstance(up.ops[0], alembic_ops.CreateTableOp)
    assert up.ops[0].table_name == "invoices"
    modify = up.ops[1]
    assert isinstance(modify, alembic_ops.ModifyTableOps)
    assert modify.table_name == "customers"
    assert len(modify.ops) == 1
    assert isinstance(modify.ops[0], alembic_ops.AddColumnOp)


def test_dropped_ops_are_reported_for_logging() -> None:
    up = _mixed_upgrade()
    dropped = scope_upgrade_to_additive(up)
    # Every suppressed op is named (never silent).
    assert "alter_column customers.id" in dropped
    assert "drop_column customers.legacy_note" in dropped
    assert "drop_column orders.old_col" in dropped
    assert "drop_table audit_legacy" in dropped
    assert len(dropped) == 4


def test_all_additive_is_unchanged_and_reverses_cleanly() -> None:
    up = alembic_ops.UpgradeOps(
        ops=[alembic_ops.CreateTableOp("invoices", [sa.Column("id", sa.Uuid(), primary_key=True)])]
    )
    dropped = scope_upgrade_to_additive(up)
    assert dropped == []
    assert len(up.ops) == 1
    # The downgrade of an additive upgrade is its clean inverse (drop the new table).
    down = up.reverse()
    assert any(isinstance(o, alembic_ops.DropTableOp) for o in down.ops)


def test_entirely_destructive_upgrade_becomes_empty() -> None:
    up = alembic_ops.UpgradeOps(
        ops=[
            alembic_ops.DropTableOp("gone"),
            alembic_ops.ModifyTableOps(
                "t", ops=[alembic_ops.DropColumnOp("t", sa.Column("c", sa.Text()))]
            ),
        ]
    )
    dropped = scope_upgrade_to_additive(up)
    assert up.is_empty()
    assert len(dropped) == 2
