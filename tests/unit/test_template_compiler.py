"""Tests for template compiler source= option wiring."""

from dazzle.core import ir
from dazzle.core.ir import FieldTypeKind, SurfaceMode
from dazzle_dnr_ui.converters.template_compiler import _build_form_fields


class TestFormFieldSourceOption:
    """Tests for source= option producing FieldSourceContext."""

    def _make_surface_with_source(self, source_ref: str) -> ir.SurfaceSpec:
        """Helper to build a surface with a source option on one field."""
        return ir.SurfaceSpec(
            name="test_create",
            title="Test",
            entity_ref="Client",
            mode=SurfaceMode.CREATE,
            sections=[
                ir.SurfaceSection(
                    name="main",
                    title="Details",
                    elements=[
                        ir.SurfaceElement(
                            field_name="company_name",
                            label="Company",
                            options={"source": source_ref},
                        ),
                    ],
                )
            ],
            actions=[],
        )

    def _make_entity(self) -> ir.EntitySpec:
        return ir.EntitySpec(
            name="Client",
            title="Client",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=FieldTypeKind.UUID),
                    is_primary_key=True,
                ),
                ir.FieldSpec(
                    name="company_name",
                    type=ir.FieldType(kind=FieldTypeKind.STR, max_length=200),
                    is_required=True,
                ),
            ],
        )

    def test_source_option_produces_field_source_context(self):
        """Test that source= option on a field produces a FieldSourceContext."""
        surface = self._make_surface_with_source("companies_house_lookup.search_companies")
        entity = self._make_entity()

        fields = _build_form_fields(surface, entity)

        assert len(fields) == 1
        field = fields[0]
        assert field.name == "company_name"
        assert field.type == "search_select"
        assert field.source is not None
        assert field.source.endpoint == "/api/_fragments/search"
        assert field.source.display_key == "company_name"
        assert field.source.value_key == "company_number"

    def test_no_source_option_has_no_source_context(self):
        """Test that fields without source= have no FieldSourceContext."""
        surface = ir.SurfaceSpec(
            name="test_create",
            title="Test",
            entity_ref="Client",
            mode=SurfaceMode.CREATE,
            sections=[
                ir.SurfaceSection(
                    name="main",
                    title="Details",
                    elements=[
                        ir.SurfaceElement(field_name="company_name", label="Company"),
                    ],
                )
            ],
            actions=[],
        )
        entity = self._make_entity()

        fields = _build_form_fields(surface, entity)

        assert len(fields) == 1
        assert fields[0].source is None
        assert fields[0].type == "text"
