"""
Tests for archetype expander (v0.10.3).

Tests cover:
- Field merging from extended archetypes
- Settings archetype expansion (singleton, admin access)
- Tenant archetype expansion (tenant root flag)
- Tenant FK injection into non-settings entities
"""

from pathlib import Path

from dazzle.core import ir
from dazzle.core.archetype_expander import expand_archetypes
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.linker_impl import SymbolTable, build_symbol_table


def _create_test_module(dsl: str) -> tuple[ir.ModuleIR, SymbolTable]:
    """Helper to parse DSL and create module with symbol table."""
    result = parse_dsl(dsl, Path("test.dsl"))
    module_name, _, _, _, _, fragment = result
    module = ir.ModuleIR(
        name=module_name,
        file=Path("test.dsl"),
        uses=[],
        fragment=fragment,
    )
    symbols = build_symbol_table([module])
    return module, symbols


class TestFieldMerging:
    """Test archetype field merging via extends."""

    def test_single_archetype_extends(self):
        """Entity extends single archetype - fields are merged."""
        dsl = """
module test
app Test "Test"

archetype Timestamped:
    created_at: datetime auto_add
    updated_at: datetime auto_update

entity Task "Task":
    extends: Timestamped
    id: uuid pk
    title: str(200) required
"""
        module, symbols = _create_test_module(dsl)
        expanded = expand_archetypes(list(module.fragment.entities), symbols)

        task = expanded[0]
        field_names = [f.name for f in task.fields]
        assert "created_at" in field_names
        assert "updated_at" in field_names
        assert "id" in field_names
        assert "title" in field_names
        # Archetype fields should come first
        assert field_names.index("created_at") < field_names.index("id")

    def test_multiple_archetype_extends(self):
        """Entity extends multiple archetypes - all fields merged in order."""
        dsl = """
module test
app Test "Test"

archetype Timestamped:
    created_at: datetime auto_add
    updated_at: datetime auto_update

archetype Auditable:
    created_by: str(100)
    updated_by: str(100)

entity Task "Task":
    extends: Timestamped, Auditable
    id: uuid pk
    title: str(200) required
"""
        module, symbols = _create_test_module(dsl)
        expanded = expand_archetypes(list(module.fragment.entities), symbols)

        task = expanded[0]
        field_names = [f.name for f in task.fields]
        # All archetype fields should be present
        assert "created_at" in field_names
        assert "updated_at" in field_names
        assert "created_by" in field_names
        assert "updated_by" in field_names
        # Entity fields should be present
        assert "id" in field_names
        assert "title" in field_names

    def test_entity_field_overrides_archetype(self):
        """Entity field with same name overrides archetype field."""
        dsl = """
module test
app Test "Test"

archetype Timestamped:
    created_at: datetime auto_add

entity Task "Task":
    extends: Timestamped
    id: uuid pk
    created_at: date  # Override with different type
"""
        module, symbols = _create_test_module(dsl)
        expanded = expand_archetypes(list(module.fragment.entities), symbols)

        task = expanded[0]
        # Should only have one created_at field
        created_at_fields = [f for f in task.fields if f.name == "created_at"]
        assert len(created_at_fields) == 1
        # Entity's version takes precedence (date, not datetime)
        assert created_at_fields[0].type.kind == ir.FieldTypeKind.DATE


class TestSettingsArchetype:
    """Test settings semantic archetype expansion."""

    def test_settings_is_singleton(self):
        """Settings entity gets is_singleton=True."""
        dsl = """
module test
app Test "Test"

entity AppSettings "Settings":
    archetype: settings
    id: uuid pk
    timezone: timezone = "UTC"
"""
        module, symbols = _create_test_module(dsl)
        expanded = expand_archetypes(list(module.fragment.entities), symbols)

        settings = expanded[0]
        assert settings.is_singleton is True

    def test_settings_gets_admin_access(self):
        """Settings entity without access gets admin-only access."""
        dsl = """
module test
app Test "Test"

entity AppSettings "Settings":
    archetype: settings
    id: uuid pk
    timezone: timezone = "UTC"
"""
        module, symbols = _create_test_module(dsl)
        expanded = expand_archetypes(list(module.fragment.entities), symbols)

        settings = expanded[0]
        assert settings.access is not None
        # Should have visibility rules requiring admin
        assert len(settings.access.visibility) > 0
        # Should have permission rules for all operations
        assert len(settings.access.permissions) == 3


class TestTenantArchetype:
    """Test tenant semantic archetype expansion."""

    def test_tenant_is_root(self):
        """Tenant entity gets is_tenant_root=True."""
        dsl = """
module test
app Test "Test"

entity Organization "Organization":
    archetype: tenant
    id: uuid pk
    name: str(200) required
"""
        module, symbols = _create_test_module(dsl)
        expanded = expand_archetypes(list(module.fragment.entities), symbols)

        tenant = expanded[0]
        assert tenant.is_tenant_root is True

    def test_tenant_fk_injection(self):
        """Non-settings entities get tenant FK injected."""
        dsl = """
module test
app Test "Test"

entity Organization "Organization":
    archetype: tenant
    id: uuid pk
    name: str(200) required

entity Contact "Contact":
    id: uuid pk
    name: str(200) required
"""
        module, symbols = _create_test_module(dsl)
        expanded = expand_archetypes(list(module.fragment.entities), symbols)

        contact = next(e for e in expanded if e.name == "Contact")
        field_names = [f.name for f in contact.fields]
        # Should have organization FK (lowercase tenant name)
        assert "organization" in field_names

        # Check it's a ref to Organization
        org_field = next(f for f in contact.fields if f.name == "organization")
        assert org_field.type.kind == ir.FieldTypeKind.REF
        assert org_field.type.ref_entity == "Organization"

    def test_tenant_fk_not_injected_into_settings(self):
        """Settings entities don't get tenant FK (system-wide)."""
        dsl = """
module test
app Test "Test"

entity Organization "Organization":
    archetype: tenant
    id: uuid pk
    name: str(200) required

entity SystemSettings "System Settings":
    archetype: settings
    id: uuid pk
    timezone: timezone = "UTC"
"""
        module, symbols = _create_test_module(dsl)
        expanded = expand_archetypes(list(module.fragment.entities), symbols)

        settings = next(e for e in expanded if e.name == "SystemSettings")
        field_names = [f.name for f in settings.fields]
        # Should NOT have organization FK
        assert "organization" not in field_names

    def test_tenant_fk_not_injected_if_exists(self):
        """Entity with existing tenant ref doesn't get duplicate."""
        dsl = """
module test
app Test "Test"

entity Organization "Organization":
    archetype: tenant
    id: uuid pk
    name: str(200) required

entity Contact "Contact":
    id: uuid pk
    org: ref Organization  # Already has tenant ref
    name: str(200) required
"""
        module, symbols = _create_test_module(dsl)
        expanded = expand_archetypes(list(module.fragment.entities), symbols)

        contact = next(e for e in expanded if e.name == "Contact")
        # Count refs to Organization
        org_refs = [
            f
            for f in contact.fields
            if f.type.kind == ir.FieldTypeKind.REF
            and f.type.ref_entity == "Organization"
        ]
        # Should only have one ref (the existing one)
        assert len(org_refs) == 1
        assert org_refs[0].name == "org"


class TestTenantSettingsArchetype:
    """Test tenant_settings semantic archetype expansion."""

    def test_tenant_settings_is_singleton(self):
        """Tenant settings entity gets is_singleton=True."""
        dsl = """
module test
app Test "Test"

entity Organization "Organization":
    archetype: tenant
    id: uuid pk
    name: str(200) required

entity OrgSettings "Organization Settings":
    archetype: tenant_settings
    id: uuid pk
    org: ref Organization
    timezone: timezone
"""
        module, symbols = _create_test_module(dsl)
        expanded = expand_archetypes(list(module.fragment.entities), symbols)

        org_settings = next(e for e in expanded if e.name == "OrgSettings")
        assert org_settings.is_singleton is True


class TestTimezoneFieldType:
    """Test timezone field type parsing."""

    def test_timezone_field_parsed(self):
        """Timezone field type is correctly parsed."""
        dsl = """
module test
app Test "Test"

entity Settings "Settings":
    id: uuid pk
    timezone: timezone = "UTC"
"""
        module, symbols = _create_test_module(dsl)
        settings = module.fragment.entities[0]

        tz_field = next(f for f in settings.fields if f.name == "timezone")
        assert tz_field.type.kind == ir.FieldTypeKind.TIMEZONE
        assert tz_field.default == "UTC"


class TestAutoSurfaceGeneration:
    """Test auto-surface generation for semantic archetypes."""

    def test_settings_surface_generated(self):
        """Settings entity gets auto-generated settings surface."""
        from dazzle.core.archetype_expander import generate_archetype_surfaces

        dsl = """
module test
app Test "Test"

entity AppSettings "Application Settings":
    archetype: settings
    id: uuid pk
    timezone: timezone = "UTC"
    maintenance_mode: bool = false
"""
        module, symbols = _create_test_module(dsl)
        expanded = expand_archetypes(list(module.fragment.entities), symbols)

        surfaces = generate_archetype_surfaces(expanded, [])

        assert len(surfaces) == 1
        surface = surfaces[0]
        assert surface.name == "app_settings_settings"
        assert surface.mode == ir.SurfaceMode.EDIT
        assert surface.entity_ref == "AppSettings"
        assert surface.access is not None
        assert surface.access.require_auth is True
        assert "admin" in surface.access.allow_personas

    def test_tenant_admin_surface_generated(self):
        """Tenant entity gets auto-generated admin surface."""
        from dazzle.core.archetype_expander import generate_archetype_surfaces

        dsl = """
module test
app Test "Test"

entity Organization "Organization":
    archetype: tenant
    id: uuid pk
    name: str(200) required
    slug: str(50) required unique
"""
        module, symbols = _create_test_module(dsl)
        expanded = expand_archetypes(list(module.fragment.entities), symbols)

        surfaces = generate_archetype_surfaces(expanded, [])

        assert len(surfaces) == 1
        surface = surfaces[0]
        assert surface.name == "organization_admin"
        assert surface.mode == ir.SurfaceMode.LIST
        assert surface.entity_ref == "Organization"
        assert surface.access is not None
        assert "admin" in surface.access.allow_personas

    def test_tenant_settings_surface_generated(self):
        """Tenant settings entity gets auto-generated settings surface."""
        from dazzle.core.archetype_expander import generate_archetype_surfaces

        dsl = """
module test
app Test "Test"

entity Organization "Organization":
    archetype: tenant
    id: uuid pk
    name: str(200) required

entity OrgSettings "Organization Settings":
    archetype: tenant_settings
    id: uuid pk
    org: ref Organization
    timezone: timezone
"""
        module, symbols = _create_test_module(dsl)
        expanded = expand_archetypes(list(module.fragment.entities), symbols)

        surfaces = generate_archetype_surfaces(expanded, [])

        # Should have 2 surfaces: one for tenant, one for tenant_settings
        assert len(surfaces) == 2
        surface_names = {s.name for s in surfaces}
        assert "organization_admin" in surface_names
        assert "org_settings_settings" in surface_names

        org_settings_surface = next(s for s in surfaces if s.name == "org_settings_settings")
        assert org_settings_surface.mode == ir.SurfaceMode.EDIT
        assert org_settings_surface.entity_ref == "OrgSettings"

    def test_existing_surface_not_overridden(self):
        """Explicit DSL surface overrides auto-generation."""
        from dazzle.core.archetype_expander import generate_archetype_surfaces

        dsl = """
module test
app Test "Test"

entity AppSettings "Settings":
    archetype: settings
    id: uuid pk
    timezone: timezone = "UTC"
"""
        module, symbols = _create_test_module(dsl)
        expanded = expand_archetypes(list(module.fragment.entities), symbols)

        # Simulate existing surface with same name
        existing_surface = ir.SurfaceSpec(
            name="app_settings_settings",
            title="Custom Settings",
            entity_ref="AppSettings",
            mode=ir.SurfaceMode.EDIT,
            sections=[],
            actions=[],
        )

        surfaces = generate_archetype_surfaces(expanded, [existing_surface])

        # Should not generate new surface since one with same name exists
        assert len(surfaces) == 0

    def test_surface_elements_exclude_pk(self):
        """Surface elements don't include primary key fields."""
        from dazzle.core.archetype_expander import generate_archetype_surfaces

        dsl = """
module test
app Test "Test"

entity AppSettings "Settings":
    archetype: settings
    id: uuid pk
    timezone: timezone = "UTC"
    site_name: str(200) = "My App"
"""
        module, symbols = _create_test_module(dsl)
        expanded = expand_archetypes(list(module.fragment.entities), symbols)

        surfaces = generate_archetype_surfaces(expanded, [])

        assert len(surfaces) == 1
        surface = surfaces[0]
        assert len(surface.sections) == 1

        section = surface.sections[0]
        field_names = [e.field_name for e in section.elements]
        assert "id" not in field_names
        assert "timezone" in field_names
        assert "site_name" in field_names
