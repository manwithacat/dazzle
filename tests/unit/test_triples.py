"""
Tests for src/dazzle/core/ir/triples.py

Covers:
- WidgetKind enum values
- resolve_widget() mapping from FieldTypeKind to WidgetKind
- _id suffix convention: uuid field ending in _id → SEARCH_SELECT, plain 'id' → TEXT_INPUT
- has_source=True override → SEARCH_SELECT
- SurfaceFieldTriple construction (basic field and FK field)
"""

import pytest
from pydantic import ValidationError

from dazzle.core.ir.fields import FieldModifier, FieldSpec, FieldType, FieldTypeKind
from dazzle.core.ir.triples import SurfaceFieldTriple, WidgetKind, resolve_widget


def _make_field(
    name: str,
    kind: FieldTypeKind,
    *,
    modifiers: list[FieldModifier] | None = None,
    ref_entity: str | None = None,
    enum_values: list[str] | None = None,
) -> FieldSpec:
    """Helper: build a minimal FieldSpec."""
    return FieldSpec(
        name=name,
        type=FieldType(
            kind=kind,
            ref_entity=ref_entity,
            enum_values=enum_values,
        ),
        modifiers=modifiers or [],
    )


# ---------------------------------------------------------------------------
# WidgetKind values
# ---------------------------------------------------------------------------


class TestWidgetKindValues:
    def test_all_expected_values_present(self) -> None:
        expected = {
            "TEXT_INPUT",
            "TEXTAREA",
            "CHECKBOX",
            "DATE_PICKER",
            "DATETIME_PICKER",
            "NUMBER_INPUT",
            "EMAIL_INPUT",
            "ENUM_SELECT",
            "SEARCH_SELECT",
            "MONEY_INPUT",
            "FILE_UPLOAD",
        }
        actual = {member.name for member in WidgetKind}
        assert actual == expected

    def test_widget_kind_is_str(self) -> None:
        # WidgetKind inherits from StrEnum
        assert isinstance(WidgetKind.TEXT_INPUT, str)


# ---------------------------------------------------------------------------
# resolve_widget: basic type mappings
# ---------------------------------------------------------------------------


class TestResolveWidgetTypeMap:
    @pytest.mark.parametrize(
        "kind, expected_widget",
        [
            (FieldTypeKind.STR, WidgetKind.TEXT_INPUT),
            (FieldTypeKind.TEXT, WidgetKind.TEXTAREA),
            (FieldTypeKind.INT, WidgetKind.NUMBER_INPUT),
            (FieldTypeKind.DECIMAL, WidgetKind.NUMBER_INPUT),
            (FieldTypeKind.FLOAT, WidgetKind.NUMBER_INPUT),
            (FieldTypeKind.BOOL, WidgetKind.CHECKBOX),
            (FieldTypeKind.DATE, WidgetKind.DATE_PICKER),
            (FieldTypeKind.DATETIME, WidgetKind.DATETIME_PICKER),
            (FieldTypeKind.UUID, WidgetKind.TEXT_INPUT),
            (FieldTypeKind.ENUM, WidgetKind.ENUM_SELECT),
            (FieldTypeKind.REF, WidgetKind.SEARCH_SELECT),
            (FieldTypeKind.EMAIL, WidgetKind.EMAIL_INPUT),
            (FieldTypeKind.JSON, WidgetKind.TEXTAREA),
            (FieldTypeKind.MONEY, WidgetKind.MONEY_INPUT),
            (FieldTypeKind.FILE, WidgetKind.FILE_UPLOAD),
            (FieldTypeKind.URL, WidgetKind.TEXT_INPUT),
            (FieldTypeKind.TIMEZONE, WidgetKind.TEXT_INPUT),
            (FieldTypeKind.HAS_MANY, WidgetKind.SEARCH_SELECT),
            (FieldTypeKind.HAS_ONE, WidgetKind.SEARCH_SELECT),
            (FieldTypeKind.EMBEDS, WidgetKind.SEARCH_SELECT),
            (FieldTypeKind.BELONGS_TO, WidgetKind.SEARCH_SELECT),
        ],
    )
    def test_type_to_widget(self, kind: FieldTypeKind, expected_widget: WidgetKind) -> None:
        field = _make_field("some_field", kind)
        assert resolve_widget(field) == expected_widget


# ---------------------------------------------------------------------------
# resolve_widget: _id suffix convention
# ---------------------------------------------------------------------------


class TestResolveWidgetIdSuffix:
    def test_uuid_field_named_id_gives_text_input(self) -> None:
        """Plain 'id' primary-key field should stay TEXT_INPUT, not SEARCH_SELECT."""
        field = _make_field("id", FieldTypeKind.UUID, modifiers=[FieldModifier.PK])
        assert resolve_widget(field) == WidgetKind.TEXT_INPUT

    def test_uuid_field_ending_in_underscore_id_gives_search_select(self) -> None:
        """A uuid FK column like 'client_id' signals a foreign key → SEARCH_SELECT."""
        field = _make_field("client_id", FieldTypeKind.UUID)
        assert resolve_widget(field) == WidgetKind.SEARCH_SELECT

    def test_uuid_field_ending_in_underscore_id_longer_name(self) -> None:
        field = _make_field("assessment_event_id", FieldTypeKind.UUID)
        assert resolve_widget(field) == WidgetKind.SEARCH_SELECT

    def test_str_field_ending_in_id_not_affected(self) -> None:
        """The _id suffix rule only applies to UUID fields."""
        field = _make_field("some_id", FieldTypeKind.STR)
        assert resolve_widget(field) == WidgetKind.TEXT_INPUT

    def test_uuid_field_not_ending_in_underscore_id_gives_text_input(self) -> None:
        """A uuid field whose name doesn't end in _id stays TEXT_INPUT."""
        field = _make_field("record_uuid", FieldTypeKind.UUID)
        assert resolve_widget(field) == WidgetKind.TEXT_INPUT


# ---------------------------------------------------------------------------
# resolve_widget: has_source override
# ---------------------------------------------------------------------------


class TestResolveWidgetHasSource:
    def test_has_source_overrides_str_to_search_select(self) -> None:
        field = _make_field("owner", FieldTypeKind.STR)
        assert resolve_widget(field, has_source=True) == WidgetKind.SEARCH_SELECT

    def test_has_source_overrides_uuid_id_to_search_select(self) -> None:
        """Even 'id' gets SEARCH_SELECT when has_source=True."""
        field = _make_field("id", FieldTypeKind.UUID, modifiers=[FieldModifier.PK])
        assert resolve_widget(field, has_source=True) == WidgetKind.SEARCH_SELECT

    def test_has_source_false_leaves_default(self) -> None:
        field = _make_field("notes", FieldTypeKind.TEXT)
        assert resolve_widget(field, has_source=False) == WidgetKind.TEXTAREA


# ---------------------------------------------------------------------------
# SurfaceFieldTriple construction
# ---------------------------------------------------------------------------


class TestSurfaceFieldTriple:
    def test_basic_str_field(self) -> None:
        field = _make_field("title", FieldTypeKind.STR, modifiers=[FieldModifier.REQUIRED])
        triple = SurfaceFieldTriple(
            field_name=field.name,
            widget=resolve_widget(field),
            is_required=field.is_required,
            is_fk=False,
            ref_entity=None,
        )
        assert triple.field_name == "title"
        assert triple.widget == WidgetKind.TEXT_INPUT
        assert triple.is_required is True
        assert triple.is_fk is False
        assert triple.ref_entity is None

    def test_fk_ref_field(self) -> None:
        field = _make_field(
            "client",
            FieldTypeKind.REF,
            ref_entity="Client",
            modifiers=[FieldModifier.REQUIRED],
        )
        triple = SurfaceFieldTriple(
            field_name=field.name,
            widget=resolve_widget(field),
            is_required=field.is_required,
            is_fk=True,
            ref_entity=field.type.ref_entity,
        )
        assert triple.field_name == "client"
        assert triple.widget == WidgetKind.SEARCH_SELECT
        assert triple.is_fk is True
        assert triple.ref_entity == "Client"

    def test_uuid_fk_id_field(self) -> None:
        field = _make_field("client_id", FieldTypeKind.UUID)
        triple = SurfaceFieldTriple(
            field_name=field.name,
            widget=resolve_widget(field),
            is_required=field.is_required,
            is_fk=True,
            ref_entity="Client",
        )
        assert triple.widget == WidgetKind.SEARCH_SELECT
        assert triple.is_fk is True

    def test_triple_is_frozen(self) -> None:
        field = _make_field("name", FieldTypeKind.STR)
        triple = SurfaceFieldTriple(
            field_name=field.name,
            widget=resolve_widget(field),
            is_required=False,
            is_fk=False,
            ref_entity=None,
        )
        with pytest.raises(ValidationError):
            triple.field_name = "other"  # type: ignore[misc]

    def test_optional_field(self) -> None:
        field = _make_field("notes", FieldTypeKind.TEXT)
        triple = SurfaceFieldTriple(
            field_name=field.name,
            widget=resolve_widget(field),
            is_required=field.is_required,
            is_fk=False,
            ref_entity=None,
        )
        assert triple.is_required is False
        assert triple.widget == WidgetKind.TEXTAREA
