"""Unit tests for dazzle.db.schema_snapshot — pure MetaData introspection.

Tests build a hand-crafted MetaData; no CWD or DB access required.
"""

import pytest
import sqlalchemy as sa

from dazzle.db.schema_snapshot import (
    _sa_type_to_token,
    project_schema,
    render_snapshot_literal,
    snapshot_from_module,
)


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


@pytest.mark.parametrize(
    "sa_type,expected",
    [
        (sa.Text(), "text"),
        (sa.Integer(), "integer"),
        (sa.BigInteger(), "bigint"),
        (sa.Boolean(), "boolean"),
        (sa.Float(), "float"),
        (sa.Numeric(), "numeric"),
        (sa.Numeric(10, 2), "numeric(10,2)"),
        (sa.Date(), "date"),
        (sa.DateTime(timezone=True), "timestamptz"),
        (sa.Uuid(), "uuid"),
        (sa.JSON(), "json"),
    ],
)
def test_sa_type_to_token(sa_type: sa.types.TypeEngine, expected: str) -> None:
    assert _sa_type_to_token(sa_type) == expected


def test_snapshot_literal_roundtrips() -> None:
    snap = project_schema(_meta())
    literal = render_snapshot_literal(snap)
    # The literal is valid Python that evaluates back to the same dict.
    assert eval(literal) == snap  # noqa: S307 — test-only, trusted input
    # Deterministic: same input → identical source.
    assert render_snapshot_literal(snap) == literal


def test_snapshot_from_module() -> None:
    # Create a mock module with SCHEMA_SNAPSHOT.
    import types

    mod = types.ModuleType("test_mod")
    snap = project_schema(_meta())
    mod.SCHEMA_SNAPSHOT = snap  # type: ignore[attr-defined]
    assert snapshot_from_module(mod) == snap

    # Module without SCHEMA_SNAPSHOT → empty dict.
    empty_mod = types.ModuleType("empty_mod")
    assert snapshot_from_module(empty_mod) == {}
