"""
Unit tests for the semantic validator module.

Tests validation of entities, surfaces, experiences, services, and UX specs
for semantic correctness.
"""

import pytest

from dazzle.core import ir
from dazzle.core.validator import (
    extended_lint,
    validate_entities,
    validate_experiences,
    validate_foreign_models,
    validate_integrations,
    validate_services,
    validate_surfaces,
    validate_ux_specs,
)


# =============================================================================
# Entity Validation Tests
# =============================================================================


class TestValidateEntities:
    """Test entity validation."""

    def test_valid_entity(self) -> None:
        """Test validation of a valid entity."""
        entity = ir.EntitySpec(
            name="Task",
            title="A task item",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                    modifiers=[ir.FieldModifier.PK],
                ),
                ir.FieldSpec(
                    name="title",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                    modifiers=[ir.FieldModifier.REQUIRED],
                ),
            ],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
        )

        errors, warnings = validate_entities(appspec)

        assert len(errors) == 0
        assert len(warnings) == 0

    def test_missing_primary_key(self) -> None:
        """Test detection of missing primary key."""
        entity = ir.EntitySpec(
            name="Task",
            title="A task item",
            fields=[
                ir.FieldSpec(
                    name="title",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                ),
            ],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
        )

        errors, warnings = validate_entities(appspec)

        assert any("no primary key" in e for e in errors)

    def test_duplicate_field_names(self) -> None:
        """Test detection of duplicate field names."""
        entity = ir.EntitySpec(
            name="Task",
            title="A task item",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                    modifiers=[ir.FieldModifier.PK],
                ),
                ir.FieldSpec(
                    name="title",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                ),
                ir.FieldSpec(
                    name="title",  # Duplicate
                    type=ir.FieldType(kind=ir.FieldTypeKind.TEXT),
                ),
            ],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
        )

        errors, warnings = validate_entities(appspec)

        assert any("duplicate field names" in e for e in errors)

    def test_enum_without_values(self) -> None:
        """Test detection of enum without values."""
        entity = ir.EntitySpec(
            name="Task",
            title="A task item",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                    modifiers=[ir.FieldModifier.PK],
                ),
                ir.FieldSpec(
                    name="status",
                    type=ir.FieldType(kind=ir.FieldTypeKind.ENUM, enum_values=[]),
                ),
            ],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
        )

        errors, warnings = validate_entities(appspec)

        assert any("enum type but no values" in e for e in errors)

    def test_decimal_missing_precision(self) -> None:
        """Test detection of decimal without precision/scale."""
        entity = ir.EntitySpec(
            name="Task",
            title="A task item",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                    modifiers=[ir.FieldModifier.PK],
                ),
                ir.FieldSpec(
                    name="amount",
                    type=ir.FieldType(kind=ir.FieldTypeKind.DECIMAL),  # No precision/scale
                ),
            ],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
        )

        errors, warnings = validate_entities(appspec)

        assert any("missing precision/scale" in e for e in errors)

    def test_decimal_scale_greater_than_precision(self) -> None:
        """Test detection of invalid decimal scale > precision."""
        entity = ir.EntitySpec(
            name="Task",
            title="A task item",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                    modifiers=[ir.FieldModifier.PK],
                ),
                ir.FieldSpec(
                    name="amount",
                    type=ir.FieldType(kind=ir.FieldTypeKind.DECIMAL, precision=5, scale=10),
                ),
            ],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
        )

        errors, warnings = validate_entities(appspec)

        assert any("scale" in e and "precision" in e for e in errors)

    def test_string_missing_max_length(self) -> None:
        """Test detection of string without max_length."""
        entity = ir.EntitySpec(
            name="Task",
            title="A task item",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                    modifiers=[ir.FieldModifier.PK],
                ),
                ir.FieldSpec(
                    name="title",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR),  # No max_length
                ),
            ],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
        )

        errors, warnings = validate_entities(appspec)

        assert any("no max_length" in e for e in errors)

    def test_string_very_large_max_length_warning(self) -> None:
        """Test warning for very large string max_length."""
        entity = ir.EntitySpec(
            name="Task",
            title="A task item",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                    modifiers=[ir.FieldModifier.PK],
                ),
                ir.FieldSpec(
                    name="description",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=20000),
                ),
            ],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
        )

        errors, warnings = validate_entities(appspec)

        assert any("text" in w.lower() for w in warnings)

    def test_conflicting_modifiers(self) -> None:
        """Test detection of conflicting required/optional modifiers."""
        entity = ir.EntitySpec(
            name="Task",
            title="A task item",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                    modifiers=[ir.FieldModifier.PK],
                ),
                ir.FieldSpec(
                    name="title",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                    modifiers=[ir.FieldModifier.REQUIRED, ir.FieldModifier.OPTIONAL],
                ),
            ],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
        )

        errors, warnings = validate_entities(appspec)

        assert any("required" in e and "optional" in e for e in errors)

    def test_auto_modifier_on_non_datetime(self) -> None:
        """Test warning for auto_add/auto_update on non-datetime field."""
        entity = ir.EntitySpec(
            name="Task",
            title="A task item",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                    modifiers=[ir.FieldModifier.PK],
                ),
                ir.FieldSpec(
                    name="counter",
                    type=ir.FieldType(kind=ir.FieldTypeKind.INT),
                    modifiers=[ir.FieldModifier.AUTO_ADD],  # Unusual on int
                ),
            ],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
        )

        errors, warnings = validate_entities(appspec)

        assert any("auto_add" in w for w in warnings)

    def test_constraint_references_nonexistent_field(self) -> None:
        """Test detection of constraint referencing non-existent field."""
        entity = ir.EntitySpec(
            name="Task",
            title="A task item",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                    modifiers=[ir.FieldModifier.PK],
                ),
            ],
            constraints=[
                ir.Constraint(
                    kind=ir.ConstraintKind.UNIQUE,
                    fields=["nonexistent_field"],
                ),
            ],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
        )

        errors, warnings = validate_entities(appspec)

        assert any("nonexistent_field" in e for e in errors)


# =============================================================================
# Surface Validation Tests
# =============================================================================


class TestValidateSurfaces:
    """Test surface validation."""

    def test_valid_surface(self) -> None:
        """Test validation of a valid surface."""
        entity = ir.EntitySpec(
            name="Task",
            title="A task item",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                    modifiers=[ir.FieldModifier.PK],
                ),
                ir.FieldSpec(
                    name="title",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                ),
            ],
        )
        surface = ir.SurfaceSpec(
            name="task_list",
            title="Tasks",
            entity_ref="Task",
            mode=ir.SurfaceMode.LIST,
            sections=[
                ir.SurfaceSection(
                    name="main",
                    elements=[
                        ir.SurfaceElement(field_name="title", label="Title"),
                    ],
                ),
            ],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
            surfaces=[surface],
        )

        errors, warnings = validate_surfaces(appspec)

        assert len(errors) == 0

    def test_surface_references_nonexistent_field(self) -> None:
        """Test detection of surface referencing non-existent entity field."""
        entity = ir.EntitySpec(
            name="Task",
            title="A task item",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                    modifiers=[ir.FieldModifier.PK],
                ),
            ],
        )
        surface = ir.SurfaceSpec(
            name="task_list",
            title="Tasks",
            entity_ref="Task",
            mode=ir.SurfaceMode.LIST,
            sections=[
                ir.SurfaceSection(
                    name="main",
                    elements=[
                        ir.SurfaceElement(field_name="nonexistent_field", label="Title"),
                    ],
                ),
            ],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
            surfaces=[surface],
        )

        errors, warnings = validate_surfaces(appspec)

        assert any("nonexistent_field" in e for e in errors)

    def test_surface_no_sections_warning(self) -> None:
        """Test warning for surface with no sections."""
        entity = ir.EntitySpec(
            name="Task",
            title="A task item",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                    modifiers=[ir.FieldModifier.PK],
                ),
            ],
        )
        surface = ir.SurfaceSpec(
            name="task_list",
            title="Tasks",
            entity_ref="Task",
            mode=ir.SurfaceMode.LIST,
            sections=[],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
            surfaces=[surface],
        )

        errors, warnings = validate_surfaces(appspec)

        assert any("no sections" in w for w in warnings)

    def test_create_mode_without_entity_ref_warning(self) -> None:
        """Test warning for create mode without entity reference."""
        surface = ir.SurfaceSpec(
            name="task_create",
            title="Create Task",
            mode=ir.SurfaceMode.CREATE,
            sections=[],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            surfaces=[surface],
        )

        errors, warnings = validate_surfaces(appspec)

        assert any("create" in w and "no entity reference" in w for w in warnings)


# =============================================================================
# Experience Validation Tests
# =============================================================================


class TestValidateExperiences:
    """Test experience validation."""

    def test_valid_experience(self) -> None:
        """Test validation of a valid experience."""
        experience = ir.ExperienceSpec(
            name="onboarding",
            title="User Onboarding",
            start_step="welcome",
            steps=[
                ir.ExperienceStep(
                    name="welcome",
                    kind=ir.StepKind.SURFACE,
                    surface="welcome_page",
                    transitions=[
                        ir.StepTransition(
                            event=ir.TransitionEvent.SUCCESS,
                            next_step="complete",
                        ),
                    ],
                ),
                ir.ExperienceStep(
                    name="complete",
                    kind=ir.StepKind.SURFACE,
                    surface="completion_page",
                    transitions=[],
                ),
            ],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            experiences=[experience],
        )

        errors, warnings = validate_experiences(appspec)

        assert len(errors) == 0

    def test_experience_no_steps(self) -> None:
        """Test detection of experience with no steps."""
        experience = ir.ExperienceSpec(
            name="empty",
            title="Empty Experience",
            start_step="nowhere",
            steps=[],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            experiences=[experience],
        )

        errors, warnings = validate_experiences(appspec)

        assert any("no steps" in e for e in errors)

    def test_experience_unreachable_steps(self) -> None:
        """Test detection of unreachable steps."""
        experience = ir.ExperienceSpec(
            name="flow",
            title="Flow",
            start_step="step1",
            steps=[
                ir.ExperienceStep(
                    name="step1",
                    kind=ir.StepKind.SURFACE,
                    surface="page1",
                    transitions=[],  # No way to get to step2
                ),
                ir.ExperienceStep(
                    name="step2",  # Unreachable
                    kind=ir.StepKind.SURFACE,
                    surface="page2",
                    transitions=[],
                ),
            ],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            experiences=[experience],
        )

        errors, warnings = validate_experiences(appspec)

        assert any("unreachable" in w.lower() for w in warnings)

    def test_surface_step_without_surface(self) -> None:
        """Test detection of surface step without surface target."""
        experience = ir.ExperienceSpec(
            name="flow",
            title="Flow",
            start_step="step1",
            steps=[
                ir.ExperienceStep(
                    name="step1",
                    kind=ir.StepKind.SURFACE,
                    surface=None,  # Missing surface
                    transitions=[],
                ),
            ],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            experiences=[experience],
        )

        errors, warnings = validate_experiences(appspec)

        assert any("no surface target" in e for e in errors)


# =============================================================================
# Service Validation Tests
# =============================================================================


class TestValidateServices:
    """Test service (API) validation."""

    def test_valid_service(self) -> None:
        """Test validation of a valid service."""
        api = ir.APISpec(
            name="github",
            title="GitHub API",
            spec_url="https://api.github.com/openapi.yaml",
            spec_inline=None,
            auth_profile=ir.AuthProfile(kind=ir.AuthKind.API_KEY_HEADER),
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            apis=[api],
        )

        errors, warnings = validate_services(appspec)

        assert len(errors) == 0

    def test_service_no_spec(self) -> None:
        """Test detection of service without spec."""
        api = ir.APISpec(
            name="github",
            title="GitHub API",
            spec_url=None,
            spec_inline=None,
            auth_profile=ir.AuthProfile(kind=ir.AuthKind.API_KEY_HEADER),
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            apis=[api],
        )

        errors, warnings = validate_services(appspec)

        assert any("no spec" in e for e in errors)

    def test_service_invalid_url_warning(self) -> None:
        """Test warning for invalid spec URL."""
        api = ir.APISpec(
            name="github",
            title="GitHub API",
            spec_url="not-a-valid-url",
            spec_inline=None,
            auth_profile=ir.AuthProfile(kind=ir.AuthKind.API_KEY_HEADER),
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            apis=[api],
        )

        errors, warnings = validate_services(appspec)

        assert any("invalid" in w.lower() for w in warnings)

    def test_oauth2_without_scopes_warning(self) -> None:
        """Test warning for OAuth2 without scopes."""
        api = ir.APISpec(
            name="github",
            title="GitHub API",
            spec_url="https://api.github.com/openapi.yaml",
            spec_inline=None,
            auth_profile=ir.AuthProfile(
                kind=ir.AuthKind.OAUTH2_PKCE,
                options={},  # No scopes
            ),
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            apis=[api],
        )

        errors, warnings = validate_services(appspec)

        assert any("scopes" in w for w in warnings)


# =============================================================================
# Foreign Model Validation Tests
# =============================================================================


class TestValidateForeignModels:
    """Test foreign model validation."""

    def test_valid_foreign_model(self) -> None:
        """Test validation of a valid foreign model."""
        foreign_model = ir.ForeignModelSpec(
            name="GitHubUser",
            title="GitHub User",
            api_ref="github",
            key_fields=["id"],
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.INT),
                ),
                ir.FieldSpec(
                    name="login",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=100),
                ),
            ],
            constraints=[],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            foreign_models=[foreign_model],
        )

        errors, warnings = validate_foreign_models(appspec)

        assert len(errors) == 0

    def test_foreign_model_no_key_fields(self) -> None:
        """Test detection of foreign model without key fields."""
        foreign_model = ir.ForeignModelSpec(
            name="GitHubUser",
            title="GitHub User",
            api_ref="github",
            key_fields=[],  # No key fields
            fields=[
                ir.FieldSpec(
                    name="login",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=100),
                ),
            ],
            constraints=[],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            foreign_models=[foreign_model],
        )

        errors, warnings = validate_foreign_models(appspec)

        assert any("no key fields" in e for e in errors)

    def test_foreign_model_key_field_not_defined(self) -> None:
        """Test detection of key field not in fields list."""
        foreign_model = ir.ForeignModelSpec(
            name="GitHubUser",
            title="GitHub User",
            api_ref="github",
            key_fields=["nonexistent_id"],  # Key field not in fields
            fields=[
                ir.FieldSpec(
                    name="login",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=100),
                ),
            ],
            constraints=[],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            foreign_models=[foreign_model],
        )

        errors, warnings = validate_foreign_models(appspec)

        assert any("not defined" in e for e in errors)


# =============================================================================
# Integration Validation Tests
# =============================================================================


class TestValidateIntegrations:
    """Test integration validation."""

    def test_integration_no_apis_warning(self) -> None:
        """Test warning for integration without API references."""
        integration = ir.IntegrationSpec(
            name="sync_users",
            title="Sync Users",
            api_refs=[],  # No API refs
            actions=[],
            syncs=[],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            integrations=[integration],
        )

        errors, warnings = validate_integrations(appspec)

        assert any("doesn't use any APIs" in w for w in warnings)

    def test_integration_no_actions_or_syncs_warning(self) -> None:
        """Test warning for integration without actions or syncs."""
        integration = ir.IntegrationSpec(
            name="sync_users",
            title="Sync Users",
            api_refs=["github"],
            actions=[],  # No actions
            syncs=[],  # No syncs
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            integrations=[integration],
        )

        errors, warnings = validate_integrations(appspec)

        assert any("no actions or syncs" in w for w in warnings)


# =============================================================================
# Extended Lint Tests
# =============================================================================


class TestExtendedLint:
    """Test extended lint rules."""

    def test_entity_naming_convention(self) -> None:
        """Test warning for non-PascalCase entity names."""
        entity = ir.EntitySpec(
            name="task",  # Should be PascalCase
            title="A task",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                    modifiers=[ir.FieldModifier.PK],
                ),
            ],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
        )

        warnings = extended_lint(appspec)

        assert any("PascalCase" in w for w in warnings)

    def test_unused_entities_warning(self) -> None:
        """Test warning for unused entities."""
        entity1 = ir.EntitySpec(
            name="Task",
            title="A task",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                    modifiers=[ir.FieldModifier.PK],
                ),
            ],
        )
        entity2 = ir.EntitySpec(
            name="Orphan",  # Never referenced
            title="Orphan",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                    modifiers=[ir.FieldModifier.PK],
                ),
            ],
        )
        surface = ir.SurfaceSpec(
            name="task_list",
            title="Tasks",
            entity_ref="Task",  # Only references Task, not Orphan
            mode=ir.SurfaceMode.LIST,
            sections=[],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity1, entity2]),
            surfaces=[surface],
        )

        warnings = extended_lint(appspec)

        assert any("Unused entities" in w and "Orphan" in w for w in warnings)

    def test_missing_title_warning(self) -> None:
        """Test warning for missing titles."""
        entity = ir.EntitySpec(
            name="Task",
            title=None,  # Missing title
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                    modifiers=[ir.FieldModifier.PK],
                ),
            ],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
        )

        warnings = extended_lint(appspec)

        assert any("no title" in w for w in warnings)
