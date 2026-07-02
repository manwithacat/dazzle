"""#1522 — belongs_to is ref-equivalent at the core→http boundary.

``_map_field_type`` had no BELONGS_TO branch, so a ``belongs_to X`` field fell
through to the default scalar-STR mapping: no relation registration (the
relation loader's ``"belongs_to"`` arm was dead code — it runs against
converted backend specs whose kind vocabulary is scalar/enum/ref), no
FK-display join (raw UUID leaked in repr/grid), a TEXT column with no FK
constraint, and a ``str``-typed model field. These tests pin full ref parity.
"""

from __future__ import annotations

from dazzle.core import ir
from dazzle.http.converters.entity_converter import convert_entity
from dazzle.http.runtime.relation_loader import RelationRegistry


def _entity(name: str, fields: list[ir.FieldSpec]) -> ir.EntitySpec:
    id_field = ir.FieldSpec(
        name="id",
        type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
        modifiers=[ir.FieldModifier.PK],
    )
    return ir.EntitySpec(name=name, fields=[id_field, *fields])


def _order_with_belongs_to() -> ir.EntitySpec:
    return _entity(
        "Order",
        [
            ir.FieldSpec(
                name="customer",
                type=ir.FieldType(kind=ir.FieldTypeKind.BELONGS_TO, ref_entity="Customer"),
            )
        ],
    )


def test_belongs_to_converts_to_ref_kind() -> None:
    back = convert_entity(_order_with_belongs_to())
    fk = next(f for f in back.fields if f.name == "customer")
    assert fk.type.kind == "ref"
    assert fk.type.ref_entity == "Customer"


def test_belongs_to_matches_ref_conversion_exactly() -> None:
    """belongs_to and ref to the same target must be indistinguishable downstream."""
    via_ref = _entity(
        "Order",
        [
            ir.FieldSpec(
                name="customer",
                type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Customer"),
            )
        ],
    )
    ref_field = next(f for f in convert_entity(via_ref).fields if f.name == "customer")
    bt_field = next(
        f for f in convert_entity(_order_with_belongs_to()).fields if f.name == "customer"
    )
    assert bt_field.type == ref_field.type


def test_belongs_to_registers_implicit_relation() -> None:
    """The relation loader sees kind='ref' post-conversion and registers the
    many_to_one relation — reviving the previously-dead belongs_to arm."""
    back = convert_entity(_order_with_belongs_to())
    registry = RelationRegistry.from_entities([back])
    relations = registry.get_relations("Order")
    assert len(relations) == 1
    rel = relations[0]
    assert rel.to_entity == "Customer"
    assert rel.foreign_key_field == "customer"
    assert rel.kind == "many_to_one"
