"""#1460: cyclic / self-referential FKs are hoisted to post-create op.create_foreign_key.

SQLAlchemy marks a foreign key ``use_alter=True`` when it participates in a table
dependency cycle or self-reference; ``create_all`` emits it as a trailing
``ALTER TABLE … ADD CONSTRAINT``. Alembic autogenerate keeps it inline in the
``CreateTableOp`` — but ``CreateTable`` DDL *omits* ``use_alter`` constraints and
Alembic emits no ALTER, so the FK silently disappears from a ``dazzle db baseline``
schema. ``hoist_cyclic_create_fks`` reproduces ``create_all``'s behaviour.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic.operations import ops as alembic_ops

from dazzle.http.alembic.directive_scoping import hoist_cyclic_create_fks


def _cyclic_upgrade() -> alembic_ops.UpgradeOps:
    """A baseline-style upgrade: three new tables forming an Org↔Person cycle plus
    a Node self-reference. The cyclic/self-ref FKs carry ``use_alter=True`` exactly
    as Dazzle's sa_schema builds them. Built via ``CreateTableOp.from_table`` so the
    constraints are column-bound exactly as Alembic autogenerate produces them."""
    md = sa.MetaData()
    org = sa.Table(
        "Org",
        md,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner", sa.Uuid()),
        sa.ForeignKeyConstraint(
            ["owner"], ["Person.id"], name="fk_Org_owner_Person", use_alter=True
        ),
    )
    person = sa.Table(
        "Person",
        md,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("org", sa.Uuid()),
        sa.ForeignKeyConstraint(["org"], ["Org.id"], name="fk_Person_org_Org", use_alter=True),
    )
    node = sa.Table(
        "Node",
        md,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("parent", sa.Uuid()),
        sa.ForeignKeyConstraint(
            ["parent"], ["Node.id"], name="fk_Node_parent_Node", use_alter=True
        ),
    )
    return alembic_ops.UpgradeOps(
        ops=[alembic_ops.CreateTableOp.from_table(t) for t in (org, person, node)]
    )


def _fk_ops(up: alembic_ops.UpgradeOps) -> list[alembic_ops.CreateForeignKeyOp]:
    return [o for o in up.ops if isinstance(o, alembic_ops.CreateForeignKeyOp)]


def _table_op(up: alembic_ops.UpgradeOps, name: str) -> alembic_ops.CreateTableOp:
    return next(
        o for o in up.ops if isinstance(o, alembic_ops.CreateTableOp) and o.table_name == name
    )


def test_use_alter_fks_are_hoisted_to_trailing_create_fk() -> None:
    up = _cyclic_upgrade()
    hoisted = hoist_cyclic_create_fks(up)

    # All three cyclic/self-ref FKs are reported and emitted as create_foreign_key.
    assert set(hoisted) == {
        "fk_Org_owner_Person",
        "fk_Person_org_Org",
        "fk_Node_parent_Node",
    }
    fk_ops = _fk_ops(up)
    assert len(fk_ops) == 3
    assert {o.constraint_name for o in fk_ops} == set(hoisted)


def test_inline_fks_are_stripped_from_create_table() -> None:
    up = _cyclic_upgrade()
    hoist_cyclic_create_fks(up)

    # No CreateTableOp keeps an inline ForeignKeyConstraint (they'd be dropped by
    # the CreateTable compiler — the bug). PK constraints stay.
    for op in up.ops:
        if isinstance(op, alembic_ops.CreateTableOp):
            assert not any(isinstance(c, sa.ForeignKeyConstraint) for c in op.columns), (
                f"{op.table_name} still has an inline FK"
            )
            assert any(isinstance(c, sa.PrimaryKeyConstraint) for c in op.columns), (
                f"{op.table_name} lost its PK"
            )


def test_fk_ops_come_after_all_table_creations() -> None:
    up = _cyclic_upgrade()
    hoist_cyclic_create_fks(up)

    last_create = max(i for i, o in enumerate(up.ops) if isinstance(o, alembic_ops.CreateTableOp))
    first_fk = min(i for i, o in enumerate(up.ops) if isinstance(o, alembic_ops.CreateForeignKeyOp))
    assert first_fk > last_create, "FKs must be added after every table exists"


def test_downgrade_drops_fks_before_tables() -> None:
    up = _cyclic_upgrade()
    hoist_cyclic_create_fks(up)
    down = up.reverse()

    first_drop_table = min(
        i for i, o in enumerate(down.ops) if isinstance(o, alembic_ops.DropTableOp)
    )
    drop_constraints = [
        i for i, o in enumerate(down.ops) if isinstance(o, alembic_ops.DropConstraintOp)
    ]
    assert len(drop_constraints) == 3
    assert max(drop_constraints) < first_drop_table, (
        "cyclic FK constraints must be dropped before their tables"
    )


def test_noop_when_no_use_alter_fks() -> None:
    up = alembic_ops.UpgradeOps(
        ops=[alembic_ops.CreateTableOp("plain", [sa.Column("id", sa.Uuid(), primary_key=True)])]
    )
    hoisted = hoist_cyclic_create_fks(up)
    assert hoisted == []
    assert len(up.ops) == 1
    assert not _fk_ops(up)


def test_non_use_alter_fk_stays_inline() -> None:
    """A plain (acyclic) FK has ``use_alter=False`` and must stay inline — Alembic
    renders those correctly, so hoisting them would be needless churn."""
    md = sa.MetaData()
    sa.Table("parent", md, sa.Column("id", sa.Uuid(), primary_key=True))
    child = sa.Table(
        "child",
        md,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("parent_id", sa.Uuid()),
        sa.ForeignKeyConstraint(["parent_id"], ["parent.id"], name="fk_child_parent"),
    )
    up = alembic_ops.UpgradeOps(ops=[alembic_ops.CreateTableOp.from_table(child)])
    hoisted = hoist_cyclic_create_fks(up)
    assert hoisted == []
    assert not _fk_ops(up)
    child = _table_op(up, "child")
    assert any(isinstance(c, sa.ForeignKeyConstraint) for c in child.columns)
