"""Unit tests for dazzle.db.schema_snapshot — pure MetaData introspection.

Tests build a hand-crafted MetaData; no CWD or DB access required.
"""

import sqlalchemy as sa

from dazzle.db.schema_snapshot import project_schema


def _meta() -> sa.MetaData:
    md = sa.MetaData()
    sa.Table(
        "Customer",
        md,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
    )
    sa.Table(
        "Invoice",
        md,
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("total", sa.Integer(), nullable=True),
        sa.Column("customer", sa.Uuid(), sa.ForeignKey("Customer.id")),
    )
    return md


def test_project_schema_introspects_metadata() -> None:
    snap = project_schema(_meta())
    # Table names are the entity names VERBATIM (not pluralised/lowercased).
    assert set(snap) == {"Customer", "Invoice"}
    inv = snap["Invoice"]
    assert inv["columns"]["total"]["type"] == "integer"
    assert inv["columns"]["total"]["nullable"] is True
    assert inv["columns"]["id"]["pk"] is True
    # FK column is the field name VERBATIM; target is the referenced table name.
    assert inv["fks"]["customer"] == "Customer"


def test_project_schema_is_deterministic() -> None:
    assert project_schema(_meta()) == project_schema(_meta())  # sorted, stable
