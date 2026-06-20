"""#1321 — DECIMAL columns must emit NUMERIC(p,s), not DOUBLE PRECISION.

The IR and backend spec carry `precision`/`scale` for a `decimal(p,s)` field all
the way to the DDL mappers, which previously discarded them and emitted a
binary float (`DOUBLE PRECISION` / `sa.Float`). That silently subjected every
decimal column to IEEE-754 representation error and plan-order-dependent
summation. These tests pin the exact-arithmetic mapping in both documented-mirror
DDL paths.

MONEY is deliberately NOT covered here: it is expanded into an integer
`_minor` + `_currency` column pair upstream (entity_converter), so it never
reaches these mappers as a decimal and is unaffected by the bug.
"""

from dazzle.http.runtime.pg_backend import _field_type_to_postgres
from dazzle.http.runtime.sa_schema import _field_type_to_sa
from dazzle.http.specs.entity import FieldType, ScalarType


def _decimal(precision: int | None = None, scale: int | None = None) -> FieldType:
    return FieldType(
        kind="scalar",
        scalar_type=ScalarType.DECIMAL,
        precision=precision,
        scale=scale,
    )


# ---------------------------------------------------------------------------
# Raw-DDL path (pg_backend._build_column)
# ---------------------------------------------------------------------------


def test_pg_decimal_with_precision_and_scale_emits_numeric():
    assert _field_type_to_postgres(_decimal(15, 2)) == "NUMERIC(15, 2)"


def test_pg_decimal_with_precision_only_emits_numeric():
    assert _field_type_to_postgres(_decimal(10)) == "NUMERIC(10)"


def test_pg_decimal_without_precision_emits_unconstrained_numeric():
    assert _field_type_to_postgres(_decimal()) == "NUMERIC"


def test_pg_decimal_is_never_double_precision():
    assert _field_type_to_postgres(_decimal(15, 2)) != "DOUBLE PRECISION"


def test_pg_float_stays_double_precision():
    # FLOAT is intentionally IEEE-754 (sensors, weights, scores) — must not move.
    ft = FieldType(kind="scalar", scalar_type=ScalarType.FLOAT)
    assert _field_type_to_postgres(ft) == "DOUBLE PRECISION"


# ---------------------------------------------------------------------------
# SQLAlchemy / Alembic path (sa_schema._field_to_column)
# ---------------------------------------------------------------------------


def test_sa_decimal_with_precision_and_scale_is_numeric():
    import sqlalchemy as sa

    col_type = _field_type_to_sa(_decimal(15, 2))
    assert isinstance(col_type, sa.Numeric)
    assert not isinstance(col_type, sa.Float)  # Float subclasses Numeric — be explicit
    assert col_type.precision == 15
    assert col_type.scale == 2


def test_sa_decimal_without_precision_is_unconstrained_numeric():
    import sqlalchemy as sa

    col_type = _field_type_to_sa(_decimal())
    assert isinstance(col_type, sa.Numeric)
    assert not isinstance(col_type, sa.Float)
    assert col_type.precision is None


def test_sa_float_stays_float():
    import sqlalchemy as sa

    ft = FieldType(kind="scalar", scalar_type=ScalarType.FLOAT)
    assert isinstance(_field_type_to_sa(ft), sa.Float)
