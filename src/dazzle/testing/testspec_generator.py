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
    PermissionKind,
    SurfaceAccessSpec,
    SurfaceMode,
    SurfaceSpec,
    UsabilityRule,
)
from dazzle.core.ir.computed import AggregateCall, AggregateFunction, ComputedFieldSpec
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
    valid_refs: dict[str, str] = {}
    for field in entity.fields:
        if field.is_primary_key:
            continue  # Skip auto-generated PKs
        if field.type.kind == FieldTypeKind.REF:
            # Map ref fields to their target entity's fixture
            if field.type.ref_entity:
                valid_refs[field.name] = f"{field.type.ref_entity}_valid"
            continue
        value = _generate_field_value(field)
        if value is not None:
            valid_data[field.name] = value

    fixtures.append(
        FixtureSpec(
            id=f"{entity.name}_valid",
            entity=entity.name,
            data=valid_data,
            refs=valid_refs,
            description=f"Valid {entity.name} fixture with all required fields",
        )
    )

    # State-specific fixtures for entities with state machines
    if entity.state_machine:
        sm = entity.state_machine
        status_field = sm.status_field if hasattr(sm, "status_field") else "status"
        for state in sm.states:
            state_data = valid_data.copy()
            state_data[status_field] = state
            fixtures.append(
                FixtureSpec(
                    id=f"{entity.name}_state_{state}",
                    entity=entity.name,
                    data=state_data,
                    refs=valid_refs,
                    description=f"{entity.name} fixture in '{state}' state",
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
            refs=valid_refs,  # Same refs as valid fixture
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


def _get_surface_fields(entity: EntitySpec, appspec: AppSpec, mode: SurfaceMode) -> set[str] | None:
    """
    Get the set of field names defined in the surface for an entity and mode.

    Returns:
        Set of field names if surface exists, None if no surface defined.
    """
    for surface in appspec.surfaces:
        if surface.entity_ref == entity.name and surface.mode == mode:
            if not surface.sections:
                # Surface exists but has no explicit sections — all fields visible
                return None
            field_names: set[str] = set()
            for section in surface.sections:
                for element in section.elements:
                    # field_name can be "Entity.field_name" or just "field_name"
                    if "." in element.field_name:
                        field_names.add(element.field_name.split(".", 1)[1])
                    else:
                        field_names.add(element.field_name)
            return field_names
    return None


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

    # Get surface-defined fields (if surface exists)
    surface_fields = _get_surface_fields(entity, appspec, SurfaceMode.CREATE)

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

    # Fill each form field (filtered by surface if defined)
    for field in form_fields:
        if field.type.kind == FieldTypeKind.REF:
            continue  # Skip refs for now

        # If surface defines specific fields, only fill those
        if surface_fields is not None and field.name not in surface_fields:
            continue

        steps.append(
            FlowStep(
                kind=FlowStepKind.FILL,
                target=f"field:{entity.name}.{field.name}",
                fixture_ref=f"{entity.name}_valid.{field.name}",
                description=f"Fill {field.name} field",
                field_type=field.type.kind.value,
            )
        )

    # Submit and assert (use action:Entity.save to match form template)
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
            description=f"Click on a {entity.name} row to view details",
        ),
        # Verify entity is viewable (exists in API)
        FlowStep(
            kind=FlowStepKind.ASSERT,
            assertion=FlowAssertion(
                kind=FlowAssertionKind.ENTITY_EXISTS,
                target=entity.name,
            ),
            description=f"Assert {entity.name} is accessible",
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

    # Get surface-defined fields (if surface exists)
    surface_fields = _get_surface_fields(entity, appspec, SurfaceMode.EDIT)

    # Filter form fields by surface definition
    if surface_fields is not None:
        form_fields = [f for f in form_fields if f.name in surface_fields]

    steps: list[FlowStep] = [
        FlowStep(
            kind=FlowStepKind.NAVIGATE,
            target=f"view:{list_surface}",
            description=f"Navigate to {entity.name} list",
        ),
        FlowStep(
            kind=FlowStepKind.CLICK,
            target=f"row:{entity.name}",
            description=f"Click on a {entity.name} row to view details",
        ),
        FlowStep(
            kind=FlowStepKind.CLICK,
            target=f"action:{entity.name}.edit",
            description=f"Click edit {entity.name} button",
        ),
    ]

    # Update at least one field (from surface-defined fields)
    if form_fields:
        field = form_fields[0]
        if field.type.kind != FieldTypeKind.REF:
            steps.append(
                FlowStep(
                    kind=FlowStepKind.FILL,
                    target=f"field:{entity.name}.{field.name}",
                    fixture_ref=f"{entity.name}_updated.{field.name}",
                    description=f"Update {field.name} field",
                    field_type=field.type.kind.value,
                )
            )

    steps.extend(
        [
            FlowStep(
                kind=FlowStepKind.CLICK,
                target=f"action:{entity.name}.update",
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
            target="action:confirm-delete",
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


def _has_surface_mode(entity: EntitySpec, appspec: AppSpec, mode: SurfaceMode) -> bool:
    """Check if a surface exists for this entity with the given mode."""
    for surface in appspec.surfaces:
        if surface.entity_ref == entity.name and surface.mode == mode:
            return True
    return False


def generate_entity_crud_flows(entity: EntitySpec, appspec: AppSpec) -> list[FlowSpec]:
    """Generate CRUD flows for an entity, skipping flows that require missing surfaces."""
    flows: list[FlowSpec] = []

    # Create flow requires a CREATE surface (or LIST with create action)
    if _has_surface_mode(entity, appspec, SurfaceMode.CREATE) or _has_surface_mode(
        entity, appspec, SurfaceMode.LIST
    ):
        flows.append(generate_create_flow(entity, appspec))

    # View flow requires a VIEW surface
    if _has_surface_mode(entity, appspec, SurfaceMode.VIEW):
        flows.append(generate_view_flow(entity, appspec))

    # Update flow requires an EDIT surface
    if _has_surface_mode(entity, appspec, SurfaceMode.EDIT):
        flows.append(generate_update_flow(entity, appspec))

    # Delete flow requires a LIST surface (for the delete button)
    if _has_surface_mode(entity, appspec, SurfaceMode.LIST):
        flows.append(generate_delete_flow(entity, appspec))

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
                target=f"action:{entity.name}.create",
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
# State Machine Transition Flow Generation (v0.13.0)
# =============================================================================


def generate_state_machine_flows(entity: EntitySpec, appspec: AppSpec) -> list[FlowSpec]:
    """
    Generate state machine transition test flows for an entity.

    Tests:
    - Valid transitions (status changes that should succeed)
    - Invalid transitions (status changes that should be blocked)
    - Guard condition enforcement (requires_field, requires_role)

    Args:
        entity: Entity with state machine
        appspec: Full application spec

    Returns:
        List of flow specs for state machine tests
    """
    if not entity.state_machine:
        return []

    flows: list[FlowSpec] = []
    sm = entity.state_machine
    list_surface = _get_list_surface_name(entity, appspec)

    # Generate tests for each explicit transition
    for transition in sm.transitions:
        # Skip transitions with role guards — E2E tests have no auth context
        if any(g.requires_role for g in transition.guards):
            continue
        if transition.is_wildcard:
            # For wildcard transitions, pick first non-target state as example
            example_states = [s for s in sm.states if s != transition.to_state]
            from_states = example_states[:1] if example_states else []
        else:
            from_states = [transition.from_state]

        for from_state in from_states:
            # Test valid transition
            steps: list[FlowStep] = [
                FlowStep(
                    kind=FlowStepKind.NAVIGATE,
                    target=f"view:{list_surface}",
                    description=f"Navigate to {entity.name} list",
                ),
                FlowStep(
                    kind=FlowStepKind.CLICK,
                    target=f"row:{entity.name}",
                    description=f"Select {entity.name} in state '{from_state}'",
                ),
                FlowStep(
                    kind=FlowStepKind.CLICK,
                    target=f"action:{entity.name}.transition.{transition.to_state}",
                    description=f"Trigger transition to '{transition.to_state}'",
                ),
            ]

            # Guard satisfaction: requires_field guards are satisfied by ensuring
            # the fixture has the field populated (checked server-side).
            # HTMX transition buttons send hx-put directly, so there's no form
            # to fill guard fields in the UI.

            steps.append(
                FlowStep(
                    kind=FlowStepKind.ASSERT,
                    assertion=FlowAssertion(
                        kind=FlowAssertionKind.STATE_TRANSITION_ALLOWED,
                        target=f"{entity.name}.{sm.status_field}",
                        expected=transition.to_state,
                    ),
                    description=f"Assert transition to '{transition.to_state}' succeeded",
                )
            )

            flow_id = f"{entity.name}_transition_{from_state}_to_{transition.to_state}"
            flows.append(
                FlowSpec(
                    id=flow_id,
                    description=f"Valid transition: {entity.name} from '{from_state}' to '{transition.to_state}'",
                    priority=FlowPriority.HIGH,
                    preconditions=FlowPrecondition(
                        fixtures=[f"{entity.name}_state_{from_state}"],
                    ),
                    steps=steps,
                    tags=["state_machine", "transition", entity.name.lower()],
                    entity=entity.name,
                    auto_generated=True,
                )
            )

    # Generate tests for INVALID transitions (not in allowed list)
    for from_state in sm.states:
        allowed_targets = sm.get_allowed_targets(from_state)
        invalid_targets = set(sm.states) - allowed_targets - {from_state}

        for invalid_target in list(invalid_targets)[:1]:  # Just one example per state
            steps = [
                FlowStep(
                    kind=FlowStepKind.NAVIGATE,
                    target=f"view:{list_surface}",
                    description=f"Navigate to {entity.name} list",
                ),
                FlowStep(
                    kind=FlowStepKind.CLICK,
                    target=f"row:{entity.name}",
                    description=f"Select {entity.name} in state '{from_state}'",
                ),
                FlowStep(
                    kind=FlowStepKind.CLICK,
                    target=f"action:{entity.name}.transition.{invalid_target}",
                    description=f"Attempt invalid transition to '{invalid_target}'",
                ),
                FlowStep(
                    kind=FlowStepKind.ASSERT,
                    assertion=FlowAssertion(
                        kind=FlowAssertionKind.STATE_TRANSITION_BLOCKED,
                        target=f"{entity.name}.{sm.status_field}",
                        expected=from_state,  # Should remain in original state
                    ),
                    description=f"Assert transition was blocked, status remains '{from_state}'",
                ),
            ]

            flow_id = f"{entity.name}_transition_invalid_{from_state}_to_{invalid_target}"
            flows.append(
                FlowSpec(
                    id=flow_id,
                    description=f"Invalid transition: {entity.name} cannot go from '{from_state}' to '{invalid_target}'",
                    priority=FlowPriority.MEDIUM,
                    preconditions=FlowPrecondition(
                        fixtures=[f"{entity.name}_state_{from_state}"],
                    ),
                    steps=steps,
                    tags=["state_machine", "invalid_transition", entity.name.lower()],
                    entity=entity.name,
                    auto_generated=True,
                )
            )

    return flows


# =============================================================================
# Computed Field Verification Flow Generation (v0.13.0)
# =============================================================================


def _get_expected_computed_value(computed: ComputedFieldSpec) -> str | int | float:
    """Generate expected value for a computed field based on its expression."""
    expr = computed.expression

    # For aggregates on empty data, return sensible defaults
    if isinstance(expr, AggregateCall):
        if expr.function == AggregateFunction.COUNT:
            return 0
        elif expr.function in (AggregateFunction.SUM, AggregateFunction.AVG):
            return 0
        elif expr.function == AggregateFunction.DAYS_UNTIL:
            return 0  # Placeholder
        elif expr.function == AggregateFunction.DAYS_SINCE:
            return 0  # Placeholder
        else:
            return 0

    # For field references and arithmetic, use placeholder
    return "computed"


def generate_computed_field_flows(entity: EntitySpec, appspec: AppSpec) -> list[FlowSpec]:
    """
    Generate computed field verification test flows for an entity.

    Tests that computed fields calculate correctly based on their
    expressions (count, sum, avg, etc.).

    Args:
        entity: Entity with computed fields
        appspec: Full application spec

    Returns:
        List of flow specs for computed field tests
    """
    if not entity.computed_fields:
        return []

    flows: list[FlowSpec] = []
    list_surface = _get_list_surface_name(entity, appspec)

    for computed in entity.computed_fields:
        expected = _get_expected_computed_value(computed)

        steps: list[FlowStep] = [
            FlowStep(
                kind=FlowStepKind.NAVIGATE,
                target=f"view:{list_surface}",
                description=f"Navigate to {entity.name} list",
            ),
            FlowStep(
                kind=FlowStepKind.CLICK,
                target=f"row:{entity.name}",
                description=f"Select {entity.name} to view details",
            ),
            FlowStep(
                kind=FlowStepKind.ASSERT,
                assertion=FlowAssertion(
                    kind=FlowAssertionKind.VISIBLE,
                    target=f"field:{entity.name}.{computed.name}",
                ),
                description=f"Assert computed field '{computed.name}' is visible",
            ),
            FlowStep(
                kind=FlowStepKind.ASSERT,
                assertion=FlowAssertion(
                    kind=FlowAssertionKind.COMPUTED_VALUE,
                    target=f"field:{entity.name}.{computed.name}",
                    expected=expected,
                ),
                description=f"Assert computed field '{computed.name}' has expected value",
            ),
        ]

        flow_id = f"{entity.name}_computed_{computed.name}"
        flows.append(
            FlowSpec(
                id=flow_id,
                description=f"Verify computed field '{computed.name}' on {entity.name}",
                priority=FlowPriority.MEDIUM,
                preconditions=FlowPrecondition(fixtures=[f"{entity.name}_valid"]),
                steps=steps,
                tags=["computed", entity.name.lower()],
                entity=entity.name,
                auto_generated=True,
            )
        )

    return flows


# =============================================================================
# Access Control Flow Generation (v0.13.0)
# =============================================================================


def generate_access_control_flows(entity: EntitySpec, appspec: AppSpec) -> list[FlowSpec]:
    """
    Generate access control test flows for an entity.

    Tests that permissions are enforced correctly:
    - Create permission (who can create)
    - Update permission (who can update)
    - Delete permission (who can delete)

    Args:
        entity: Entity with access spec
        appspec: Full application spec

    Returns:
        List of flow specs for access control tests
    """
    if not entity.access:
        return []

    # Skip if entity has no surfaces (can't test UI access without surfaces)
    if not _has_surface_mode(entity, appspec, SurfaceMode.LIST):
        return []

    flows: list[FlowSpec] = []
    list_surface = _get_list_surface_name(entity, appspec)

    # Map permission kinds to actions
    permission_actions = {
        PermissionKind.CREATE: ("create", f"action:{entity.name}.create"),
        PermissionKind.UPDATE: ("update", f"action:{entity.name}.edit"),
        PermissionKind.DELETE: ("delete", f"action:{entity.name}.delete"),
    }

    for perm in entity.access.permissions:
        action_name, action_target = permission_actions.get(
            perm.operation, (perm.operation.value, f"action:{entity.name}.{perm.operation.value}")
        )

        # Test: Authenticated user CAN perform operation (if allowed)
        if perm.require_auth:
            steps: list[FlowStep] = [
                FlowStep(
                    kind=FlowStepKind.NAVIGATE,
                    target=f"view:{list_surface}",
                    description=f"Navigate to {entity.name} list as authenticated user",
                ),
            ]

            if perm.operation == PermissionKind.CREATE:
                steps.append(
                    FlowStep(
                        kind=FlowStepKind.CLICK,
                        target=action_target,
                        description=f"Click {action_name} button",
                    )
                )
                steps.append(
                    FlowStep(
                        kind=FlowStepKind.ASSERT,
                        assertion=FlowAssertion(
                            kind=FlowAssertionKind.PERMISSION_GRANTED,
                            target=f"{entity.name}.{action_name}",
                        ),
                        description=f"Assert {action_name} form is accessible",
                    )
                )
            else:
                # Update/Delete need existing entity
                steps.append(
                    FlowStep(
                        kind=FlowStepKind.CLICK,
                        target=f"row:{entity.name}",
                        description=f"Select {entity.name}",
                    )
                )
                steps.append(
                    FlowStep(
                        kind=FlowStepKind.CLICK,
                        target=action_target,
                        description=f"Click {action_name} button",
                    )
                )
                steps.append(
                    FlowStep(
                        kind=FlowStepKind.ASSERT,
                        assertion=FlowAssertion(
                            kind=FlowAssertionKind.PERMISSION_GRANTED,
                            target=f"{entity.name}.{action_name}",
                        ),
                        description=f"Assert {action_name} is allowed",
                    )
                )

            flow_id = f"{entity.name}_access_{action_name}_allowed"
            flows.append(
                FlowSpec(
                    id=flow_id,
                    description=f"Authenticated user can {action_name} {entity.name}",
                    priority=FlowPriority.HIGH,
                    preconditions=FlowPrecondition(
                        authenticated=True,
                        fixtures=[f"{entity.name}_valid"]
                        if perm.operation != PermissionKind.CREATE
                        else [],
                    ),
                    steps=steps,
                    tags=["access_control", action_name, entity.name.lower()],
                    entity=entity.name,
                    auto_generated=True,
                )
            )

            # Test: Anonymous user CANNOT perform operation (if auth required)
            anon_steps: list[FlowStep] = [
                FlowStep(
                    kind=FlowStepKind.NAVIGATE,
                    target=f"view:{list_surface}",
                    description=f"Navigate to {entity.name} list as anonymous user",
                ),
                FlowStep(
                    kind=FlowStepKind.CLICK,
                    target=action_target,
                    description=f"Attempt {action_name} without authentication",
                ),
                FlowStep(
                    kind=FlowStepKind.ASSERT,
                    assertion=FlowAssertion(
                        kind=FlowAssertionKind.PERMISSION_DENIED,
                        target=f"{entity.name}.{action_name}",
                    ),
                    description=f"Assert {action_name} is denied for anonymous user",
                ),
            ]

            anon_flow_id = f"{entity.name}_access_{action_name}_denied_anon"
            flows.append(
                FlowSpec(
                    id=anon_flow_id,
                    description=f"Anonymous user cannot {action_name} {entity.name}",
                    priority=FlowPriority.MEDIUM,
                    preconditions=FlowPrecondition(
                        authenticated=False,
                        fixtures=[f"{entity.name}_valid"]
                        if perm.operation != PermissionKind.CREATE
                        else [],
                    ),
                    steps=anon_steps,
                    tags=["access_control", "denied", entity.name.lower()],
                    entity=entity.name,
                    auto_generated=True,
                )
            )

    return flows


# =============================================================================
# Reference Integrity Flow Generation (v0.13.0)
# =============================================================================


def generate_reference_flows(entity: EntitySpec, appspec: AppSpec) -> list[FlowSpec]:
    """
    Generate reference integrity test flows for an entity.

    Tests that ref fields:
    - Accept valid references to existing entities
    - Reject invalid references (non-existent foreign keys)

    Args:
        entity: Entity with ref fields
        appspec: Full application spec

    Returns:
        List of flow specs for reference integrity tests
    """
    flows: list[FlowSpec] = []

    # Skip if entity has no LIST or CREATE surfaces (can't test refs without UI)
    if not _has_surface_mode(entity, appspec, SurfaceMode.LIST):
        return []
    if not _has_surface_mode(entity, appspec, SurfaceMode.CREATE):
        return []

    list_surface = _get_list_surface_name(entity, appspec)

    # Find ref fields visible on the create surface
    ref_fields = [f for f in entity.fields if f.type.kind == FieldTypeKind.REF]
    create_surface_fields = _get_surface_fields(entity, appspec, SurfaceMode.CREATE)
    if create_surface_fields is not None:
        ref_fields = [f for f in ref_fields if f.name in create_surface_fields]

    if not ref_fields:
        return []

    for ref_field in ref_fields:
        ref_target = ref_field.type.ref_entity
        if not ref_target:
            continue

        # Test: Create with valid reference
        valid_steps: list[FlowStep] = [
            FlowStep(
                kind=FlowStepKind.NAVIGATE,
                target=f"view:{list_surface}",
                description=f"Navigate to {entity.name} list",
            ),
            FlowStep(
                kind=FlowStepKind.CLICK,
                target=f"action:{entity.name}.create",
                description=f"Click create {entity.name}",
            ),
            FlowStep(
                kind=FlowStepKind.FILL,
                target=f"field:{entity.name}.{ref_field.name}",
                fixture_ref=f"{ref_target}_valid.id",
                description=f"Select valid {ref_target} reference",
                field_type="ref",
            ),
        ]

        # Fill other required fields
        for field in _get_required_fields(entity):
            if field.name != ref_field.name and field.type.kind != FieldTypeKind.REF:
                valid_steps.append(
                    FlowStep(
                        kind=FlowStepKind.FILL,
                        target=f"field:{entity.name}.{field.name}",
                        fixture_ref=f"{entity.name}_valid.{field.name}",
                        description=f"Fill {field.name}",
                        field_type=field.type.kind.value,
                    )
                )

        valid_steps.extend(
            [
                FlowStep(
                    kind=FlowStepKind.CLICK,
                    target=f"action:{entity.name}.save",
                    description="Save entity",
                ),
                FlowStep(
                    kind=FlowStepKind.ASSERT,
                    assertion=FlowAssertion(
                        kind=FlowAssertionKind.REF_VALID,
                        target=f"{entity.name}.{ref_field.name}",
                    ),
                    description=f"Assert {ref_field.name} reference is valid",
                ),
            ]
        )

        valid_flow_id = f"{entity.name}_ref_{ref_field.name}_valid"
        flows.append(
            FlowSpec(
                id=valid_flow_id,
                description=f"Create {entity.name} with valid {ref_field.name} reference",
                priority=FlowPriority.HIGH,
                preconditions=FlowPrecondition(
                    fixtures=[f"{ref_target}_valid", f"{entity.name}_valid"]
                ),
                steps=valid_steps,
                tags=["reference", "valid", entity.name.lower()],
                entity=entity.name,
                auto_generated=True,
            )
        )

        # Test: Create with invalid reference (non-existent ID)
        invalid_steps: list[FlowStep] = [
            FlowStep(
                kind=FlowStepKind.NAVIGATE,
                target=f"view:{list_surface}",
                description=f"Navigate to {entity.name} list",
            ),
            FlowStep(
                kind=FlowStepKind.CLICK,
                target=f"action:{entity.name}.create",
                description=f"Click create {entity.name}",
            ),
            FlowStep(
                kind=FlowStepKind.FILL,
                target=f"field:{entity.name}.{ref_field.name}",
                value="00000000-0000-0000-0000-000000000000",  # Non-existent UUID
                description=f"Enter invalid {ref_target} reference",
                field_type="ref",
            ),
        ]

        # Fill other required fields
        for field in _get_required_fields(entity):
            if field.name != ref_field.name and field.type.kind != FieldTypeKind.REF:
                invalid_steps.append(
                    FlowStep(
                        kind=FlowStepKind.FILL,
                        target=f"field:{entity.name}.{field.name}",
                        fixture_ref=f"{entity.name}_valid.{field.name}",
                        description=f"Fill {field.name}",
                        field_type=field.type.kind.value,
                    )
                )

        invalid_steps.extend(
            [
                FlowStep(
                    kind=FlowStepKind.CLICK,
                    target=f"action:{entity.name}.save",
                    description="Attempt to save with invalid reference",
                ),
                FlowStep(
                    kind=FlowStepKind.ASSERT,
                    assertion=FlowAssertion(
                        kind=FlowAssertionKind.REF_INVALID,
                        target=f"{entity.name}.{ref_field.name}",
                    ),
                    description=f"Assert {ref_field.name} reference validation failed",
                ),
            ]
        )

        invalid_flow_id = f"{entity.name}_ref_{ref_field.name}_invalid"
        flows.append(
            FlowSpec(
                id=invalid_flow_id,
                description=f"Create {entity.name} with invalid {ref_field.name} reference fails",
                priority=FlowPriority.MEDIUM,
                preconditions=FlowPrecondition(fixtures=[f"{entity.name}_valid"]),
                steps=invalid_steps,
                tags=["reference", "invalid", entity.name.lower()],
                entity=entity.name,
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
    - State machine transition flows (valid/invalid transitions) [v0.13.0]
    - Computed field verification flows [v0.13.0]
    - Access control flows (permission granted/denied) [v0.13.0]
    - Reference integrity flows (valid/invalid refs) [v0.13.0]
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

    # Generate v0.13.0 flows: state machines, computed fields, access control, references
    for entity in appspec.domain.entities:
        flows.extend(generate_state_machine_flows(entity, appspec))
        flows.extend(generate_computed_field_flows(entity, appspec))
        flows.extend(generate_access_control_flows(entity, appspec))
        flows.extend(generate_reference_flows(entity, appspec))

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
