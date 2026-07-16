"""#1597 E — projection type mismatch warnings."""

from __future__ import annotations

from dazzle.core import ir
from dazzle.core.validation.surfaces import validate_surfaces

pytestmark = __import__("pytest").mark.gate


def _entity() -> ir.EntitySpec:
    return ir.EntitySpec(
        name="Task",
        title="Task",
        fields=[
            ir.FieldSpec(
                name="id",
                type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                modifiers=[ir.FieldModifier.PK],
            ),
            ir.FieldSpec(
                name="due_date",
                type=ir.FieldType(kind=ir.FieldTypeKind.DATE),
            ),
            ir.FieldSpec(
                name="title",
                type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
            ),
        ],
    )


def test_format_raw_on_date_list_field_warns() -> None:
    surface = ir.SurfaceSpec(
        name="task_list",
        title="Tasks",
        entity_ref="Task",
        mode=ir.SurfaceMode.LIST,
        sections=[
            ir.SurfaceSection(
                name="main",
                elements=[
                    ir.SurfaceElement(
                        field_name="due_date",
                        format=ir.FieldFormatSpec(kind="raw"),
                    )
                ],
            )
        ],
    )
    appspec = ir.AppSpec(
        name="t",
        domain=ir.DomainSpec(entities=[_entity()]),
        surfaces=[surface],
    )
    _errors, warnings = validate_surfaces(appspec)
    assert any("#1597" in w and "raw" in w and "due_date" in w for w in warnings)


def test_view_field_type_mismatch_warns() -> None:
    view = ir.ViewSpec(
        name="task_report",
        source_entity="Task",
        fields=[
            ir.ViewFieldSpec(
                name="due_date",
                field_type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=50),
            )
        ],
    )
    appspec = ir.AppSpec(
        name="t",
        domain=ir.DomainSpec(entities=[_entity()]),
        views=[view],
        surfaces=[],
    )
    _errors, warnings = validate_surfaces(appspec)
    assert any(
        "#1597" in w and "task_report" in w and "due_date" in w and "projection" in w
        for w in warnings
    )
