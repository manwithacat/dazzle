"""Tests for template compiler source= option wiring and route collision."""

from dazzle.core import ir
from dazzle.core.ir import FieldTypeKind, SurfaceMode
from dazzle.core.ir.fields import FieldModifier
from dazzle_ui.converters.template_compiler import (
    _build_entity_columns,
    _build_form_fields,
    compile_appspec_to_templates,
    compile_surface_to_context,
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


# =============================================================================
# Related entity tabs (hub-and-spoke pattern, #301)
# =============================================================================


def _company_entity() -> ir.EntitySpec:
    """Hub entity for testing related tabs."""
    return ir.EntitySpec(
        name="Company",
        title="Company",
        fields=[
            ir.FieldSpec(
                name="id",
                type=ir.FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
            ir.FieldSpec(
                name="name",
                type=ir.FieldType(kind=FieldTypeKind.STR, max_length=200),
                is_required=True,
            ),
            ir.FieldSpec(
                name="status",
                type=ir.FieldType(kind=FieldTypeKind.ENUM, enum_values=["active", "inactive"]),
            ),
        ],
    )


def _contact_entity() -> ir.EntitySpec:
    """Related entity with FK to Company."""
    return ir.EntitySpec(
        name="Contact",
        title="Contact",
        fields=[
            ir.FieldSpec(
                name="id",
                type=ir.FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
            ir.FieldSpec(
                name="full_name",
                type=ir.FieldType(kind=FieldTypeKind.STR, max_length=200),
                is_required=True,
            ),
            ir.FieldSpec(
                name="email",
                type=ir.FieldType(kind=FieldTypeKind.EMAIL),
            ),
            ir.FieldSpec(
                name="company",
                type=ir.FieldType(kind=FieldTypeKind.REF, ref_entity="Company"),
            ),
        ],
    )


def _task_entity() -> ir.EntitySpec:
    """Another related entity with FK to Company."""
    return ir.EntitySpec(
        name="Task",
        title="Task",
        fields=[
            ir.FieldSpec(
                name="id",
                type=ir.FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
            ir.FieldSpec(
                name="title",
                type=ir.FieldType(kind=FieldTypeKind.STR, max_length=200),
                is_required=True,
            ),
            ir.FieldSpec(
                name="completed",
                type=ir.FieldType(kind=FieldTypeKind.BOOL),
            ),
            ir.FieldSpec(
                name="company",
                type=ir.FieldType(kind=FieldTypeKind.REF, ref_entity="Company"),
            ),
        ],
    )


class TestRelatedEntityTabs:
    """Tests for related entity tab generation on detail (VIEW) pages."""

    def _make_hub_appspec(self) -> ir.AppSpec:
        """Build an AppSpec with Company (hub) + Contact, Task (spokes)."""
        company = _company_entity()
        contact = _contact_entity()
        task = _task_entity()
        return ir.AppSpec(
            name="test_app",
            title="Test App",
            version="0.1.0",
            domain=ir.DomainSpec(entities=[company, contact, task]),
            surfaces=[
                ir.SurfaceSpec(
                    name="company_list",
                    title="Companies",
                    entity_ref="Company",
                    mode=SurfaceMode.LIST,
                    actions=[],
                ),
                ir.SurfaceSpec(
                    name="company_detail",
                    title="Company Detail",
                    entity_ref="Company",
                    mode=SurfaceMode.VIEW,
                    actions=[],
                ),
                ir.SurfaceSpec(
                    name="contact_list",
                    title="Contacts",
                    entity_ref="Contact",
                    mode=SurfaceMode.LIST,
                    actions=[],
                ),
                ir.SurfaceSpec(
                    name="task_list",
                    title="Tasks",
                    entity_ref="Task",
                    mode=SurfaceMode.LIST,
                    actions=[],
                ),
            ],
        )

    def test_view_surface_has_related_tabs(self):
        """VIEW surface for hub entity gets related tabs from reverse refs."""
        appspec = self._make_hub_appspec()
        contexts = compile_appspec_to_templates(appspec)

        detail_ctx = contexts.get("/company/{id}")
        assert detail_ctx is not None
        assert detail_ctx.detail is not None
        assert len(detail_ctx.detail.related_tabs) == 2

    def test_related_tab_labels(self):
        """Related tabs use the referenced entity's title."""
        appspec = self._make_hub_appspec()
        contexts = compile_appspec_to_templates(appspec)
        tabs = contexts["/company/{id}"].detail.related_tabs
        labels = {t.label for t in tabs}
        assert "Contact" in labels
        assert "Task" in labels

    def test_related_tab_filter_field(self):
        """Each tab stores the FK field name for filtering."""
        appspec = self._make_hub_appspec()
        contexts = compile_appspec_to_templates(appspec)
        tabs = contexts["/company/{id}"].detail.related_tabs
        for tab in tabs:
            assert tab.filter_field == "company"

    def test_related_tab_api_endpoint(self):
        """Each tab has the correct API endpoint for its entity."""
        appspec = self._make_hub_appspec()
        contexts = compile_appspec_to_templates(appspec)
        tabs = contexts["/company/{id}"].detail.related_tabs
        endpoints = {t.entity_name: t.api_endpoint for t in tabs}
        assert endpoints["Contact"] == "/contacts"
        assert endpoints["Task"] == "/tasks"

    def test_related_tab_columns_exclude_fk(self):
        """Related tab columns exclude the FK field (company) and PK."""
        appspec = self._make_hub_appspec()
        contexts = compile_appspec_to_templates(appspec)
        tabs = contexts["/company/{id}"].detail.related_tabs
        contact_tab = next(t for t in tabs if t.entity_name == "Contact")
        col_keys = [c.key for c in contact_tab.columns]
        assert "company" not in col_keys
        assert "id" not in col_keys
        assert "full_name" in col_keys
        assert "email" in col_keys

    def test_related_tab_create_url(self):
        """Related tabs have a create URL."""
        appspec = self._make_hub_appspec()
        contexts = compile_appspec_to_templates(appspec)
        tabs = contexts["/company/{id}"].detail.related_tabs
        contact_tab = next(t for t in tabs if t.entity_name == "Contact")
        assert contact_tab.create_url == "/contact/create"

    def test_related_tab_detail_url(self):
        """Related tabs have a detail URL template."""
        appspec = self._make_hub_appspec()
        contexts = compile_appspec_to_templates(appspec)
        tabs = contexts["/company/{id}"].detail.related_tabs
        contact_tab = next(t for t in tabs if t.entity_name == "Contact")
        assert contact_tab.detail_url_template == "/contact/{id}"

    def test_list_surface_has_no_related_tabs(self):
        """LIST surfaces should not have related tabs."""
        appspec = self._make_hub_appspec()
        contexts = compile_appspec_to_templates(appspec)
        list_ctx = contexts.get("/company")
        assert list_ctx is not None
        assert list_ctx.detail is None  # LIST surface has no detail

    def test_entity_without_reverse_refs_has_no_tabs(self):
        """A VIEW surface for an entity with no reverse refs gets no tabs."""
        entity = _contact_entity()
        appspec = ir.AppSpec(
            name="test_app",
            domain=ir.DomainSpec(entities=[entity]),
            surfaces=[
                ir.SurfaceSpec(
                    name="contact_detail",
                    title="Contact Detail",
                    entity_ref="Contact",
                    mode=SurfaceMode.VIEW,
                    actions=[],
                ),
            ],
        )
        contexts = compile_appspec_to_templates(appspec)
        detail_ctx = contexts["/contact/{id}"]
        assert detail_ctx.detail is not None
        assert len(detail_ctx.detail.related_tabs) == 0

    def test_compile_surface_to_context_with_reverse_refs(self):
        """compile_surface_to_context passes reverse_refs to view surfaces."""
        company = _company_entity()
        contact = _contact_entity()
        surface = ir.SurfaceSpec(
            name="company_detail",
            title="Company Detail",
            entity_ref="Company",
            mode=SurfaceMode.VIEW,
            actions=[],
        )
        ctx = compile_surface_to_context(
            surface,
            company,
            reverse_refs=[("Contact", "company", contact)],
        )
        assert ctx.detail is not None
        assert len(ctx.detail.related_tabs) == 1
        assert ctx.detail.related_tabs[0].entity_name == "Contact"


class TestBuildEntityColumns:
    """Tests for _build_entity_columns helper."""

    def test_excludes_pk(self):
        """PK fields are excluded from entity columns."""
        entity = _company_entity()
        cols = _build_entity_columns(entity)
        assert all(c.key != "id" for c in cols)

    def test_includes_regular_fields(self):
        """Regular fields are included."""
        entity = _company_entity()
        cols = _build_entity_columns(entity)
        keys = [c.key for c in cols]
        assert "name" in keys
        assert "status" in keys

    def test_enum_field_is_badge_type(self):
        """Enum fields map to badge column type."""
        entity = _company_entity()
        cols = _build_entity_columns(entity)
        status_col = next(c for c in cols if c.key == "status")
        assert status_col.type == "badge"

    def test_bool_field_type(self):
        """Bool fields map to bool column type."""
        task = _task_entity()
        cols = _build_entity_columns(task)
        completed_col = next(c for c in cols if c.key == "completed")
        assert completed_col.type == "bool"

    def test_ref_field_maps_to_ref_type(self):
        """Ref (FK) fields map to ref column type, not text (#308)."""
        contact = _contact_entity()
        cols = _build_entity_columns(contact)
        company_col = next(c for c in cols if c.key == "company")
        assert company_col.type == "ref"
