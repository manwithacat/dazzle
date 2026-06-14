"""
Unit tests for the semantic validator module.

Tests validation of entities, surfaces, experiences, services, and UX specs
for semantic correctness.

Refactored to use helper functions and parameterization where applicable.
"""

from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.core.parser import parse_modules
from dazzle.core.validator import (
    extended_lint,
    validate_entities,
    validate_experiences,
    validate_foreign_models,
    validate_integrations,
    validate_nav_curation,
    validate_persona_nav_refs,
    validate_services,
    validate_surfaces,
    validate_ux_specs,
    validate_workspace_primary_actions,
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

    @pytest.mark.parametrize(
        ("entity_factory", "predicate", "channel"),
        [
            # test_duplicate_field_names
            (
                lambda: make_entity(
                    fields=[
                        make_id_field(),
                        ir.FieldSpec(
                            name="title",
                            type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                        ),
                        ir.FieldSpec(
                            name="title",
                            type=ir.FieldType(kind=ir.FieldTypeKind.TEXT),
                        ),
                    ]
                ),
                lambda msg: "duplicate field names" in msg,
                "errors",
            ),
            # test_decimal_scale_greater_than_precision
            (
                lambda: make_entity(
                    fields=[
                        make_id_field(),
                        ir.FieldSpec(
                            name="amount",
                            type=ir.FieldType(kind=ir.FieldTypeKind.DECIMAL, precision=5, scale=10),
                        ),
                    ]
                ),
                lambda msg: "scale" in msg and "precision" in msg,
                "errors",
            ),
            # test_string_very_large_max_length_warning
            (
                lambda: make_entity(
                    fields=[
                        make_id_field(),
                        ir.FieldSpec(
                            name="description",
                            type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=20000),
                        ),
                    ]
                ),
                lambda msg: "text" in msg.lower(),
                "warnings",
            ),
            # test_conflicting_modifiers
            (
                lambda: make_entity(
                    fields=[
                        make_id_field(),
                        ir.FieldSpec(
                            name="title",
                            type=ir.FieldType(kind=ir.FieldTypeKind.STR, max_length=200),
                            modifiers=[ir.FieldModifier.REQUIRED, ir.FieldModifier.OPTIONAL],
                        ),
                    ]
                ),
                lambda msg: "required" in msg and "optional" in msg,
                "errors",
            ),
            # test_auto_modifier_on_non_datetime
            (
                lambda: make_entity(
                    fields=[
                        make_id_field(),
                        ir.FieldSpec(
                            name="counter",
                            type=ir.FieldType(kind=ir.FieldTypeKind.INT),
                            modifiers=[ir.FieldModifier.AUTO_ADD],
                        ),
                    ]
                ),
                lambda msg: "auto_add" in msg,
                "warnings",
            ),
            # test_constraint_references_nonexistent_field
            (
                lambda: make_entity(
                    constraints=[
                        ir.Constraint(
                            kind=ir.ConstraintKind.UNIQUE,
                            fields=["nonexistent_field"],
                        ),
                    ]
                ),
                lambda msg: "nonexistent_field" in msg,
                "errors",
            ),
            # test_permit_without_scope_warns
            (
                lambda: ir.EntitySpec(
                    name="Task",
                    title="Task",
                    fields=[make_id_field()],
                    access=ir.AccessSpec(
                        permissions=[
                            ir.PermissionRule(
                                operation=ir.PermissionKind.READ,
                                require_auth=True,
                                effect=ir.PolicyEffect.PERMIT,
                            )
                        ]
                    ),
                ),
                lambda msg: "no scope: blocks" in msg,
                "warnings",
            ),
        ],
        ids=[
            "test_duplicate_field_names",
            "test_decimal_scale_greater_than_precision",
            "test_string_very_large_max_length_warning",
            "test_conflicting_modifiers",
            "test_auto_modifier_on_non_datetime",
            "test_constraint_references_nonexistent_field",
            "test_permit_without_scope_warns",
        ],
    )
    def test_entity_validation_diagnostics(self, entity_factory, predicate, channel: str) -> None:
        """Various entity-validation diagnostics surface the right error/warning fragments."""
        entity = entity_factory()
        appspec = make_appspec(entities=[entity])
        errors, warnings = validate_entities(appspec)
        messages = errors if channel == "errors" else warnings
        assert any(predicate(m) for m in messages)

    @pytest.mark.parametrize(
        "entity_name,field_name,expected_name",
        [
            ("Select", "id", "Select"),
            ("Task", "delete", "delete"),
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

    def test_system_entity_skips_scope_warning(self) -> None:
        """Framework-generated entities (patterns=['system']) skip the scope warning."""
        entity = ir.EntitySpec(
            name="AIJob",
            title="AI Job",
            fields=[make_id_field()],
            patterns=["system", "audit"],
            access=ir.AccessSpec(
                permissions=[
                    ir.PermissionRule(
                        operation=ir.PermissionKind.READ,
                        require_auth=True,
                        effect=ir.PolicyEffect.PERMIT,
                    )
                ]
            ),
        )
        appspec = make_appspec(entities=[entity])
        errors, warnings = validate_entities(appspec)
        assert not any("no scope: blocks" in w for w in warnings)


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
                "no surface or entity target",
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

    def test_service_warnings(self) -> None:
        """Service validation: no-spec error, invalid-url warning, oauth2-no-scopes warning.

        Combined: service_no_spec, service_invalid_url_warning, oauth2_without_scopes_warning.
        """
        # No-spec → error
        api1 = ir.APISpec(
            name="github",
            title="GitHub API",
            spec_url=None,
            spec_inline=None,
            auth_profile=ir.AuthProfile(kind=ir.AuthKind.API_KEY_HEADER),
        )
        errors, _ = validate_services(make_appspec(apis=[api1]))
        assert any("no spec" in e for e in errors)

        # Invalid URL → warning
        api2 = ir.APISpec(
            name="github",
            title="GitHub API",
            spec_url="not-a-valid-url",
            spec_inline=None,
            auth_profile=ir.AuthProfile(kind=ir.AuthKind.API_KEY_HEADER),
        )
        _, warnings = validate_services(make_appspec(apis=[api2]))
        assert any("invalid" in w.lower() for w in warnings)

        # OAuth2 without scopes → warning
        api3 = ir.APISpec(
            name="github",
            title="GitHub API",
            spec_url="https://api.github.com/openapi.yaml",
            spec_inline=None,
            auth_profile=ir.AuthProfile(kind=ir.AuthKind.OAUTH2_PKCE, options={}),
        )
        _, warnings3 = validate_services(make_appspec(apis=[api3]))
        assert any("scopes" in w for w in warnings3)


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
            (["github"], [], [], "no actions, syncs, or mappings"),
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
        assert any("Dead construct: entity 'Orphan'" in w for w in warnings)

    def test_missing_title_warning(self) -> None:
        """Test warning for missing titles."""
        entity = make_entity(title=None)
        appspec = make_appspec(entities=[entity])
        warnings = extended_lint(appspec)
        assert any("no title" in w for w in warnings)


# =============================================================================
# Dead Construct Detection Tests
# =============================================================================


class TestDeadConstructDetection:
    """Test dead construct detection (unreferenced entities and surfaces)."""

    def _make_surface(self, name: str = "task_list", entity_ref: str = "Task") -> ir.SurfaceSpec:
        return ir.SurfaceSpec(
            name=name,
            title=name.replace("_", " ").title(),
            entity_ref=entity_ref,
            mode=ir.SurfaceMode.LIST,
            sections=[],
        )

    def _make_workspace(
        self,
        name: str = "dashboard",
        regions: list[ir.WorkspaceRegion] | None = None,
    ) -> ir.WorkspaceSpec:
        return ir.WorkspaceSpec(
            name=name,
            title=name.replace("_", " ").title(),
            purpose="Test workspace",
            regions=regions or [],
        )

    # --- Entity reachability (not-dead cases) ---

    def _appspec_entity_used_by_surface(self) -> tuple[ir.AppSpec, str]:
        entity = make_entity(name="Task")
        surface = self._make_surface(entity_ref="Task")
        return make_appspec(entities=[entity], surfaces=[surface]), "entity 'Task'"

    def _appspec_entity_used_by_field_ref(self) -> tuple[ir.AppSpec, str]:
        ref_field = ir.FieldSpec(
            name="assigned_to",
            type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="User"),
        )
        task = make_entity(name="Task", fields=[make_id_field(), ref_field])
        user = make_entity(name="User")
        return make_appspec(entities=[task, user]), "entity 'User'"

    def _appspec_entity_used_by_workspace_source(self) -> tuple[ir.AppSpec, str]:
        entity = make_entity(name="Alert")
        region = ir.WorkspaceRegion(name="alerts", source="Alert")
        workspace = self._make_workspace(regions=[region])
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
            workspaces=[workspace],
        )
        return appspec, "entity 'Alert'"

    def _appspec_entity_used_by_process_trigger(self) -> tuple[ir.AppSpec, str]:
        entity = make_entity(name="Order")
        trigger = ir.ProcessTriggerSpec(
            kind=ir.ProcessTriggerKind.ENTITY_EVENT,
            entity_name="Order",
            event_type="created",
        )
        process = ir.ProcessSpec(name="order_flow", trigger=trigger, steps=[])
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
            processes=[process],
        )
        return appspec, "entity 'Order'"

    def _appspec_surface_used_by_workspace_action(self) -> tuple[ir.AppSpec, str]:
        entity = make_entity(name="Task")
        surface = self._make_surface(name="task_edit", entity_ref="Task")
        region = ir.WorkspaceRegion(name="tasks", source="Task", action="task_edit")
        workspace = self._make_workspace(regions=[region])
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
            surfaces=[surface],
            workspaces=[workspace],
        )
        return appspec, "surface 'task_edit'"

    def _appspec_surface_used_by_experience_step(self) -> tuple[ir.AppSpec, str]:
        entity = make_entity(name="Task")
        surface = self._make_surface(name="welcome", entity_ref="Task")
        step = ir.ExperienceStep(
            name="start",
            kind=ir.StepKind.SURFACE,
            surface="welcome",
        )
        experience = ir.ExperienceSpec(
            name="onboarding",
            title="Onboarding",
            start_step="start",
            steps=[step],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
            surfaces=[surface],
            experiences=[experience],
        )
        return appspec, "surface 'welcome'"

    def _appspec_surface_used_by_process_human_task(self) -> tuple[ir.AppSpec, str]:
        entity = make_entity(name="Task")
        surface = self._make_surface(name="approval_form", entity_ref="Task")
        human_task = ir.HumanTaskSpec(surface="approval_form")
        step = ir.ProcessStepSpec(
            name="approve",
            kind=ir.ProcessStepKind.HUMAN_TASK,
            human_task=human_task,
        )
        process = ir.ProcessSpec(name="approval_flow", steps=[step])
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
            surfaces=[surface],
            processes=[process],
        )
        return appspec, "surface 'approval_form'"

    def _appspec_surface_used_as_workspace_source(self) -> tuple[ir.AppSpec, str]:
        entity = make_entity(name="Task")
        surface = self._make_surface(name="task_list", entity_ref="Task")
        region = ir.WorkspaceRegion(name="tasks", source="task_list")
        workspace = self._make_workspace(regions=[region])
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
            surfaces=[surface],
            workspaces=[workspace],
        )
        return appspec, "surface 'task_list'"

    @pytest.mark.parametrize(
        "builder_name",
        [
            "test_entity_used_by_surface_is_not_dead",
            "test_entity_used_by_field_ref_is_not_dead",
            "test_entity_used_by_workspace_source_is_not_dead",
            "test_entity_used_by_process_trigger_is_not_dead",
            "test_surface_used_by_workspace_action_is_not_dead",
            "test_surface_used_by_experience_step_is_not_dead",
            "test_surface_used_by_process_human_task_is_not_dead",
            "test_surface_used_as_workspace_source_is_not_dead",
        ],
        ids=[
            "test_entity_used_by_surface_is_not_dead",
            "test_entity_used_by_field_ref_is_not_dead",
            "test_entity_used_by_workspace_source_is_not_dead",
            "test_entity_used_by_process_trigger_is_not_dead",
            "test_surface_used_by_workspace_action_is_not_dead",
            "test_surface_used_by_experience_step_is_not_dead",
            "test_surface_used_by_process_human_task_is_not_dead",
            "test_surface_used_as_workspace_source_is_not_dead",
        ],
    )
    def test_referenced_construct_is_not_dead(self, builder_name: str) -> None:
        """Referenced entities and surfaces must not appear in dead-construct warnings."""
        _builder_map = {
            "test_entity_used_by_surface_is_not_dead": self._appspec_entity_used_by_surface,
            "test_entity_used_by_field_ref_is_not_dead": self._appspec_entity_used_by_field_ref,
            "test_entity_used_by_workspace_source_is_not_dead": self._appspec_entity_used_by_workspace_source,
            "test_entity_used_by_process_trigger_is_not_dead": self._appspec_entity_used_by_process_trigger,
            "test_surface_used_by_workspace_action_is_not_dead": self._appspec_surface_used_by_workspace_action,
            "test_surface_used_by_experience_step_is_not_dead": self._appspec_surface_used_by_experience_step,
            "test_surface_used_by_process_human_task_is_not_dead": self._appspec_surface_used_by_process_human_task,
            "test_surface_used_as_workspace_source_is_not_dead": self._appspec_surface_used_as_workspace_source,
        }
        appspec, dead_name_fragment = _builder_map[builder_name]()
        warnings = extended_lint(appspec)
        assert not any(dead_name_fragment in w for w in warnings)

    @pytest.mark.parametrize(
        "appspec_fn,dead_warning_fragment",
        [
            # test_orphan_entity_is_reported
            (
                lambda self: make_appspec(entities=[make_entity(name="Orphan")]),
                "Dead construct: entity 'Orphan'",
            ),
            # test_unreferenced_surface_is_reported
            (
                lambda self: make_appspec(
                    entities=[make_entity(name="Task")],
                    surfaces=[
                        ir.SurfaceSpec(
                            name="orphan_view",
                            title="Orphan View",
                            entity_ref="Task",
                            mode=ir.SurfaceMode.LIST,
                            sections=[],
                        )
                    ],
                ),
                "Dead construct: surface 'orphan_view'",
            ),
        ],
        ids=[
            "test_orphan_entity_is_reported",
            "test_unreferenced_surface_is_reported",
        ],
    )
    def test_dead_construct_is_reported(self, appspec_fn, dead_warning_fragment: str) -> None:
        """Unreferenced entities and surfaces must appear in dead-construct warnings."""
        appspec = appspec_fn(self)
        warnings = extended_lint(appspec)
        assert any(dead_warning_fragment in w for w in warnings)

    # --- Multiple dead constructs ---

    def test_multiple_dead_constructs_all_reported(self) -> None:
        orphan1 = make_entity(name="Orphan1")
        orphan2 = make_entity(name="Orphan2")
        dead_surface = self._make_surface(name="dead_view", entity_ref="Orphan1")
        appspec = make_appspec(entities=[orphan1, orphan2], surfaces=[dead_surface])
        warnings = extended_lint(appspec)
        dead_warnings = [w for w in warnings if "Dead construct" in w]
        # Both entities and the surface should be reported
        assert any("entity 'Orphan2'" in w for w in dead_warnings)
        assert any("surface 'dead_view'" in w for w in dead_warnings)

    # --- No false positives for well-connected specs ---

    # --- Per-persona nav defs keep entities/surfaces alive (#1332) ---

    def test_surface_reachable_via_nav_def_is_not_dead(self) -> None:
        """An entity living only in a top-level `nav` def keeps its CRUD surfaces
        alive — mirrors the workspace nav_groups reachability rule (#1324, #1332).

        Regression for #1332: migrating workspace ``nav_groups`` into per-persona
        ``nav <name>:`` defs must not flag the moved entities' surfaces as dead.
        """
        entity = make_entity(name="Beneficiary")
        surface = self._make_surface(name="beneficiary_list", entity_ref="Beneficiary")
        nav = ir.NavSpec(
            name="advisor",
            groups=[
                ir.NavGroupSpec(
                    label="Records",
                    items=[ir.NavItemIR(entity="Beneficiary")],
                )
            ],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
            surfaces=[surface],
            navs=[nav],
        )
        warnings = extended_lint(appspec)
        assert not any("Dead construct" in w and "beneficiary_list" in w for w in warnings)
        assert not any("Dead construct" in w and "Beneficiary" in w for w in warnings)

    # --- related blocks keep child entities/surfaces alive (#1380) ---

    def test_child_entity_via_related_block_is_not_dead(self) -> None:
        """#1380: a child entity surfaced via a `related ...: show: <Entity>`
        block on a detail surface — and that child's CRUD surfaces — are
        reachable from the parent detail page, not dead."""
        task = make_entity(name="Task")
        comment = make_entity(name="Comment")
        task_detail = ir.SurfaceSpec(
            name="task_detail",
            title="Task Detail",
            entity_ref="Task",
            mode=ir.SurfaceMode.VIEW,
            sections=[],
            related_groups=[
                ir.RelatedGroup(
                    name="comments", show=["Comment"], display=ir.RelatedDisplayMode.TABLE
                )
            ],
        )
        comment_create = self._make_surface(name="comment_create", entity_ref="Comment")
        # Task is reachable via a workspace region (keeps task_detail alive too).
        region = ir.WorkspaceRegion(name="tasks", source="Task")
        workspace = self._make_workspace(regions=[region])
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[task, comment]),
            surfaces=[task_detail, comment_create],
            workspaces=[workspace],
        )
        warnings = extended_lint(appspec)
        assert not any("Dead construct" in w and "'Comment'" in w for w in warnings)
        assert not any("Dead construct" in w and "comment_create" in w for w in warnings)

    # --- managed_by exempts entity + surfaces from dead-construct (#1333) ---

    def test_managed_by_entity_and_surfaces_not_dead(self) -> None:
        """An entity marked `managed_by:` is reachable only via a custom
        route/pipeline/wizard/external mechanism — it and its CRUD surfaces
        are exempt from the dead-construct lint, like `domain: platform` but
        without reclassifying the domain (#1333).
        """
        entity = ir.EntitySpec(
            name="OnboardingProgress",
            title="Onboarding Progress",
            fields=[make_id_field()],
            managed_by=ir.ManagedBy.ROUTE,
        )
        surface = self._make_surface(
            name="onboarding_progress_list", entity_ref="OnboardingProgress"
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
            surfaces=[surface],
        )
        warnings = extended_lint(appspec)
        assert not any("Dead construct" in w and "OnboardingProgress" in w for w in warnings)
        assert not any("Dead construct" in w and "onboarding_progress_list" in w for w in warnings)

    def test_unmarked_orphan_entity_still_dead(self) -> None:
        """Sanity: the exemption is opt-in — an unmarked orphan is still flagged."""
        entity = make_entity(name="Orphan")
        appspec = ir.AppSpec(name="Test", domain=ir.DomainSpec(entities=[entity]), surfaces=[])
        warnings = extended_lint(appspec)
        assert any("Dead construct: entity 'Orphan'" in w for w in warnings)

    def test_fully_connected_spec_has_no_dead_warnings(self) -> None:
        task = make_entity(name="Task")
        user = make_entity(
            name="User",
            fields=[make_id_field()],
        )
        # Task has ref to User
        ref_field = ir.FieldSpec(
            name="assigned_to",
            type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="User"),
        )
        task = make_entity(name="Task", fields=[make_id_field(), ref_field])

        task_list = self._make_surface(name="task_list", entity_ref="Task")
        user_edit = self._make_surface(name="user_edit", entity_ref="User")

        region1 = ir.WorkspaceRegion(name="tasks", source="Task", action="task_list")
        region2 = ir.WorkspaceRegion(name="users", source="User", action="user_edit")
        workspace = self._make_workspace(regions=[region1, region2])

        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[task, user]),
            surfaces=[task_list, user_edit],
            workspaces=[workspace],
        )
        warnings = extended_lint(appspec)
        assert not any("Dead construct" in w for w in warnings)


# =============================================================================
# Workspace Region Filter FK Traversal Tests (#419)
# =============================================================================


class TestWorkspaceFilterFKTraversal:
    """Test that workspace region filters support FK traversal on related entity fields."""

    def test_single_hop_fk_traversal_valid(self) -> None:
        """filter: assessment_event.department = ... should pass when assessment_event is a ref."""
        department = make_entity(name="Department", fields=[make_id_field()])
        event = make_entity(
            name="AssessmentEvent",
            fields=[
                make_id_field(),
                ir.FieldSpec(
                    name="department",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Department"),
                ),
            ],
        )
        submission = make_entity(
            name="AssessmentSubmission",
            fields=[
                make_id_field(),
                ir.FieldSpec(
                    name="assessment_event",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="AssessmentEvent"),
                ),
            ],
        )
        region = ir.WorkspaceRegion(
            name="submissions",
            source="AssessmentSubmission",
            filter=ir.ConditionExpr(
                comparison=ir.Comparison(
                    field="assessment_event.department",
                    operator=ir.ComparisonOperator.EQUALS,
                    value=ir.ConditionValue(literal="some-dept-id"),
                ),
            ),
        )
        workspace = ir.WorkspaceSpec(name="hub", title="Hub", regions=[region])
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[department, event, submission]),
            workspaces=[workspace],
        )
        errors, _ = validate_ux_specs(appspec)
        assert not errors

    def test_two_hop_fk_traversal_valid(self) -> None:
        """filter: mark_scheme.subject.department = ... should pass with valid chain."""
        department = make_entity(name="Department", fields=[make_id_field()])
        subject = make_entity(
            name="Subject",
            fields=[
                make_id_field(),
                ir.FieldSpec(
                    name="department",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Department"),
                ),
            ],
        )
        mark_scheme = make_entity(
            name="MarkScheme",
            fields=[
                make_id_field(),
                ir.FieldSpec(
                    name="subject",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="Subject"),
                ),
            ],
        )
        version = make_entity(
            name="MarkSchemeVersion",
            fields=[
                make_id_field(),
                ir.FieldSpec(
                    name="mark_scheme",
                    type=ir.FieldType(kind=ir.FieldTypeKind.REF, ref_entity="MarkScheme"),
                ),
            ],
        )
        region = ir.WorkspaceRegion(
            name="versions",
            source="MarkSchemeVersion",
            filter=ir.ConditionExpr(
                comparison=ir.Comparison(
                    field="mark_scheme.subject.department",
                    operator=ir.ComparisonOperator.EQUALS,
                    value=ir.ConditionValue(literal="some-dept-id"),
                ),
            ),
        )
        workspace = ir.WorkspaceSpec(name="hub", title="Hub", regions=[region])
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[department, subject, mark_scheme, version]),
            workspaces=[workspace],
        )
        errors, _ = validate_ux_specs(appspec)
        assert not errors

    def test_fk_traversal_invalid_first_segment(self) -> None:
        """filter: nonexistent.department = ... should fail."""
        entity = make_entity(name="Task", fields=[make_id_field()])
        region = ir.WorkspaceRegion(
            name="tasks",
            source="Task",
            filter=ir.ConditionExpr(
                comparison=ir.Comparison(
                    field="nonexistent.department",
                    operator=ir.ComparisonOperator.EQUALS,
                    value=ir.ConditionValue(literal="x"),
                ),
            ),
        )
        workspace = ir.WorkspaceSpec(name="hub", title="Hub", regions=[region])
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
            workspaces=[workspace],
        )
        errors, _ = validate_ux_specs(appspec)
        assert any("nonexistent.department" in e for e in errors)

    def test_fk_traversal_non_ref_field(self) -> None:
        """filter: title.something = ... should fail when title is not a ref."""
        entity = make_entity(
            name="Task",
            fields=[
                make_id_field(),
                ir.FieldSpec(name="title", type=ir.FieldType(kind=ir.FieldTypeKind.STR)),
            ],
        )
        region = ir.WorkspaceRegion(
            name="tasks",
            source="Task",
            filter=ir.ConditionExpr(
                comparison=ir.Comparison(
                    field="title.something",
                    operator=ir.ComparisonOperator.EQUALS,
                    value=ir.ConditionValue(literal="x"),
                ),
            ),
        )
        workspace = ir.WorkspaceSpec(name="hub", title="Hub", regions=[region])
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
            workspaces=[workspace],
        )
        errors, _ = validate_ux_specs(appspec)
        assert any("not a reference field" in e for e in errors)

    def test_direct_field_still_validated(self) -> None:
        """Non-dotted field names should still be validated as before."""
        entity = make_entity(name="Task", fields=[make_id_field()])
        region = ir.WorkspaceRegion(
            name="tasks",
            source="Task",
            filter=ir.ConditionExpr(
                comparison=ir.Comparison(
                    field="bogus_field",
                    operator=ir.ComparisonOperator.EQUALS,
                    value=ir.ConditionValue(literal="x"),
                ),
            ),
        )
        workspace = ir.WorkspaceSpec(name="hub", title="Hub", regions=[region])
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[entity]),
            workspaces=[workspace],
        )
        errors, _ = validate_ux_specs(appspec)
        assert any("bogus_field" in e for e in errors)


# =============================================================================
# Persona nav_ref Resolution Tests (#1324)
# =============================================================================


class TestValidatePersonaNavRefs:
    """A persona's `uses nav <name>` must resolve to a declared `nav <name>:`."""

    def test_unresolved_persona_nav_ref_is_error(self) -> None:
        """A persona referencing an undeclared nav produces a validation error."""
        persona = ir.PersonaSpec(id="teacher", label="Teacher", nav_ref="nonexistent")
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            personas=[persona],
            navs=[],
        )
        errors, _ = validate_persona_nav_refs(appspec)
        assert any("teacher" in e and "nonexistent" in e for e in errors)

    def test_resolved_persona_nav_ref_no_error(self) -> None:
        """A persona referencing a declared nav produces no such error."""
        persona = ir.PersonaSpec(id="teacher", label="Teacher", nav_ref="teaching")
        nav = ir.NavSpec(name="teaching", groups=[])
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            personas=[persona],
            navs=[nav],
        )
        errors, _ = validate_persona_nav_refs(appspec)
        assert errors == []

    def test_persona_without_nav_ref_no_error(self) -> None:
        """A persona with nav_ref=None is unaffected."""
        persona = ir.PersonaSpec(id="teacher", label="Teacher")
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            personas=[persona],
            navs=[],
        )
        errors, _ = validate_persona_nav_refs(appspec)
        assert errors == []


class TestValidateWorkspacePrimaryActions:
    """A workspace `primary_actions:` target must resolve (#1324 FR-5)."""

    def _surface(self, name: str) -> ir.SurfaceSpec:
        return ir.SurfaceSpec(name=name, mode=ir.SurfaceMode.CREATE, entity_ref="Invoice")

    def test_unknown_surface_target_is_error(self) -> None:
        ws = ir.WorkspaceSpec(
            name="reports",
            primary_actions=[
                ir.WorkspacePrimaryActionSpec(
                    label="New Invoice", target_kind="surface", target="nope"
                )
            ],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            surfaces=[],
            workspaces=[ws],
        )
        errors, _ = validate_workspace_primary_actions(appspec)
        assert any("reports" in e and "nope" in e and "surface" in e for e in errors)

    def test_unknown_workspace_target_is_error(self) -> None:
        ws = ir.WorkspaceSpec(
            name="reports",
            primary_actions=[
                ir.WorkspacePrimaryActionSpec(
                    label="Dashboard", target_kind="workspace", target="missing_ws"
                )
            ],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            workspaces=[ws],
        )
        errors, _ = validate_workspace_primary_actions(appspec)
        assert any("reports" in e and "missing_ws" in e and "workspace" in e for e in errors)

    def test_valid_targets_no_error(self) -> None:
        target_ws = ir.WorkspaceSpec(name="ops_dashboard")
        ws = ir.WorkspaceSpec(
            name="reports",
            primary_actions=[
                ir.WorkspacePrimaryActionSpec(
                    label="New Invoice", target_kind="surface", target="create_invoice"
                ),
                ir.WorkspacePrimaryActionSpec(
                    label="Dashboard", target_kind="workspace", target="ops_dashboard"
                ),
            ],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            surfaces=[self._surface("create_invoice")],
            workspaces=[ws, target_ws],
        )
        errors, _ = validate_workspace_primary_actions(appspec)
        assert errors == []

    def test_no_primary_actions_no_error(self) -> None:
        ws = ir.WorkspaceSpec(name="reports")
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            workspaces=[ws],
        )
        errors, _ = validate_workspace_primary_actions(appspec)
        assert errors == []

    def test_wired_into_lint_appspec(self, tmp_path: Path) -> None:
        """A real parse→link→lint run surfaces the unknown-target error."""
        from dazzle.core.linker import build_appspec
        from dazzle.core.lint import lint_appspec
        from dazzle.core.parser import parse_modules

        dsl = """
module t
app MyApp "My App"

entity Invoice "Invoice":
  id: uuid pk

workspace reports "Reports":
  primary_actions:
    action "Go" -> surface does_not_exist
  metrics:
    source: Invoice
"""
        dsl_dir = tmp_path / "dsl"
        dsl_dir.mkdir()
        (dsl_dir / "app.dsl").write_text(dsl)
        (tmp_path / "dazzle.toml").write_text(
            '[project]\nname = "t"\nversion = "0.1.0"\nroot = "t"\n[modules]\npaths = ["./dsl"]\n'
        )
        modules = parse_modules([dsl_dir / "app.dsl"])
        appspec = build_appspec(modules, "t")
        errors, _warnings, _rel = lint_appspec(appspec, extended=False)
        assert any("does_not_exist" in e for e in errors)


class TestValidateNavCuration:
    """Navigation curation lint (#1324 FR-6) — WARNINGS only.

    Three diagnostics: auto-discovery reliance, dead curated nav items,
    and ignored author-declared workspace nav_groups.
    """

    # --- Diagnostic 1: auto-discovery reliance ---------------------------

    def test_persona_without_nav_warns_auto_discovery(self) -> None:
        """A persona with nav_ref=None gets an auto-discovery-reliance warning."""
        persona = ir.PersonaSpec(id="teacher", label="Teacher")
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            personas=[persona],
            navs=[],
        )
        errors, warnings = validate_nav_curation(appspec)
        assert errors == []
        assert any(
            "teacher" in w and "auto-discovered" in w and "uses nav" in w for w in warnings
        ), warnings

    def test_persona_with_nav_no_auto_discovery_warning(self) -> None:
        """A persona WITH an explicit nav gets no auto-discovery warning for it."""
        persona = ir.PersonaSpec(id="teacher", label="Teacher", nav_ref="teaching")
        nav = ir.NavSpec(name="teaching", groups=[])
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            personas=[persona],
            navs=[nav],
        )
        _errors, warnings = validate_nav_curation(appspec)
        assert not any("teacher" in w and "auto-discovered" in w for w in warnings), warnings

    # --- Diagnostic 2: dead curated nav item -----------------------------

    def test_dead_curated_item_warns(self, tmp_path: Path) -> None:
        """A nav listing an entity the bound persona can't LIST → dead-link warning."""
        dsl = """module test
app TestApp "Test"

entity Secret "Secret":
  id: uuid pk
  name: str(100) required
  permit:
    list: role(admin) or role(manager)
    read: role(admin) or role(manager)
    create: role(admin)
    update: role(admin)
    delete: role(admin)

nav membernav:
  group "Main":
    Secret

persona member "Member":
  uses nav membernav
"""
        appspec = _appspec(dsl, tmp_path)
        _errors, warnings = validate_nav_curation(appspec)
        assert any("membernav" in w and "Secret" in w and "dead link" in w for w in warnings), (
            warnings
        )

    def test_listable_curated_item_no_dead_warning(self, tmp_path: Path) -> None:
        """A nav listing an entity the bound persona CAN list → no dead-link warning."""
        dsl = """module test
app TestApp "Test"

entity Task "Task":
  id: uuid pk
  title: str(200) required
  permit:
    list: role(admin) or role(member)
    read: role(admin) or role(member)
    create: role(admin)
    update: role(admin)
    delete: role(admin)

nav membernav:
  group "Main":
    Task

persona member "Member":
  uses nav membernav
"""
        appspec = _appspec(dsl, tmp_path)
        _errors, warnings = validate_nav_curation(appspec)
        assert not any("dead link" in w for w in warnings), warnings

    def test_nav_item_matching_nothing_warns(self) -> None:
        """A nav item that is neither an entity nor a workspace warns."""
        nav = ir.NavSpec(
            name="membernav",
            groups=[ir.NavGroupSpec(label="Main", items=[ir.NavItemIR(entity="Bogus")])],
        )
        persona = ir.PersonaSpec(id="member", label="Member", nav_ref="membernav")
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            personas=[persona],
            navs=[nav],
        )
        _errors, warnings = validate_nav_curation(appspec)
        assert any("membernav" in w and "Bogus" in w and "does not match" in w for w in warnings), (
            warnings
        )

    def test_nav_with_no_bound_persona_warns(self) -> None:
        """A nav no persona binds to warns once and skips per-item checks."""
        nav = ir.NavSpec(
            name="orphan",
            groups=[ir.NavGroupSpec(label="Main", items=[ir.NavItemIR(entity="Bogus")])],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            personas=[],
            navs=[nav],
        )
        _errors, warnings = validate_nav_curation(appspec)
        assert any("orphan" in w and "not used by any persona" in w for w in warnings), warnings
        # Per-item checks are skipped — no dead/does-not-match warning for Bogus.
        assert not any("Bogus" in w for w in warnings), warnings

    # --- Diagnostic 3: ignored workspace nav_groups ----------------------

    def test_author_workspace_nav_groups_warns(self) -> None:
        """An author workspace (no leading _) declaring nav_groups warns."""
        ws = ir.WorkspaceSpec(
            name="dashboard",
            nav_groups=[ir.NavGroupSpec(label="Main", items=[ir.NavItemIR(entity="Task")])],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            personas=[],
            workspaces=[ws],
        )
        _errors, warnings = validate_nav_curation(appspec)
        assert any("dashboard" in w and "nav_groups" in w and "ignored" in w for w in warnings), (
            warnings
        )

    def test_framework_workspace_nav_groups_no_warning(self) -> None:
        """A _-prefixed (framework) workspace with nav_groups does NOT warn."""
        ws = ir.WorkspaceSpec(
            name="_platform_admin",
            nav_groups=[ir.NavGroupSpec(label="Main", items=[ir.NavItemIR(entity="Task")])],
        )
        appspec = ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[]),
            personas=[],
            workspaces=[ws],
        )
        _errors, warnings = validate_nav_curation(appspec)
        assert not any("_platform_admin" in w and "ignored" in w for w in warnings), warnings

    # --- Diagnostic 4: undeclared tenant_config in nav `when` (#1324 FR-4) ---

    @staticmethod
    def _tenant_flag_cond(key: str) -> ir.ConditionExpr:
        """A bare ``tenant_config.<key>`` flag → implicit ``= true`` truthy
        comparison, as parse_condition_expr emits it."""
        return ir.ConditionExpr(
            comparison=ir.Comparison(
                field=f"tenant_config.{key}",
                operator=ir.ComparisonOperator.EQUALS,
                value=ir.ConditionValue(literal=True),
            )
        )

    def _nav_appspec_with_when(
        self,
        *,
        group_when: ir.ConditionExpr | None = None,
        item_when: ir.ConditionExpr | None = None,
        declared_keys: dict[str, str] | None = None,
    ) -> ir.AppSpec:
        nav = ir.NavSpec(
            name="membernav",
            groups=[
                ir.NavGroupSpec(
                    label="Main",
                    when=group_when,
                    items=[ir.NavItemIR(entity="Task", when=item_when)],
                )
            ],
        )
        persona = ir.PersonaSpec(id="member", label="Member", nav_ref="membernav")
        # Task is listable by member so no dead-link noise crowds the assertion.
        task = ir.EntitySpec(
            name="Task",
            label="Task",
            fields=[
                ir.FieldSpec(
                    name="id",
                    type=ir.FieldType(kind=ir.FieldTypeKind.UUID),
                    modifiers=[ir.FieldModifier.PK],
                )
            ],
        )
        tenancy = (
            ir.TenancySpec(per_tenant_config=declared_keys) if declared_keys is not None else None
        )
        return ir.AppSpec(
            name="Test",
            domain=ir.DomainSpec(entities=[task]),
            personas=[persona],
            navs=[nav],
            tenancy=tenancy,
        )

    def test_group_when_undeclared_tenant_config_warns(self) -> None:
        appspec = self._nav_appspec_with_when(
            group_when=self._tenant_flag_cond("mis_connected"),
            declared_keys={"locale": "str"},
        )
        _errors, warnings = validate_nav_curation(appspec)
        assert any(
            "membernav" in w and "tenant_config" in w and "mis_connected" in w for w in warnings
        ), warnings

    def test_item_when_undeclared_tenant_config_warns(self) -> None:
        appspec = self._nav_appspec_with_when(
            item_when=self._tenant_flag_cond("beta_features"),
            declared_keys={"locale": "str"},
        )
        _errors, warnings = validate_nav_curation(appspec)
        assert any(
            "membernav" in w and "tenant_config" in w and "beta_features" in w for w in warnings
        ), warnings

    def test_declared_tenant_config_key_no_warning(self) -> None:
        appspec = self._nav_appspec_with_when(
            group_when=self._tenant_flag_cond("mis_connected"),
            declared_keys={"mis_connected": "bool"},
        )
        _errors, warnings = validate_nav_curation(appspec)
        assert not any("tenant_config" in w for w in warnings), warnings

    def test_no_tenancy_declared_tenant_config_ref_warns(self) -> None:
        """No tenancy block at all → a tenant_config ref is undeclared → warn."""
        appspec = self._nav_appspec_with_when(
            group_when=self._tenant_flag_cond("mis_connected"),
            declared_keys=None,
        )
        _errors, warnings = validate_nav_curation(appspec)
        assert any(
            "membernav" in w and "tenant_config" in w and "mis_connected" in w for w in warnings
        ), warnings

    def test_no_when_no_tenant_config_warning(self) -> None:
        appspec = self._nav_appspec_with_when(declared_keys={"locale": "str"})
        _errors, warnings = validate_nav_curation(appspec)
        assert not any("tenant_config" in w for w in warnings), warnings


def _appspec(dsl: str, tmp_path: Path) -> ir.AppSpec:
    """Helper to parse DSL, link, and return AppSpec."""
    dsl_dir = tmp_path / "dsl"
    dsl_dir.mkdir()
    (dsl_dir / "app.dsl").write_text(dsl)
    (tmp_path / "dazzle.toml").write_text(
        '[project]\nname = "test"\nversion = "0.1.0"\nroot = "test"\n[modules]\npaths = ["./dsl"]\n'
    )
    modules = parse_modules([dsl_dir / "app.dsl"])
    return build_appspec(modules, "test")


class TestPersonaNavRefPipelineIntegration:
    """Integration test: persona nav_ref validation through full parse→link→lint."""

    def test_resolved_nav_ref_passes_full_pipeline(self, tmp_path: Path) -> None:
        """DSL with a resolved persona nav_ref must parse, link, and lint without error."""
        dsl = """module test
app TestApp "Test Application"

nav teaching:
  group "Marking":
    Assignment

persona teacher "Teacher":
  uses nav teaching
"""
        appspec = _appspec(dsl, tmp_path)
        errors, _warnings, _relevance = lint_appspec(appspec, suggest=False)

        # Assert: no error about unresolved nav_ref
        assert not any("uses nav" in e and "teaching" in e for e in errors), errors

        # Assert: appspec.navs was populated by the linker
        assert appspec.navs is not None, "appspec.navs should be populated"
        assert len(appspec.navs) > 0, "appspec.navs should contain at least one nav"
        nav_names = [n.name for n in appspec.navs]
        assert "teaching" in nav_names, f"Expected 'teaching' nav, got {nav_names}"

    def test_unresolved_nav_ref_fails_full_pipeline(self, tmp_path: Path) -> None:
        """DSL with an unresolved persona nav_ref must produce a validation error."""
        dsl = """module test
app TestApp "Test Application"

persona teacher "Teacher":
  uses nav missing
"""
        appspec = _appspec(dsl, tmp_path)
        errors, _warnings, _relevance = lint_appspec(appspec, suggest=False)

        # Assert: lint_appspec includes the persona nav_ref error
        assert any("missing" in e for e in errors), (
            f"Expected error mentioning 'missing' nav, got {errors}"
        )
