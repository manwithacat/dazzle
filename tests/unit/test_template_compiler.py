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
        assert len(detail_ctx.detail.related_groups) == 1
        assert len(detail_ctx.detail.related_groups[0].tabs) == 2

    def test_related_tab_labels(self):
        """Related tabs use the referenced entity's title."""
        appspec = self._make_hub_appspec()
        contexts = compile_appspec_to_templates(appspec)
        tabs = contexts["/company/{id}"].detail.related_groups[0].tabs
        labels = {t.label for t in tabs}
        assert "Contact" in labels
        assert "Task" in labels

    def test_related_tab_filter_field(self):
        """Each tab stores the FK field name for filtering."""
        appspec = self._make_hub_appspec()
        contexts = compile_appspec_to_templates(appspec)
        tabs = contexts["/company/{id}"].detail.related_groups[0].tabs
        for tab in tabs:
            assert tab.filter_field == "company"

    def test_related_tab_api_endpoint(self):
        """Each tab has the correct API endpoint for its entity."""
        appspec = self._make_hub_appspec()
        contexts = compile_appspec_to_templates(appspec)
        tabs = contexts["/company/{id}"].detail.related_groups[0].tabs
        endpoints = {t.entity_name: t.api_endpoint for t in tabs}
        assert endpoints["Contact"] == "/contacts"
        assert endpoints["Task"] == "/tasks"

    def test_related_tab_columns_exclude_fk(self):
        """Related tab columns exclude the FK field (company) and PK."""
        appspec = self._make_hub_appspec()
        contexts = compile_appspec_to_templates(appspec)
        tabs = contexts["/company/{id}"].detail.related_groups[0].tabs
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
        tabs = contexts["/company/{id}"].detail.related_groups[0].tabs
        contact_tab = next(t for t in tabs if t.entity_name == "Contact")
        assert contact_tab.create_url == "/contact/create"

    def test_related_tab_detail_url(self):
        """Related tabs have a detail URL template."""
        appspec = self._make_hub_appspec()
        contexts = compile_appspec_to_templates(appspec)
        tabs = contexts["/company/{id}"].detail.related_groups[0].tabs
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
        assert len(detail_ctx.detail.related_groups) == 0

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
        assert len(ctx.detail.related_groups) == 1
        assert len(ctx.detail.related_groups[0].tabs) == 1
        assert ctx.detail.related_groups[0].tabs[0].entity_name == "Contact"


def _audit_log_entity() -> ir.EntitySpec:
    """Entity with polymorphic FK (entity_type enum + entity_id uuid)."""
    return ir.EntitySpec(
        name="AuditLog",
        title="Audit Log",
        fields=[
            ir.FieldSpec(
                name="id",
                type=ir.FieldType(kind=FieldTypeKind.UUID),
                modifiers=[FieldModifier.PK],
            ),
            ir.FieldSpec(
                name="entity_type",
                type=ir.FieldType(
                    kind=FieldTypeKind.ENUM,
                    enum_values=["company", "sole_trader"],
                ),
            ),
            ir.FieldSpec(
                name="entity_id",
                type=ir.FieldType(kind=FieldTypeKind.UUID),
            ),
            ir.FieldSpec(
                name="action",
                type=ir.FieldType(kind=FieldTypeKind.STR, max_length=100),
            ),
        ],
    )


class TestPolymorphicFKTabs:
    """Tests for polymorphic FK detection and related tab generation (#321)."""

    def _make_poly_appspec(self) -> ir.AppSpec:
        """Build AppSpec with Company, SoleTrader, and AuditLog (polymorphic FK)."""
        company = _company_entity()
        sole_trader = _sole_trader_entity()
        audit = _audit_log_entity()
        return ir.AppSpec(
            name="test_app",
            title="Test App",
            version="0.1.0",
            domain=ir.DomainSpec(entities=[company, sole_trader, audit]),
            surfaces=[
                ir.SurfaceSpec(
                    name="company_detail",
                    title="Company Detail",
                    entity_ref="Company",
                    mode=SurfaceMode.VIEW,
                    actions=[],
                ),
                ir.SurfaceSpec(
                    name="sole_trader_detail",
                    title="Sole Trader Detail",
                    entity_ref="SoleTrader",
                    mode=SurfaceMode.VIEW,
                    actions=[],
                ),
                ir.SurfaceSpec(
                    name="audit_list",
                    title="Audit Logs",
                    entity_ref="AuditLog",
                    mode=SurfaceMode.LIST,
                    actions=[],
                ),
            ],
        )

    def test_company_gets_audit_tab_from_polymorphic_fk(self):
        """Company detail page gets AuditLog tab via polymorphic FK."""
        appspec = self._make_poly_appspec()
        contexts = compile_appspec_to_templates(appspec)
        detail_ctx = contexts.get("/company/{id}")
        assert detail_ctx is not None
        assert detail_ctx.detail is not None
        tabs = detail_ctx.detail.related_groups[0].tabs
        audit_tabs = [t for t in tabs if t.entity_name == "AuditLog"]
        assert len(audit_tabs) == 1

    def test_sole_trader_gets_audit_tab_from_polymorphic_fk(self):
        """SoleTrader detail page gets AuditLog tab via polymorphic FK."""
        appspec = self._make_poly_appspec()
        contexts = compile_appspec_to_templates(appspec)
        detail_ctx = contexts.get("/soletrader/{id}")
        assert detail_ctx is not None
        assert detail_ctx.detail is not None
        tabs = detail_ctx.detail.related_groups[0].tabs
        audit_tabs = [t for t in tabs if t.entity_name == "AuditLog"]
        assert len(audit_tabs) == 1

    def test_polymorphic_tab_has_type_filter(self):
        """Polymorphic tab stores the type discriminator field and value."""
        appspec = self._make_poly_appspec()
        contexts = compile_appspec_to_templates(appspec)
        tabs = contexts["/company/{id}"].detail.related_groups[0].tabs
        audit_tab = next(t for t in tabs if t.entity_name == "AuditLog")
        assert audit_tab.filter_type_field == "entity_type"
        assert audit_tab.filter_type_value == "company"
        assert audit_tab.filter_field == "entity_id"

    def test_polymorphic_tab_type_value_matches_target(self):
        """Each target entity gets the correct type discriminator value."""
        appspec = self._make_poly_appspec()
        contexts = compile_appspec_to_templates(appspec)
        # SoleTrader should get type_value="sole_trader"
        tabs = contexts["/soletrader/{id}"].detail.related_groups[0].tabs
        audit_tab = next(t for t in tabs if t.entity_name == "AuditLog")
        assert audit_tab.filter_type_value == "sole_trader"

    def test_polymorphic_tab_columns_exclude_type_and_id(self):
        """Polymorphic tab columns exclude both entity_type and entity_id."""
        appspec = self._make_poly_appspec()
        contexts = compile_appspec_to_templates(appspec)
        tabs = contexts["/company/{id}"].detail.related_groups[0].tabs
        audit_tab = next(t for t in tabs if t.entity_name == "AuditLog")
        col_keys = [c.key for c in audit_tab.columns]
        assert "entity_type" not in col_keys
        assert "entity_id" not in col_keys
        assert "action" in col_keys

    def test_polymorphic_tab_api_endpoint(self):
        """Polymorphic tab uses the correct API endpoint."""
        appspec = self._make_poly_appspec()
        contexts = compile_appspec_to_templates(appspec)
        tabs = contexts["/company/{id}"].detail.related_groups[0].tabs
        audit_tab = next(t for t in tabs if t.entity_name == "AuditLog")
        assert audit_tab.api_endpoint == "/auditlogs"

    def test_non_enum_type_field_not_detected(self):
        """entity_type as str (not enum) should NOT trigger polymorphic detection."""
        entity = ir.EntitySpec(
            name="Note",
            title="Note",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=FieldTypeKind.UUID),
                    modifiers=[FieldModifier.PK],
                ),
                ir.FieldSpec(
                    name="entity_type",
                    type=ir.FieldType(kind=FieldTypeKind.STR, max_length=100),
                ),
                ir.FieldSpec(
                    name="entity_id",
                    type=ir.FieldType(kind=FieldTypeKind.UUID),
                ),
            ],
        )
        company = _company_entity()
        appspec = ir.AppSpec(
            name="test_app",
            domain=ir.DomainSpec(entities=[company, entity]),
            surfaces=[
                ir.SurfaceSpec(
                    name="company_detail",
                    title="Company Detail",
                    entity_ref="Company",
                    mode=SurfaceMode.VIEW,
                    actions=[],
                ),
            ],
        )
        contexts = compile_appspec_to_templates(appspec)
        assert len(contexts["/company/{id}"].detail.related_groups) == 0

    def test_compile_surface_to_context_with_poly_refs(self):
        """compile_surface_to_context passes poly_refs to view surfaces."""
        company = _company_entity()
        audit = _audit_log_entity()
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
            poly_refs=[("AuditLog", "entity_type", "entity_id", "company", audit)],
        )
        assert ctx.detail is not None
        assert len(ctx.detail.related_groups) == 1
        assert len(ctx.detail.related_groups[0].tabs) == 1
        tab = ctx.detail.related_groups[0].tabs[0]
        assert tab.entity_name == "AuditLog"
        assert tab.filter_type_field == "entity_type"
        assert tab.filter_type_value == "company"


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

    def test_ref_field_id_suffix_stripped_for_column_key(self):
        """Ref fields with _id suffix use relation name as column key (#553)."""
        entity = ir.EntitySpec(
            name="Task",
            title="Task",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=FieldTypeKind.UUID),
                    modifiers=[FieldModifier.PK],
                ),
                ir.FieldSpec(
                    name="assigned_to_id",
                    type=ir.FieldType(kind=FieldTypeKind.REF, ref_entity="User"),
                ),
            ],
        )
        cols = _build_entity_columns(entity)
        ref_col = next(c for c in cols if c.type == "ref")
        assert ref_col.key == "assigned_to"
        assert ref_col.label == "Assigned To"

    def test_belongs_to_field_maps_to_ref_type(self):
        """Belongs_to fields also map to ref column type (#553)."""
        entity = ir.EntitySpec(
            name="LineItem",
            title="Line Item",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=FieldTypeKind.UUID),
                    modifiers=[FieldModifier.PK],
                ),
                ir.FieldSpec(
                    name="order_id",
                    type=ir.FieldType(kind=FieldTypeKind.BELONGS_TO, ref_entity="Order"),
                ),
            ],
        )
        cols = _build_entity_columns(entity)
        ref_col = next(c for c in cols if c.type == "ref")
        assert ref_col.key == "order"
        assert ref_col.label == "Order"


class TestEnumFilterLabels:
    """Tests for #584 — enum filter options use human-readable labels."""

    def test_inline_enum_filter_labels_title_cased(self):
        """Inline enum values get snake_case converted to Title Case."""
        from dazzle_ui.converters.template_compiler import _infer_filter_type

        field = ir.FieldSpec(
            name="status",
            type=ir.FieldType(
                kind=FieldTypeKind.ENUM, enum_values=["in_progress", "on_hold", "done"]
            ),
        )
        ftype, opts = _infer_filter_type(field, None, "status")
        assert ftype == "select"
        assert opts[0] == {"value": "in_progress", "label": "In Progress"}
        assert opts[1] == {"value": "on_hold", "label": "On Hold"}
        assert opts[2] == {"value": "done", "label": "Done"}

    def test_named_enum_filter_labels_use_titles(self):
        """Named EnumSpec titles override mechanical title-casing."""
        from dazzle_ui.converters.template_compiler import _infer_filter_type

        enum_spec = ir.EnumSpec(
            name="Priority",
            title="Priority",
            values=[
                ir.EnumValueSpec(name="p1", title="Critical"),
                ir.EnumValueSpec(name="p2", title="High"),
                ir.EnumValueSpec(name="p3", title="Medium"),
            ],
        )
        field = ir.FieldSpec(
            name="priority",
            type=ir.FieldType(kind=FieldTypeKind.ENUM, enum_values=["p1", "p2", "p3"]),
        )
        ftype, opts = _infer_filter_type(field, None, "priority", enums=[enum_spec])
        assert ftype == "select"
        assert opts[0] == {"value": "p1", "label": "Critical"}
        assert opts[1] == {"value": "p2", "label": "High"}
        assert opts[2] == {"value": "p3", "label": "Medium"}

    def test_named_enum_fallback_when_no_title(self):
        """Values without titles in EnumSpec fall back to title-casing."""
        from dazzle_ui.converters.template_compiler import _infer_filter_type

        enum_spec = ir.EnumSpec(
            name="Status",
            values=[
                ir.EnumValueSpec(name="in_progress", title="In Progress"),
                ir.EnumValueSpec(name="done"),  # no title
            ],
        )
        field = ir.FieldSpec(
            name="status",
            type=ir.FieldType(kind=FieldTypeKind.ENUM, enum_values=["in_progress", "done"]),
        )
        ftype, opts = _infer_filter_type(field, None, "status", enums=[enum_spec])
        assert opts[0] == {"value": "in_progress", "label": "In Progress"}
        assert opts[1] == {"value": "done", "label": "Done"}  # fallback


class TestRelatedGroupValidation:
    """Tests for related group validation in the linker."""

    def test_related_group_unknown_entity(self):
        """Related group referencing unknown entity produces validation error."""
        from dazzle.core.linker_impl import SymbolTable, validate_references

        surface = ir.SurfaceSpec(
            name="contact_detail",
            title="Contact Detail",
            entity_ref="Contact",
            mode=ir.SurfaceMode.VIEW,
            related_groups=[
                ir.RelatedGroup(
                    name="compliance",
                    title="Compliance",
                    display=ir.RelatedDisplayMode.STATUS_CARDS,
                    show=["NonExistentEntity"],
                ),
            ],
        )
        contact = _contact_entity()
        symbols = SymbolTable()
        symbols.add_entity(contact, "test")
        symbols.add_surface(surface, "test")
        errors = validate_references(symbols)
        assert any("NonExistentEntity" in e and "unknown entity" in e.lower() for e in errors)

    def test_related_group_no_fk_to_parent(self):
        """Related group entity without FK to surface entity produces error."""
        from dazzle.core.linker_impl import SymbolTable, validate_references

        standalone = ir.EntitySpec(
            name="Standalone",
            title="Standalone",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(name="value", type=ir.FieldType(kind=ir.FieldTypeKind.STR)),
            ],
        )
        contact = _contact_entity()
        surface = ir.SurfaceSpec(
            name="contact_detail",
            title="Contact Detail",
            entity_ref="Contact",
            mode=ir.SurfaceMode.VIEW,
            related_groups=[
                ir.RelatedGroup(
                    name="misc",
                    title="Misc",
                    display=ir.RelatedDisplayMode.TABLE,
                    show=["Standalone"],
                ),
            ],
        )
        symbols = SymbolTable()
        symbols.add_entity(contact, "test")
        symbols.add_entity(standalone, "test")
        symbols.add_surface(surface, "test")
        errors = validate_references(symbols)
        assert any("Standalone" in e and "no fk" in e.lower() for e in errors)

    def test_related_group_duplicate_entity(self):
        """Same entity in two related groups produces validation error."""
        from dazzle.core.linker_impl import SymbolTable, validate_references

        tax_return = ir.EntitySpec(
            name="TaxReturn",
            title="Tax Return",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="contact",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Contact"),
                ),
            ],
        )
        contact = _contact_entity()
        surface = ir.SurfaceSpec(
            name="contact_detail",
            title="Contact Detail",
            entity_ref="Contact",
            mode=ir.SurfaceMode.VIEW,
            related_groups=[
                ir.RelatedGroup(
                    name="a", title="A", display=ir.RelatedDisplayMode.TABLE, show=["TaxReturn"]
                ),
                ir.RelatedGroup(
                    name="b", title="B", display=ir.RelatedDisplayMode.TABLE, show=["TaxReturn"]
                ),
            ],
        )
        symbols = SymbolTable()
        symbols.add_entity(contact, "test")
        symbols.add_entity(tax_return, "test")
        symbols.add_surface(surface, "test")
        errors = validate_references(symbols)
        assert any(
            "TaxReturn" in e and ("duplicate" in e.lower() or "appears in both" in e.lower())
            for e in errors
        )

    def test_related_group_on_non_view_surface(self):
        """Related group on a list surface produces validation error."""
        from dazzle.core.linker_impl import SymbolTable, validate_references

        contact = _contact_entity()
        surface = ir.SurfaceSpec(
            name="contact_list",
            title="Contacts",
            entity_ref="Contact",
            mode=ir.SurfaceMode.LIST,
            related_groups=[
                ir.RelatedGroup(
                    name="a", title="A", display=ir.RelatedDisplayMode.TABLE, show=["TaxReturn"]
                ),
            ],
        )
        symbols = SymbolTable()
        symbols.add_entity(contact, "test")
        symbols.add_surface(surface, "test")
        errors = validate_references(symbols)
        assert any("related" in e.lower() and "view" in e.lower() for e in errors)


class TestTripleRelatedGroups:
    """Tests for related_groups on VerifiableTriple."""

    def test_triple_includes_related_groups(self):
        """VerifiableTriple includes related_groups from surface."""
        from dazzle.core.ir.triples import derive_triples

        contact = _contact_entity()
        tax_return = ir.EntitySpec(
            name="TaxReturn",
            title="Tax Return",
            fields=[
                ir.FieldSpec(name="id", type=ir.FieldType(kind=ir.FieldTypeKind.UUID)),
                ir.FieldSpec(
                    name="contact",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Contact"),
                ),
            ],
        )
        surface = ir.SurfaceSpec(
            name="contact_detail",
            title="Contact Detail",
            entity_ref="Contact",
            mode=ir.SurfaceMode.VIEW,
            sections=[
                ir.SurfaceSection(
                    name="main",
                    elements=[
                        ir.SurfaceElement(field_name="full_name"),
                    ],
                ),
            ],
            related_groups=[
                ir.RelatedGroup(
                    name="compliance",
                    title="Compliance",
                    display=ir.RelatedDisplayMode.STATUS_CARDS,
                    show=["TaxReturn"],
                ),
            ],
        )
        persona = ir.PersonaSpec(id="admin", label="Admin")

        triples = derive_triples([contact, tax_return], [surface], [persona])
        triple = next(t for t in triples if t.surface == "contact_detail")
        assert triple.related_groups == ["compliance"]

    def test_triple_empty_related_groups_when_no_groups(self):
        """VerifiableTriple has empty related_groups when surface has none."""
        from dazzle.core.ir.triples import derive_triples

        contact = _contact_entity()
        surface = ir.SurfaceSpec(
            name="contact_detail",
            title="Contact Detail",
            entity_ref="Contact",
            mode=ir.SurfaceMode.VIEW,
            sections=[
                ir.SurfaceSection(
                    name="main",
                    elements=[
                        ir.SurfaceElement(field_name="full_name"),
                    ],
                ),
            ],
        )
        persona = ir.PersonaSpec(id="admin", label="Admin")

        triples = derive_triples([contact], [surface], [persona])
        triple = next(t for t in triples if t.surface == "contact_detail")
        assert triple.related_groups == []


class TestRelatedGroupContext:
    """Tests for RelatedGroupContext model."""

    def test_related_group_context_model(self):
        """RelatedGroupContext wraps RelatedTabContext with display mode."""
        from dazzle_ui.runtime.template_context import RelatedGroupContext, RelatedTabContext

        tab = RelatedTabContext(
            tab_id="tab-tax-return",
            label="Tax Return",
            entity_name="TaxReturn",
            api_endpoint="/tax-returns",
            filter_field="contact",
            columns=[],
        )
        group = RelatedGroupContext(
            group_id="group-compliance",
            label="Compliance",
            display="status_cards",
            tabs=[tab],
        )
        assert group.display == "status_cards"
        assert len(group.tabs) == 1
        assert group.is_auto is False


class TestRelatedGroupCompiler:
    """Tests for related group compilation."""

    def test_view_surface_with_related_groups(self):
        """VIEW surface with related_groups produces RelatedGroupContext."""
        company = _company_entity()
        contact = _contact_entity()
        task = _task_entity()
        appspec = ir.AppSpec(
            name="test_app",
            title="Test App",
            version="0.1.0",
            domain=ir.DomainSpec(entities=[company, contact, task]),
            surfaces=[
                ir.SurfaceSpec(
                    name="company_detail",
                    title="Company Detail",
                    entity_ref="Company",
                    mode=SurfaceMode.VIEW,
                    related_groups=[
                        ir.RelatedGroup(
                            name="people",
                            title="People",
                            display=ir.RelatedDisplayMode.STATUS_CARDS,
                            show=["Contact"],
                        ),
                    ],
                ),
            ],
        )
        contexts = compile_appspec_to_templates(appspec)
        detail_ctx = contexts["/company/{id}"]
        assert len(detail_ctx.detail.related_groups) == 2
        people_group = detail_ctx.detail.related_groups[0]
        assert people_group.label == "People"
        assert people_group.display == "status_cards"
        assert people_group.is_auto is False
        assert len(people_group.tabs) == 1
        assert people_group.tabs[0].entity_name == "Contact"
        other_group = detail_ctx.detail.related_groups[1]
        assert other_group.display == "table"
        assert other_group.is_auto is True
        assert len(other_group.tabs) == 1
        assert other_group.tabs[0].entity_name == "Task"

    def test_view_surface_without_related_groups_auto_groups(self):
        """VIEW surface without related_groups auto-groups all tabs."""
        company = _company_entity()
        contact = _contact_entity()
        task = _task_entity()
        appspec = ir.AppSpec(
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
        contexts = compile_appspec_to_templates(appspec)
        detail_ctx = contexts["/company/{id}"]
        assert len(detail_ctx.detail.related_groups) == 1
        auto_group = detail_ctx.detail.related_groups[0]
        assert auto_group.is_auto is True
        assert auto_group.display == "table"
        assert len(auto_group.tabs) == 2
