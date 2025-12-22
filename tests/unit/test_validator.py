"""
Unit tests for the semantic validator module.

Tests validation of entities, surfaces, experiences, services, and UX specs
for semantic correctness.

Refactored to use helper functions and parameterization where applicable.
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
)

# =============================================================================
# Helper Functions
# =============================================================================


def make_id_field() -> ir.FieldSpec:
    """Create a standard UUID primary key field."""
    return ir.FieldSpec(
        name="id",
        type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
        modifiers=[ir.FieldModifier.PK],
    )


def make_entity(
    name: str = "Task",
    title: str | None = "A task item",
    fields: list[ir.FieldSpec] | None = None,
    constraints: list[ir.Constraint] | None = None,
) -> ir.EntitySpec:
    """Create an entity with sensible defaults."""
    if fields is None:
        fields = [make_id_field()]
    return ir.EntitySpec(
        name=name,
        title=title,
        fields=fields,
        constraints=constraints or [],
    )


def make_appspec(
    entities: list[ir.EntitySpec] | None = None,
    surfaces: list[ir.SurfaceSpec] | None = None,
    experiences: list[ir.ExperienceSpec] | None = None,
    apis: list[ir.APISpec] | None = None,
    foreign_models: list[ir.ForeignModelSpec] | None = None,
    integrations: list[ir.IntegrationSpec] | None = None,
) -> ir.AppSpec:
    """Create an AppSpec with sensible defaults."""
    return ir.AppSpec(
        name="Test",
        domain=ir.DomainSpec(entities=entities or []),
        surfaces=surfaces or [],
        experiences=experiences or [],
        apis=apis or [],
        foreign_models=foreign_models or [],
        integrations=integrations or [],
    )


# =============================================================================
# Entity Validation Tests
# =============================================================================


class TestValidateEntities:
    """Test entity validation."""

    def test_valid_entity(self) -> None:
        """Test validation of a valid entity."""
        entity = make_entity(
            fields=[
                make_id_field(),
                ir.FieldSpec(
                    name="title",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                    modifiers=[ir.FieldModifier.REQUIRED],
                ),
            ]
        )
        appspec = make_appspec(entities=[entity])
        errors, warnings = validate_entities(appspec)
        assert len(errors) == 0
        assert len(warnings) == 0

    @pytest.mark.parametrize(
        "extra_field,error_fragment",
        [
            # Missing primary key
            (None, "no primary key"),
            # Enum without values
            (
                ir.FieldSpec(
                    name="status",
                    type=ir.FieldType(kind=ir.FieldTypeKind.ENUM, enum_values=[]),
                ),
                "enum type but no values",
            ),
            # Decimal missing precision
            (
                ir.FieldSpec(
                    name="amount",
                    type=ir.FieldType(kind=ir.FieldTypeKind.DECIMAL),
                ),
                "missing precision/scale",
            ),
            # String missing max_length
            (
                ir.FieldSpec(
                    name="title",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR),
                ),
                "no max_length",
            ),
        ],
        ids=[
            "missing_pk",
            "enum_no_values",
            "decimal_no_precision",
            "string_no_max_length",
        ],
    )
    def test_field_type_errors(self, extra_field: ir.FieldSpec | None, error_fragment: str) -> None:
        """Test detection of various field type errors."""
        if extra_field is None:
            # Special case: no PK
            fields = [
                ir.FieldSpec(
                    name="title",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                )
            ]
        else:
            fields = [make_id_field(), extra_field]

        entity = make_entity(fields=fields)
        appspec = make_appspec(entities=[entity])
        errors, warnings = validate_entities(appspec)
        assert any(error_fragment in e for e in errors)

    def test_duplicate_field_names(self) -> None:
        """Test detection of duplicate field names."""
        entity = make_entity(
            fields=[
                make_id_field(),
                ir.FieldSpec(
                    name="title",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                ),
                ir.FieldSpec(
                    name="title",  # Duplicate
                    type=ir.FieldType(kind=ir.FieldTypeKind.TEXT),
                ),
            ]
        )
        appspec = make_appspec(entities=[entity])
        errors, warnings = validate_entities(appspec)
        assert any("duplicate field names" in e for e in errors)

    def test_decimal_scale_greater_than_precision(self) -> None:
        """Test detection of invalid decimal scale > precision."""
        entity = make_entity(
            fields=[
                make_id_field(),
                ir.FieldSpec(
                    name="amount",
                    type=ir.FieldType(kind=ir.FieldTypeKind.DECIMAL, precision=5, scale=10),
                ),
            ]
        )
        appspec = make_appspec(entities=[entity])
        errors, warnings = validate_entities(appspec)
        assert any("scale" in e and "precision" in e for e in errors)

    def test_string_very_large_max_length_warning(self) -> None:
        """Test warning for very large string max_length."""
        entity = make_entity(
            fields=[
                make_id_field(),
                ir.FieldSpec(
                    name="description",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=20000),
                ),
            ]
        )
        appspec = make_appspec(entities=[entity])
        errors, warnings = validate_entities(appspec)
        assert any("text" in w.lower() for w in warnings)

    @pytest.mark.parametrize(
        "entity_name,field_name,expected_name",
        [
            ("Order", "id", "Order"),
            ("Task", "order", "order"),
        ],
        ids=["entity_name", "field_name"],
    )
    def test_sql_reserved_word_warning(
        self, entity_name: str, field_name: str, expected_name: str
    ) -> None:
        """Test warning for SQL reserved words in names."""
        fields = [make_id_field()]
        if field_name != "id":
            fields.append(
                ir.FieldSpec(
                    name=field_name,
                    type=ir.FieldType(kind=ir.FieldTypeKind.INT),
                )
            )
        entity = make_entity(name=entity_name, fields=fields)
        appspec = make_appspec(entities=[entity])
        errors, warnings = validate_entities(appspec)
        assert len(errors) == 0
        assert any("SQL reserved word" in w and expected_name in w for w in warnings)

    def test_conflicting_modifiers(self) -> None:
        """Test detection of conflicting required/optional modifiers."""
        entity = make_entity(
            fields=[
                make_id_field(),
                ir.FieldSpec(
                    name="title",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                    modifiers=[ir.FieldModifier.REQUIRED, ir.FieldModifier.OPTIONAL],
                ),
            ]
        )
        appspec = make_appspec(entities=[entity])
        errors, warnings = validate_entities(appspec)
        assert any("required" in e and "optional" in e for e in errors)

    def test_auto_modifier_on_non_datetime(self) -> None:
        """Test warning for auto_add/auto_update on non-datetime field."""
        entity = make_entity(
            fields=[
                make_id_field(),
                ir.FieldSpec(
                    name="counter",
                    type=ir.FieldType(kind=ir.FieldTypeKind.INT),
                    modifiers=[ir.FieldModifier.AUTO_ADD],
                ),
            ]
        )
        appspec = make_appspec(entities=[entity])
        errors, warnings = validate_entities(appspec)
        assert any("auto_add" in w for w in warnings)

    def test_constraint_references_nonexistent_field(self) -> None:
        """Test detection of constraint referencing non-existent field."""
        entity = make_entity(
            constraints=[
                ir.Constraint(
                    kind=ir.ConstraintKind.UNIQUE,
                    fields=["nonexistent_field"],
                ),
            ]
        )
        appspec = make_appspec(entities=[entity])
        errors, warnings = validate_entities(appspec)
        assert any("nonexistent_field" in e for e in errors)


# =============================================================================
# Surface Validation Tests
# =============================================================================


class TestValidateSurfaces:
    """Test surface validation."""

    def test_valid_surface(self) -> None:
        """Test validation of a valid surface."""
        entity = make_entity(
            fields=[
                make_id_field(),
                ir.FieldSpec(
                    name="title",
                    type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                ),
            ]
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
        appspec = make_appspec(entities=[entity], surfaces=[surface])
        errors, warnings = validate_surfaces(appspec)
        assert len(errors) == 0

    def test_surface_references_nonexistent_field(self) -> None:
        """Test detection of surface referencing non-existent entity field."""
        entity = make_entity()
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
        appspec = make_appspec(entities=[entity], surfaces=[surface])
        errors, warnings = validate_surfaces(appspec)
        assert any("nonexistent_field" in e for e in errors)

    def test_surface_no_sections_warning(self) -> None:
        """Test warning for surface with no sections."""
        entity = make_entity()
        surface = ir.SurfaceSpec(
            name="task_list",
            title="Tasks",
            entity_ref="Task",
            mode=ir.SurfaceMode.LIST,
            sections=[],
        )
        appspec = make_appspec(entities=[entity], surfaces=[surface])
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
        appspec = make_appspec(surfaces=[surface])
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
        appspec = make_appspec(experiences=[experience])
        errors, warnings = validate_experiences(appspec)
        assert len(errors) == 0

    @pytest.mark.parametrize(
        "experience,error_fragment",
        [
            (
                ir.ExperienceSpec(
                    name="empty",
                    title="Empty Experience",
                    start_step="nowhere",
                    steps=[],
                ),
                "no steps",
            ),
            (
                ir.ExperienceSpec(
                    name="flow",
                    title="Flow",
                    start_step="step1",
                    steps=[
                        ir.ExperienceStep(
                            name="step1",
                            kind=ir.StepKind.SURFACE,
                            surface=None,
                            transitions=[],
                        ),
                    ],
                ),
                "no surface target",
            ),
        ],
        ids=["no_steps", "surface_step_without_surface"],
    )
    def test_experience_errors(self, experience: ir.ExperienceSpec, error_fragment: str) -> None:
        """Test detection of experience errors."""
        appspec = make_appspec(experiences=[experience])
        errors, warnings = validate_experiences(appspec)
        assert any(error_fragment in e for e in errors)

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
                    transitions=[],
                ),
                ir.ExperienceStep(
                    name="step2",  # Unreachable
                    kind=ir.StepKind.SURFACE,
                    surface="page2",
                    transitions=[],
                ),
            ],
        )
        appspec = make_appspec(experiences=[experience])
        errors, warnings = validate_experiences(appspec)
        assert any("unreachable" in w.lower() for w in warnings)


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
        appspec = make_appspec(apis=[api])
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
        appspec = make_appspec(apis=[api])
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
        appspec = make_appspec(apis=[api])
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
                options={},
            ),
        )
        appspec = make_appspec(apis=[api])
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
        appspec = make_appspec(foreign_models=[foreign_model])
        errors, warnings = validate_foreign_models(appspec)
        assert len(errors) == 0

    @pytest.mark.parametrize(
        "key_fields,field_list,error_fragment",
        [
            ([], [("login", ir.FieldTypeKind.STR, 100)], "no key fields"),
            (
                ["nonexistent_id"],
                [("login", ir.FieldTypeKind.STR, 100)],
                "not defined",
            ),
        ],
        ids=["no_key_fields", "key_field_not_defined"],
    )
    def test_foreign_model_key_errors(
        self,
        key_fields: list[str],
        field_list: list[tuple],
        error_fragment: str,
    ) -> None:
        """Test detection of foreign model key field errors."""
        fields = [
            ir.FieldSpec(
                name=name,
                type=ir.FieldType(kind=kind, max_length=max_len),
            )
            for name, kind, max_len in field_list
        ]
        foreign_model = ir.ForeignModelSpec(
            name="GitHubUser",
            title="GitHub User",
            api_ref="github",
            key_fields=key_fields,
            fields=fields,
            constraints=[],
        )
        appspec = make_appspec(foreign_models=[foreign_model])
        errors, warnings = validate_foreign_models(appspec)
        assert any(error_fragment in e for e in errors)


# =============================================================================
# Integration Validation Tests
# =============================================================================


class TestValidateIntegrations:
    """Test integration validation."""

    @pytest.mark.parametrize(
        "api_refs,actions,syncs,warning_fragment",
        [
            ([], [], [], "doesn't use any APIs"),
            (["github"], [], [], "no actions or syncs"),
        ],
        ids=["no_apis", "no_actions_or_syncs"],
    )
    def test_integration_warnings(
        self,
        api_refs: list[str],
        actions: list,
        syncs: list,
        warning_fragment: str,
    ) -> None:
        """Test warnings for integration issues."""
        integration = ir.IntegrationSpec(
            name="sync_users",
            title="Sync Users",
            api_refs=api_refs,
            actions=actions,
            syncs=syncs,
        )
        appspec = make_appspec(integrations=[integration])
        errors, warnings = validate_integrations(appspec)
        assert any(warning_fragment in w for w in warnings)


# =============================================================================
# Extended Lint Tests
# =============================================================================


class TestExtendedLint:
    """Test extended lint rules."""

    def test_entity_naming_convention(self) -> None:
        """Test warning for non-PascalCase entity names."""
        entity = make_entity(name="task")  # Should be PascalCase
        appspec = make_appspec(entities=[entity])
        warnings = extended_lint(appspec)
        assert any("PascalCase" in w for w in warnings)

    def test_unused_entities_warning(self) -> None:
        """Test warning for unused entities."""
        entity1 = make_entity(name="Task")
        entity2 = make_entity(name="Orphan")  # Never referenced
        surface = ir.SurfaceSpec(
            name="task_list",
            title="Tasks",
            entity_ref="Task",  # Only references Task
            mode=ir.SurfaceMode.LIST,
            sections=[],
        )
        appspec = make_appspec(entities=[entity1, entity2], surfaces=[surface])
        warnings = extended_lint(appspec)
        assert any("Unused entities" in w and "Orphan" in w for w in warnings)

    def test_missing_title_warning(self) -> None:
        """Test warning for missing titles."""
        entity = make_entity(title=None)
        appspec = make_appspec(entities=[entity])
        warnings = extended_lint(appspec)
        assert any("no title" in w for w in warnings)
