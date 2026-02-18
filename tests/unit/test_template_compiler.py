"""Tests for template compiler source= option wiring and route collision."""

from dazzle.core import ir
from dazzle.core.ir import FieldTypeKind, SurfaceMode
from dazzle.core.ir.fields import FieldModifier
from dazzle_ui.converters.template_compiler import (
    _build_form_fields,
    compile_appspec_to_templates,
)


def _sole_trader_entity() -> ir.EntitySpec:
    """Entity with 5 non-PK fields (owner is NOT an entity field)."""
    return ir.EntitySpec(
        name="SoleTrader",
        title="Sole Trader",
        fields=[
            ir.FieldSpec(
                name="id",
                type=ir.FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
            ir.FieldSpec(
                name="trading_name",
                type=ir.FieldType(kind=FieldTypeKind.STR, max_length=200),
                is_required=True,
            ),
            ir.FieldSpec(
                name="nino",
                type=ir.FieldType(kind=FieldTypeKind.STR, max_length=9),
            ),
            ir.FieldSpec(
                name="utr",
                type=ir.FieldType(kind=FieldTypeKind.STR, max_length=10),
            ),
            ir.FieldSpec(
                name="is_vat_registered",
                type=ir.FieldType(kind=FieldTypeKind.BOOL),
            ),
            ir.FieldSpec(
                name="vat_number",
                type=ir.FieldType(kind=FieldTypeKind.STR, max_length=12),
            ),
        ],
    )


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
                    modifiers=[FieldModifier.PK],
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


class TestFormFieldSectionOverEntityFallback:
    """When a surface defines sections, _build_form_fields must use section
    fields — NOT fall back to entity fields."""

    def test_surface_with_sections_uses_section_fields(self):
        """Surface with sections produces only the section-defined fields."""
        entity = _sole_trader_entity()
        surface = ir.SurfaceSpec(
            name="sole_trader_create",
            title="Add Sole Trader",
            entity_ref="SoleTrader",
            mode=SurfaceMode.CREATE,
            sections=[
                ir.SurfaceSection(
                    name="main",
                    title="New Sole Trader",
                    elements=[
                        ir.SurfaceElement(field_name="owner", label="Owner"),
                        ir.SurfaceElement(field_name="trading_name", label="Trading Name"),
                        ir.SurfaceElement(field_name="utr", label="UTR"),
                    ],
                )
            ],
            actions=[],
        )

        fields = _build_form_fields(surface, entity)

        assert len(fields) == 3
        assert [f.name for f in fields] == ["owner", "trading_name", "utr"]
        assert [f.label for f in fields] == ["Owner", "Trading Name", "UTR"]

    def test_surface_without_sections_falls_back_to_entity_fields(self):
        """Surface without sections produces all non-PK entity fields."""
        entity = _sole_trader_entity()
        surface = ir.SurfaceSpec(
            name="sole_trader_create",
            title="Add Sole Trader",
            entity_ref="SoleTrader",
            mode=SurfaceMode.CREATE,
            sections=[],
            actions=[],
        )

        fields = _build_form_fields(surface, entity)

        assert len(fields) == 5
        assert {f.name for f in fields} == {
            "trading_name",
            "nino",
            "utr",
            "is_vat_registered",
            "vat_number",
        }


class TestRouteCollisionPrefersSectioned:
    """When two surfaces for the same entity+mode produce the same route,
    compile_appspec_to_templates must prefer the surface with sections."""

    def test_sectioned_surface_wins_over_sectionless(self):
        """Surface with explicit sections wins when a sectionless surface
        maps to the same route (same entity + mode)."""
        entity = _sole_trader_entity()

        # Surface WITH sections — user-defined field subset
        surface_with = ir.SurfaceSpec(
            name="sole_trader_create",
            title="Add Sole Trader",
            entity_ref="SoleTrader",
            mode=SurfaceMode.CREATE,
            sections=[
                ir.SurfaceSection(
                    name="main",
                    title="New Sole Trader",
                    elements=[
                        ir.SurfaceElement(field_name="owner", label="Owner"),
                        ir.SurfaceElement(field_name="trading_name", label="Trading Name"),
                        ir.SurfaceElement(field_name="utr", label="UTR"),
                    ],
                )
            ],
            actions=[],
        )

        # Surface WITHOUT sections — same entity + mode, different name
        surface_without = ir.SurfaceSpec(
            name="add_sole_trader",
            title="New Sole Trader",
            entity_ref="SoleTrader",
            mode=SurfaceMode.CREATE,
            sections=[],
            actions=[],
        )

        # Order: sectionless first, then sectioned — sectioned must still win
        appspec = ir.AppSpec(
            name="test_app",
            title="Test App",
            version="0.1.0",
            domain=ir.DomainSpec(entities=[entity]),
            surfaces=[surface_without, surface_with],
        )

        contexts = compile_appspec_to_templates(appspec)

        route = "/soletrader/create"
        assert route in contexts
        ctx = contexts[route]
        assert ctx.form is not None
        # Must have 3 section-defined fields, not 5 entity-fallback fields
        assert len(ctx.form.fields) == 3
        assert [f.name for f in ctx.form.fields] == ["owner", "trading_name", "utr"]

    def test_sectioned_surface_wins_regardless_of_order(self):
        """Surface with sections wins even when it appears first in the list
        (a sectionless surface must not overwrite it)."""
        entity = _sole_trader_entity()

        surface_with = ir.SurfaceSpec(
            name="sole_trader_create",
            title="Add Sole Trader",
            entity_ref="SoleTrader",
            mode=SurfaceMode.CREATE,
            sections=[
                ir.SurfaceSection(
                    name="main",
                    title="New Sole Trader",
                    elements=[
                        ir.SurfaceElement(field_name="trading_name", label="Trading Name"),
                        ir.SurfaceElement(field_name="utr", label="UTR"),
                    ],
                )
            ],
            actions=[],
        )

        surface_without = ir.SurfaceSpec(
            name="add_sole_trader",
            title="New Sole Trader",
            entity_ref="SoleTrader",
            mode=SurfaceMode.CREATE,
            sections=[],
            actions=[],
        )

        # Order: sectioned first, then sectionless — sectioned must still win
        appspec = ir.AppSpec(
            name="test_app",
            title="Test App",
            version="0.1.0",
            domain=ir.DomainSpec(entities=[entity]),
            surfaces=[surface_with, surface_without],
        )

        contexts = compile_appspec_to_templates(appspec)

        route = "/soletrader/create"
        assert route in contexts
        ctx = contexts[route]
        assert ctx.form is not None
        assert len(ctx.form.fields) == 2
        assert [f.name for f in ctx.form.fields] == ["trading_name", "utr"]

    def test_no_collision_with_single_surface(self):
        """A single surface with sections compiles correctly."""
        entity = _sole_trader_entity()

        surface = ir.SurfaceSpec(
            name="sole_trader_create",
            title="Add Sole Trader",
            entity_ref="SoleTrader",
            mode=SurfaceMode.CREATE,
            sections=[
                ir.SurfaceSection(
                    name="main",
                    title="New Sole Trader",
                    elements=[
                        ir.SurfaceElement(field_name="owner", label="Owner"),
                        ir.SurfaceElement(field_name="trading_name", label="Trading Name"),
                        ir.SurfaceElement(field_name="utr", label="UTR"),
                    ],
                )
            ],
            actions=[],
        )

        appspec = ir.AppSpec(
            name="test_app",
            title="Test App",
            version="0.1.0",
            domain=ir.DomainSpec(entities=[entity]),
            surfaces=[surface],
        )

        contexts = compile_appspec_to_templates(appspec)

        route = "/soletrader/create"
        assert route in contexts
        ctx = contexts[route]
        assert ctx.form is not None
        assert len(ctx.form.fields) == 3
        assert [f.name for f in ctx.form.fields] == ["owner", "trading_name", "utr"]
