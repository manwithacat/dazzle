"""Regression guard for #1302.

`convert_entities` dropped `display_field` when converting the IR
`EntitySpec` to the back-runtime `EntitySpec`. Runtime consumers that
read `entity_spec.display_field` (cohort_strip member labels, #1299)
therefore always saw an empty value and fell back to the raw id/UUID —
so #1299's fix was defeated one layer up. This pins that the converted
back-runtime spec carries `display_field` through.
"""

from dazzle.core.ir import EntitySpec, FieldModifier, FieldSpec, FieldType, FieldTypeKind
from dazzle.http.converters.entity_converter import convert_entities


def _ir_entity(name: str, display_field: str | None) -> EntitySpec:
    return EntitySpec(
        name=name,
        display_field=display_field,
        fields=[
            FieldSpec(
                name="id",
                type=FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
            FieldSpec(name="name", type=FieldType(kind=FieldTypeKind.STR, max_length=200)),
        ],
    )


def test_display_field_survives_conversion() -> None:
    """The exact #1302 repro: a converted entity must expose display_field."""
    conv = convert_entities([_ir_entity("TeachingGroup", "name")])
    assert hasattr(conv[0], "display_field")  # pre-fix: False
    assert conv[0].display_field == "name"  # pre-fix: attribute absent / ""


def test_display_field_none_when_unset() -> None:
    conv = convert_entities([_ir_entity("Thing", None)])
    assert conv[0].display_field is None


def test_display_field_propagated_for_all_entities() -> None:
    """Mirror the issue's batch check — none should be dropped."""
    conv = convert_entities([_ir_entity("TeachingGroup", "name"), _ir_entity("School", "title")])
    assert {e.name: e.display_field for e in conv} == {
        "TeachingGroup": "name",
        "School": "title",
    }
