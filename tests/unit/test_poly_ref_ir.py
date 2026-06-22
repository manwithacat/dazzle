"""#1448: poly_ref field kind + PolyPathCheck predicate node IR."""

from __future__ import annotations

from pydantic import TypeAdapter

from dazzle.core.ir.fields import FieldType, FieldTypeKind
from dazzle.core.ir.predicates import (
    CompOp,
    PolyPathCheck,
    ScopePredicate,
    UserAttrCheck,
)


def test_poly_ref_field_type():
    ft = FieldType(kind=FieldTypeKind.POLY_REF, poly_targets=["CohortAssessment", "Manuscript"])
    assert ft.kind == FieldTypeKind.POLY_REF
    assert ft.poly_targets == ["CohortAssessment", "Manuscript"]


def test_poly_path_check_in_union():
    node = PolyPathCheck(
        field="target",
        type_field="target_type",
        type_value="CohortAssessment",
        id_field="target_id",
        target_entity="CohortAssessment",
        sub=UserAttrCheck(field="uploaded_by", op=CompOp.EQ, user_attr="entity_id"),
    )
    # Round-trips through the discriminated union on the "kind" tag.
    adapter = TypeAdapter(ScopePredicate)
    restored = adapter.validate_python(node.model_dump())
    assert isinstance(restored, PolyPathCheck)
    assert restored.target_entity == "CohortAssessment"
    assert isinstance(restored.sub, UserAttrCheck)
    assert restored.sub.field == "uploaded_by"
