"""
Widget resolution and SurfaceFieldTriple IR types.

This module provides:
- WidgetKind: enumeration of UI widget types
- _WIDGET_MAP: mapping from FieldTypeKind to WidgetKind
- resolve_widget(): derives the correct widget for a FieldSpec
- SurfaceFieldTriple: frozen Pydantic model capturing per-field UI metadata

The widget mapping mirrors the form-type logic in
``dazzle_ui/converters/template_compiler.py`` but lives in the IR layer
with no UI-layer imports, making it available to static analysis, testing
and the contract verification layer.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from dazzle.core.ir.fields import FieldSpec, FieldTypeKind


class WidgetKind(StrEnum):
    """UI widget types that can be rendered for a surface field."""

    TEXT_INPUT = "text_input"
    TEXTAREA = "textarea"
    CHECKBOX = "checkbox"
    DATE_PICKER = "date_picker"
    DATETIME_PICKER = "datetime_picker"
    NUMBER_INPUT = "number_input"
    EMAIL_INPUT = "email_input"
    ENUM_SELECT = "enum_select"
    SEARCH_SELECT = "search_select"
    MONEY_INPUT = "money_input"
    FILE_UPLOAD = "file_upload"


# Default mapping from field type kind to widget kind.
# Relationship types (REF, HAS_MANY, HAS_ONE, EMBEDS, BELONGS_TO) all map to
# SEARCH_SELECT because they always resolve against another entity.
_WIDGET_MAP: dict[FieldTypeKind, WidgetKind] = {
    FieldTypeKind.STR: WidgetKind.TEXT_INPUT,
    FieldTypeKind.TEXT: WidgetKind.TEXTAREA,
    FieldTypeKind.INT: WidgetKind.NUMBER_INPUT,
    FieldTypeKind.DECIMAL: WidgetKind.NUMBER_INPUT,
    FieldTypeKind.FLOAT: WidgetKind.NUMBER_INPUT,
    FieldTypeKind.BOOL: WidgetKind.CHECKBOX,
    FieldTypeKind.DATE: WidgetKind.DATE_PICKER,
    FieldTypeKind.DATETIME: WidgetKind.DATETIME_PICKER,
    FieldTypeKind.UUID: WidgetKind.TEXT_INPUT,
    FieldTypeKind.ENUM: WidgetKind.ENUM_SELECT,
    FieldTypeKind.REF: WidgetKind.SEARCH_SELECT,
    FieldTypeKind.EMAIL: WidgetKind.EMAIL_INPUT,
    FieldTypeKind.JSON: WidgetKind.TEXTAREA,
    FieldTypeKind.MONEY: WidgetKind.MONEY_INPUT,
    FieldTypeKind.FILE: WidgetKind.FILE_UPLOAD,
    FieldTypeKind.URL: WidgetKind.TEXT_INPUT,
    FieldTypeKind.TIMEZONE: WidgetKind.TEXT_INPUT,
    FieldTypeKind.HAS_MANY: WidgetKind.SEARCH_SELECT,
    FieldTypeKind.HAS_ONE: WidgetKind.SEARCH_SELECT,
    FieldTypeKind.EMBEDS: WidgetKind.SEARCH_SELECT,
    FieldTypeKind.BELONGS_TO: WidgetKind.SEARCH_SELECT,
}


def resolve_widget(field: FieldSpec, *, has_source: bool = False) -> WidgetKind:
    """Derive the appropriate UI widget kind for a field.

    Resolution order:
    1. ``has_source=True`` always yields ``SEARCH_SELECT`` — the field has a
       declared data source so it renders as a search/select control.
    2. UUID fields whose name ends in ``_id`` (but are not literally named
       ``"id"``) are treated as FK columns and yield ``SEARCH_SELECT``.
    3. All other fields resolve through ``_WIDGET_MAP``; unmapped kinds fall
       back to ``TEXT_INPUT``.

    Args:
        field: The ``FieldSpec`` to inspect.
        has_source: Whether the field has an explicit ``source:`` declaration
            in the DSL that points to an entity or view.

    Returns:
        The ``WidgetKind`` appropriate for rendering this field.
    """
    if has_source:
        return WidgetKind.SEARCH_SELECT

    # UUID FK column convention: foo_id → SEARCH_SELECT, but plain 'id' stays TEXT_INPUT
    if field.type.kind == FieldTypeKind.UUID and field.name != "id" and field.name.endswith("_id"):
        return WidgetKind.SEARCH_SELECT

    return _WIDGET_MAP.get(field.type.kind, WidgetKind.TEXT_INPUT)


class SurfaceFieldTriple(BaseModel):
    """Frozen snapshot of per-field UI metadata for a surface.

    Captures everything the contract verification and template layers need to
    know about how a single field should be rendered, without re-deriving it
    from the raw FieldSpec on every pass.

    Attributes:
        field_name: The DSL field identifier.
        widget: The resolved widget kind for this field.
        is_required: Whether the field carries the ``required`` modifier.
        is_fk: Whether this field is a foreign-key reference to another entity.
        ref_entity: Name of the referenced entity when ``is_fk`` is ``True``.
    """

    model_config = ConfigDict(frozen=True)

    field_name: str
    widget: WidgetKind
    is_required: bool
    is_fk: bool
    ref_entity: str | None
