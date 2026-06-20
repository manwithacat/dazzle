"""Regression guard for #1188.

A primary-key field must not carry ``unique=True`` on its backend ``FieldSpec``.
The PRIMARY KEY already enforces uniqueness; an extra ``unique=True`` makes the
schema builder emit a redundant *unnamed* UNIQUE constraint, which Alembic
autogenerate cannot reconcile by name and therefore re-emits on every
``dazzle db revision`` run.
"""

from dazzle.core.ir import FieldModifier, FieldSpec, FieldType, FieldTypeKind
from dazzle.http.converters.entity_converter import convert_field


def test_pk_field_not_marked_unique() -> None:
    pk = FieldSpec(
        name="id",
        type=FieldType(kind=FieldTypeKind.UUID),
        modifiers=[FieldModifier.PK],
    )
    assert convert_field(pk).unique is False


def test_explicit_unique_field_stays_unique() -> None:
    email = FieldSpec(
        name="email",
        type=FieldType(kind=FieldTypeKind.STR, max_length=200),
        modifiers=[FieldModifier.UNIQUE],
    )
    assert convert_field(email).unique is True
