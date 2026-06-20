"""#1226 — back-side EntitySpec now carries soft_delete + temporal fields.

Prior to #1226 the converter dropped IR's `soft_delete` and `temporal`
because the back-side EntitySpec didn't declare them. Runtime code
worked around it with `getattr(entity, "...", default)` at 11 sites.

These tests pin the new contract: the converter threads both fields
through, so runtime can use direct attribute access.
"""

from __future__ import annotations

from dazzle.core import ir
from dazzle.http.converters.entity_converter import convert_entity
from dazzle.http.specs.entity import EntitySpec as BackEntitySpec


def _id_field() -> ir.FieldSpec:
    return ir.FieldSpec(
        name="id",
        type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
        modifiers=[ir.FieldModifier.PK],
    )


def _date_field(name: str, *, required: bool = False) -> ir.FieldSpec:
    mods = [ir.FieldModifier.REQUIRED] if required else []
    return ir.FieldSpec(
        name=name,
        type=ir.FieldType(kind=ir.FieldTypeKind.DATE),
        modifiers=mods,
    )


class TestSoftDeleteThreaded:
    def test_soft_delete_false_by_default(self) -> None:
        ir_entity = ir.EntitySpec(name="Plain", fields=[_id_field()])
        back = convert_entity(ir_entity)
        assert isinstance(back, BackEntitySpec)
        assert back.soft_delete is False

    def test_soft_delete_true_is_threaded(self) -> None:
        ir_entity = ir.EntitySpec(
            name="WithTombstone",
            fields=[_id_field()],
            soft_delete=True,
        )
        back = convert_entity(ir_entity)
        assert back.soft_delete is True


class TestTemporalThreaded:
    def test_temporal_none_by_default(self) -> None:
        ir_entity = ir.EntitySpec(name="Plain", fields=[_id_field()])
        back = convert_entity(ir_entity)
        assert back.temporal is None

    def test_temporal_block_is_threaded(self) -> None:
        ir_entity = ir.EntitySpec(
            name="Employment",
            fields=[
                _id_field(),
                _date_field("start_date", required=True),
                _date_field("end_date"),
                ir.FieldSpec(
                    name="person",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Person"),
                ),
            ],
            temporal=ir.TemporalSpec(
                start_field="start_date",
                end_field="end_date",
                key_field="person",
            ),
        )
        back = convert_entity(ir_entity)
        assert back.temporal is not None
        assert back.temporal.start_field == "start_date"
        assert back.temporal.end_field == "end_date"
        assert back.temporal.key_field == "person"
        assert back.temporal.default_filter == "active"
        assert back.temporal.as_of_param == "as_of"

    def test_temporal_custom_default_filter_is_threaded(self) -> None:
        ir_entity = ir.EntitySpec(
            name="Audit",
            fields=[
                _id_field(),
                _date_field("opened_at", required=True),
                _date_field("closed_at"),
                ir.FieldSpec(
                    name="subject",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                ),
            ],
            temporal=ir.TemporalSpec(
                start_field="opened_at",
                end_field="closed_at",
                key_field="subject",
                default_filter="none",
                as_of_param="snapshot",
            ),
        )
        back = convert_entity(ir_entity)
        assert back.temporal is not None
        assert back.temporal.default_filter == "none"
        assert back.temporal.as_of_param == "snapshot"


class TestDirectAttributeAccessWorks:
    """Pin that runtime code can use direct attribute access without
    AttributeError — what the 11 defensive getattr sites guarded against."""

    def test_back_entity_soft_delete_is_real_attribute(self) -> None:
        back = BackEntitySpec(name="X")
        assert back.soft_delete is False
        # No AttributeError — the attribute exists with a default.

    def test_back_entity_temporal_is_real_attribute(self) -> None:
        back = BackEntitySpec(name="X")
        assert back.temporal is None
        # No AttributeError — the attribute exists with a default.
