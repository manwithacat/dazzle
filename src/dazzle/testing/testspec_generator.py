"""
E2E TestSpec Generator.

Generates E2ETestSpec from AppSpec, automatically creating:
- CRUD flows for each entity
- Validation flows from field constraints
- Navigation flows from surfaces
- Test fixtures from entity schemas
"""

from dazzle.core.ir import (
    A11yRule,
    AppSpec,
    E2ETestSpec,
    EntitySpec,
    FieldModifier,
    FieldSpec,
    FieldTypeKind,
    FixtureSpec,
    FlowAssertion,
    FlowAssertionKind,
    FlowPrecondition,
    FlowPriority,
    FlowSpec,
    FlowStep,
    FlowStepKind,
    SurfaceAccessSpec,
    SurfaceMode,
    SurfaceSpec,
    UsabilityRule,
)
from dazzle.core.manifest import ProjectManifest
from dazzle.testing.auth_flows import generate_all_auth_flows

# =============================================================================
# Fixture Generation
# =============================================================================


def _generate_field_value(field: FieldSpec, suffix: str = "") -> str | int | float | bool:
    """Generate a sample value for a field based on its type."""
    kind = field.type.kind

    if kind == FieldTypeKind.STR:
        max_len = field.type.max_length or 50
        base = f"Test {field.name.replace('_', ' ').title()}"
        return (base + suffix)[:max_len]

    elif kind == FieldTypeKind.TEXT:
        return f"Sample text content for {field.name}{suffix}."

    elif kind == FieldTypeKind.INT:
        return 42

    elif kind == FieldTypeKind.DECIMAL:
        return 99.99

    elif kind == FieldTypeKind.BOOL:
        return True

    elif kind == FieldTypeKind.DATE:
        return "2025-01-15"

    elif kind == FieldTypeKind.DATETIME:
        return "2025-01-15T10:30:00Z"

    elif kind == FieldTypeKind.UUID:
        # UUIDs are typically auto-generated, skip
        return None  # type: ignore

    elif kind == FieldTypeKind.EMAIL:
        return f"test{suffix}@example.com"

    elif kind == FieldTypeKind.ENUM:
        # Use first enum value
        if field.type.enum_values:
            return field.type.enum_values[0]
        return "default"

    elif kind == FieldTypeKind.REF:
        # References need fixture refs, skip here
        return None  # type: ignore

    return f"value{suffix}"


def generate_entity_fixtures(entity: EntitySpec) -> list[FixtureSpec]:
    """Generate test fixtures for an entity."""
    fixtures: list[FixtureSpec] = []

    # Valid fixture - all required fields
    valid_data: dict[str, str | int | float | bool] = {}
    for field in entity.fields:
        if field.is_primary_key:
            continue  # Skip auto-generated PKs
        if field.type.kind == FieldTypeKind.REF:
            continue  # Skip refs, handled separately
        value = _generate_field_value(field)
        if value is not None:
            valid_data[field.name] = value

    fixtures.append(
        FixtureSpec(
            id=f"{entity.name}_valid",
            entity=entity.name,
            data=valid_data,
            description=f"Valid {entity.name} fixture with all required fields",
        )
    )

    # Additional fixture for update tests
    update_data = valid_data.copy()
    for field in entity.fields:
        if field.is_primary_key or field.type.kind in (FieldTypeKind.UUID, FieldTypeKind.REF):
            continue
        value = _generate_field_value(field, "_updated")
        if value is not None:
            update_data[field.name] = value

    fixtures.append(
        FixtureSpec(
            id=f"{entity.name}_updated",
            entity=entity.name,
            data=update_data,
            description=f"Updated {entity.name} fixture for update tests",
        )
    )

    return fixtures


def generate_fixtures(appspec: AppSpec) -> list[FixtureSpec]:
    """Generate all fixtures from AppSpec entities."""
    fixtures: list[FixtureSpec] = []
    for entity in appspec.domain.entities:
        fixtures.extend(generate_entity_fixtures(entity))
    return fixtures


# =============================================================================
# CRUD Flow Generation
# =============================================================================


def _get_list_surface_name(entity: EntitySpec, appspec: AppSpec) -> str:
    """Find or generate the list surface name for an entity."""
    # Look for existing list surface
    for surface in appspec.surfaces:
        if surface.entity_ref == entity.name and surface.mode == SurfaceMode.LIST:
            return surface.name
    # Default naming convention
    return f"{entity.name.lower()}_list"


def _get_create_surface_name(entity: EntitySpec, appspec: AppSpec) -> str:
    """Find or generate the create surface name for an entity."""
    for surface in appspec.surfaces:
        if surface.entity_ref == entity.name and surface.mode == SurfaceMode.CREATE:
            return surface.name
    return f"{entity.name.lower()}_create"


def _get_edit_surface_name(entity: EntitySpec, appspec: AppSpec) -> str:
    """Find or generate the edit surface name for an entity."""
    for surface in appspec.surfaces:
        if surface.entity_ref == entity.name and surface.mode == SurfaceMode.EDIT:
            return surface.name
    return f"{entity.name.lower()}_edit"


def _get_required_fields(entity: EntitySpec) -> list[FieldSpec]:
    """Get all required fields for an entity."""
    return [
        f
        for f in entity.fields
        if f.is_required
        and not f.is_primary_key
        and f.type.kind not in (FieldTypeKind.UUID, FieldTypeKind.REF)
    ]


def _get_form_fields(entity: EntitySpec) -> list[FieldSpec]:
    """Get all fields that appear in a form (non-auto fields)."""
    excluded_kinds = {FieldTypeKind.UUID}
    return [
        f
        for f in entity.fields
        if not f.is_primary_key
        and f.type.kind not in excluded_kinds
        and FieldModifier.AUTO_ADD not in f.modifiers
        and FieldModifier.AUTO_UPDATE not in f.modifiers
    ]


def generate_create_flow(entity: EntitySpec, appspec: AppSpec) -> FlowSpec:
    """Generate a create flow for an entity."""
    list_surface = _get_list_surface_name(entity, appspec)
    form_fields = _get_form_fields(entity)

    steps: list[FlowStep] = [
        FlowStep(
            kind=FlowStepKind.NAVIGATE,
            target=f"view:{list_surface}",
            description=f"Navigate to {entity.name} list",
        ),
        FlowStep(
            kind=FlowStepKind.CLICK,
            target=f"action:{entity.name}.create",
            description=f"Click create {entity.name} button",
        ),
    ]

    # Fill each form field
    for field in form_fields:
        if field.type.kind == FieldTypeKind.REF:
            continue  # Skip refs for now
        steps.append(
            FlowStep(
                kind=FlowStepKind.FILL,
                target=f"field:{entity.name}.{field.name}",
                fixture_ref=f"{entity.name}_valid.{field.name}",
                description=f"Fill {field.name} field",
            )
        )

    # Submit and assert
    steps.extend(
        [
            FlowStep(
                kind=FlowStepKind.CLICK,
                target=f"action:{entity.name}.save",
                description="Click save button",
            ),
            FlowStep(
                kind=FlowStepKind.ASSERT,
                assertion=FlowAssertion(
                    kind=FlowAssertionKind.ENTITY_EXISTS,
                    target=entity.name,
                ),
                description=f"Assert {entity.name} was created",
            ),
        ]
    )

    return FlowSpec(
        id=f"{entity.name}_create_valid",
        description=f"Create a valid {entity.name} entity",
        priority=FlowPriority.HIGH,
        steps=steps,
        tags=["crud", "create", entity.name.lower()],
        entity=entity.name,
        auto_generated=True,
    )


def generate_view_flow(entity: EntitySpec, appspec: AppSpec) -> FlowSpec:
    """Generate a view/detail flow for an entity."""
    list_surface = _get_list_surface_name(entity, appspec)

    steps: list[FlowStep] = [
        FlowStep(
            kind=FlowStepKind.NAVIGATE,
            target=f"view:{list_surface}",
            description=f"Navigate to {entity.name} list",
        ),
        FlowStep(
            kind=FlowStepKind.CLICK,
            target=f"row:{entity.name}",
            description=f"Click on a {entity.name} row",
        ),
        FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(
                kind=FlowAssertionKind.VISIBLE,
                target=f"view:{entity.name.lower()}_detail",
            ),
            description=f"Assert {entity.name} detail view is visible",
        ),
    ]

    return FlowSpec(
        id=f"{entity.name}_view_detail",
        description=f"View a {entity.name} entity detail",
        priority=FlowPriority.MEDIUM,
        preconditions=FlowPrecondition(fixtures=[f"{entity.name}_valid"]),
        steps=steps,
        tags=["crud", "read", entity.name.lower()],
        entity=entity.name,
        auto_generated=True,
    )


def generate_update_flow(entity: EntitySpec, appspec: AppSpec) -> FlowSpec:
    """Generate an update flow for an entity."""
    list_surface = _get_list_surface_name(entity, appspec)
    form_fields = _get_form_fields(entity)

    steps: list[FlowStep] = [
        FlowStep(
            kind=FlowStepKind.NAVIGATE,
            target=f"view:{list_surface}",
            description=f"Navigate to {entity.name} list",
        ),
        FlowStep(
            kind=FlowStepKind.CLICK,
            target=f"action:{entity.name}.edit",
            description=f"Click edit {entity.name} button",
        ),
    ]

    # Update at least one field
    if form_fields:
        field = form_fields[0]
        if field.type.kind != FieldTypeKind.REF:
            steps.append(
                FlowStep(
                    kind=FlowStepKind.FILL,
                    target=f"field:{entity.name}.{field.name}",
                    fixture_ref=f"{entity.name}_updated.{field.name}",
                    description=f"Update {field.name} field",
                )
            )

    steps.extend(
        [
            FlowStep(
                kind=FlowStepKind.CLICK,
                target=f"action:{entity.name}.save",
                description="Click save button",
            ),
            FlowStep(
                kind=FlowStepKind.ASSERT,
                assertion=FlowAssertion(
                    kind=FlowAssertionKind.ENTITY_EXISTS,
                    target=entity.name,
                ),
                description=f"Assert {entity.name} was updated",
            ),
        ]
    )

    return FlowSpec(
        id=f"{entity.name}_update_valid",
        description=f"Update a {entity.name} entity",
        priority=FlowPriority.HIGH,
        preconditions=FlowPrecondition(fixtures=[f"{entity.name}_valid"]),
        steps=steps,
        tags=["crud", "update", entity.name.lower()],
        entity=entity.name,
        auto_generated=True,
    )


def generate_delete_flow(entity: EntitySpec, appspec: AppSpec) -> FlowSpec:
    """Generate a delete flow for an entity."""
    list_surface = _get_list_surface_name(entity, appspec)

    steps: list[FlowStep] = [
        FlowStep(
            kind=FlowStepKind.NAVIGATE,
            target=f"view:{list_surface}",
            description=f"Navigate to {entity.name} list",
        ),
        FlowStep(
            kind=FlowStepKind.CLICK,
            target=f"action:{entity.name}.delete",
            description=f"Click delete {entity.name} button",
        ),
        FlowStep(
            kind=FlowStepKind.CLICK,
            target="action:confirm",
            description="Confirm deletion",
        ),
        FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(
                kind=FlowAssertionKind.ENTITY_NOT_EXISTS,
                target=entity.name,
            ),
            description=f"Assert {entity.name} was deleted",
        ),
    ]

    return FlowSpec(
        id=f"{entity.name}_delete",
        description=f"Delete a {entity.name} entity",
        priority=FlowPriority.MEDIUM,
        preconditions=FlowPrecondition(fixtures=[f"{entity.name}_valid"]),
        steps=steps,
        tags=["crud", "delete", entity.name.lower()],
        entity=entity.name,
        auto_generated=True,
    )


def generate_entity_crud_flows(entity: EntitySpec, appspec: AppSpec) -> list[FlowSpec]:
    """Generate all CRUD flows for an entity."""
    flows: list[FlowSpec] = [
        generate_create_flow(entity, appspec),
        generate_view_flow(entity, appspec),
        generate_update_flow(entity, appspec),
        generate_delete_flow(entity, appspec),
    ]
    return flows


# =============================================================================
# Validation Flow Generation
# =============================================================================


def generate_validation_flows(entity: EntitySpec, appspec: AppSpec) -> list[FlowSpec]:
    """Generate validation error flows from field constraints."""
    flows: list[FlowSpec] = []
    list_surface = _get_list_surface_name(entity, appspec)
    required_fields = _get_required_fields(entity)

    # Test missing required field
    for field in required_fields:
        steps: list[FlowStep] = [
            FlowStep(
                kind=FlowStepKind.NAVIGATE,
                target=f"view:{list_surface}",
                description=f"Navigate to {entity.name} list",
            ),
            FlowStep(
                kind=FlowStepKind.CLICK,
                target=f"action:{entity.name}.create",
                description=f"Click create {entity.name} button",
            ),
            # Don't fill the required field, just submit
            FlowStep(
                kind=FlowStepKind.CLICK,
                target=f"action:{entity.name}.save",
                description="Click save without filling required field",
            ),
            FlowStep(
                kind=FlowStepKind.ASSERT,
                assertion=FlowAssertion(
                    kind=FlowAssertionKind.VALIDATION_ERROR,
                    target=f"field:{entity.name}.{field.name}",
                ),
                description=f"Assert validation error on {field.name}",
            ),
        ]

        flows.append(
            FlowSpec(
                id=f"{entity.name}_validation_required_{field.name}",
                description=f"Validation error when {field.name} is missing",
                priority=FlowPriority.MEDIUM,
                steps=steps,
                tags=["validation", "required", entity.name.lower()],
                entity=entity.name,
                auto_generated=True,
            )
        )

    return flows


# =============================================================================
# Surface Navigation Flow Generation
# =============================================================================


def generate_surface_flows(surface: SurfaceSpec, appspec: AppSpec) -> list[FlowSpec]:
    """Generate navigation flows for a surface."""
    flows: list[FlowSpec] = []

    # Basic navigation test
    steps: list[FlowStep] = [
        FlowStep(
            kind=FlowStepKind.NAVIGATE,
            target=f"view:{surface.name}",
            description=f"Navigate to {surface.title or surface.name}",
        ),
        FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(
                kind=FlowAssertionKind.VISIBLE,
                target=f"view:{surface.name}",
            ),
            description=f"Assert {surface.name} view is visible",
        ),
    ]

    flows.append(
        FlowSpec(
            id=f"navigate_{surface.name}",
            description=f"Navigate to {surface.title or surface.name}",
            priority=FlowPriority.LOW,
            steps=steps,
            tags=["navigation", surface.name],
            entity=surface.entity_ref,
            auto_generated=True,
        )
    )

    return flows


# =============================================================================
# Usability Rules Generation
# =============================================================================


def generate_usability_rules(appspec: AppSpec) -> list[UsabilityRule]:
    """Generate default usability rules."""
    return [
        UsabilityRule(
            id="high_priority_max_steps",
            description="High priority flows should complete in 5 steps or less",
            check="max_steps",
            threshold=5,
            target="priority:high",
            severity="warning",
        ),
        UsabilityRule(
            id="primary_action_visible",
            description="Primary actions should be visible on page load",
            check="primary_action_visible",
            severity="error",
        ),
        UsabilityRule(
            id="destructive_confirm",
            description="Destructive actions should have confirmation dialogs",
            check="destructive_confirm",
            severity="error",
        ),
        UsabilityRule(
            id="validation_near_field",
            description="Validation messages should appear near the field",
            check="validation_placement",
            severity="warning",
        ),
    ]


# =============================================================================
# A11y Rules Generation
# =============================================================================


def generate_a11y_rules() -> list[A11yRule]:
    """Generate default accessibility rules."""
    return [
        A11yRule(id="color-contrast", level="AA", enabled=True),
        A11yRule(id="label", level="A", enabled=True),
        A11yRule(id="button-name", level="A", enabled=True),
        A11yRule(id="link-name", level="A", enabled=True),
        A11yRule(id="image-alt", level="A", enabled=True),
        A11yRule(id="heading-order", level="AA", enabled=True),
        A11yRule(id="focus-visible", level="AA", enabled=True),
    ]


# =============================================================================
# Auth Flow Generation
# =============================================================================


def generate_auth_tests(
    appspec: AppSpec,
    manifest: ProjectManifest | None = None,
) -> tuple[list[FixtureSpec], list[FlowSpec]]:
    """
    Generate auth-related fixtures and flows.

    Only generates if auth is enabled in the manifest.

    Args:
        appspec: Application specification
        manifest: Optional project manifest with auth config

    Returns:
        Tuple of (fixtures, flows)
    """
    if manifest is None or not manifest.auth.enabled:
        return [], []

    # Collect protected surfaces
    protected_surfaces: list[tuple[str, str | None, SurfaceAccessSpec]] = []
    for surface in appspec.surfaces:
        if surface.access and surface.access.require_auth:
            protected_surfaces.append((surface.name, surface.title, surface.access))

    return generate_all_auth_flows(
        allow_registration=manifest.auth.allow_registration,
        protected_surfaces=protected_surfaces if protected_surfaces else None,
    )


# =============================================================================
# Main Generator
# =============================================================================


def generate_e2e_testspec(
    appspec: AppSpec,
    manifest: ProjectManifest | None = None,
) -> E2ETestSpec:
    """
    Generate a complete E2ETestSpec from an AppSpec.

    This generates:
    - Fixtures for each entity (valid and updated variants)
    - CRUD flows for each entity (create, read, update, delete)
    - Validation flows for required field constraints
    - Navigation flows for each surface
    - Auth flows (if auth enabled in manifest)
    - Default usability rules
    - Default accessibility rules

    Args:
        appspec: The application specification to generate tests from
        manifest: Optional project manifest for auth config

    Returns:
        Complete E2ETestSpec ready for test execution
    """
    fixtures: list[FixtureSpec] = []
    flows: list[FlowSpec] = []

    # Generate fixtures for each entity
    fixtures = generate_fixtures(appspec)

    # Generate CRUD flows for each entity
    for entity in appspec.domain.entities:
        flows.extend(generate_entity_crud_flows(entity, appspec))
        flows.extend(generate_validation_flows(entity, appspec))

    # Generate navigation flows for each surface
    for surface in appspec.surfaces:
        flows.extend(generate_surface_flows(surface, appspec))

    # Generate auth flows if auth is enabled
    auth_fixtures, auth_flows = generate_auth_tests(appspec, manifest)
    fixtures.extend(auth_fixtures)
    flows.extend(auth_flows)

    # Generate usability and a11y rules
    usability_rules = generate_usability_rules(appspec)
    a11y_rules = generate_a11y_rules()

    return E2ETestSpec(
        app_name=appspec.name,
        version=appspec.version,
        fixtures=fixtures,
        flows=flows,
        usability_rules=usability_rules,
        a11y_rules=a11y_rules,
        metadata={
            "generator": "dazzle.testing.testspec_generator",
            "entity_count": len(appspec.domain.entities),
            "surface_count": len(appspec.surfaces),
            "auth_enabled": manifest.auth.enabled if manifest else False,
        },
    )
