"""
Surface converter - converts Dazzle IR SurfaceSpec to DNR UISpec ComponentSpec.

This module transforms Dazzle's surface definitions into DNR UI components,
mapping surface modes to appropriate UI patterns.
"""

from dazzle.core import ir
from dazzle_dnr_ui.specs import (
    ActionSpec,
    ComponentSpec,
    ElementNode,
    FetchEffect,
    LiteralBinding,
    NavigateEffect,
    PropFieldSpec,
    PropsSchema,
    StateScope,
    StateSpec,
)

# =============================================================================
# Component Type Inference
# =============================================================================


def _surface_mode_to_component(mode: ir.SurfaceMode) -> str:
    """Map surface mode to appropriate DNR pattern component."""
    mode_map = {
        ir.SurfaceMode.LIST: "FilterableTable",
        ir.SurfaceMode.VIEW: "Card",
        ir.SurfaceMode.CREATE: "Form",
        ir.SurfaceMode.EDIT: "Form",
        ir.SurfaceMode.CUSTOM: "Page",
    }
    return mode_map.get(mode, "Page")


def _generate_component_name(surface: ir.SurfaceSpec) -> str:
    """Generate a PascalCase component name from surface."""
    # Convert snake_case to PascalCase
    parts = surface.name.split("_")
    return "".join(part.title() for part in parts)


# =============================================================================
# Props Schema Generation
# =============================================================================


def _generate_props_schema(
    surface: ir.SurfaceSpec,
    entity: ir.EntitySpec | None,
) -> PropsSchema:
    """Generate props schema based on surface mode and entity."""
    fields: list[PropFieldSpec] = []

    if surface.mode == ir.SurfaceMode.LIST:
        # List needs data source
        fields.extend(
            [
                PropFieldSpec(name="items", type=f"list[{surface.entity_ref}]", required=True),
                PropFieldSpec(name="loading", type="bool", required=False, default=False),
                PropFieldSpec(name="onRowClick", type="Action", required=False),
            ]
        )

    elif surface.mode == ir.SurfaceMode.VIEW:
        # View needs entity data
        fields.extend(
            [
                PropFieldSpec(
                    name=surface.entity_ref.lower() if surface.entity_ref else "item",
                    type=surface.entity_ref or "object",
                    required=True,
                ),
            ]
        )

    elif surface.mode in (ir.SurfaceMode.CREATE, ir.SurfaceMode.EDIT):
        # Forms need submit handler
        fields.extend(
            [
                PropFieldSpec(name="onSubmit", type="Action", required=True),
                PropFieldSpec(name="onCancel", type="Action", required=False),
            ]
        )

        if surface.mode == ir.SurfaceMode.EDIT:
            fields.append(
                PropFieldSpec(
                    name="initialValues", type=surface.entity_ref or "object", required=True
                )
            )

    return PropsSchema(fields=fields)


# =============================================================================
# Actions Generation
# =============================================================================


def _generate_actions(
    surface: ir.SurfaceSpec,
) -> list[ActionSpec]:
    """Generate actions based on surface mode and UX spec."""
    actions: list[ActionSpec] = []

    # Standard CRUD actions
    if surface.mode == ir.SurfaceMode.LIST:
        # Navigation to detail/edit
        actions.append(
            ActionSpec(
                name="viewItem",
                description="Navigate to item detail",
                inputs={"id": "uuid"},
                effect=NavigateEffect(
                    route=f"/{surface.entity_ref.lower() if surface.entity_ref else 'item'}/{{id}}",
                ),
            )
        )

    elif surface.mode == ir.SurfaceMode.CREATE:
        actions.append(
            ActionSpec(
                name="submitCreate",
                description=f"Create new {surface.entity_ref or 'item'}",
                effect=FetchEffect(
                    backend_service=f"create_{surface.entity_ref.lower() if surface.entity_ref else 'item'}",
                    on_success="onCreateSuccess",
                    on_error="onCreateError",
                ),
            )
        )
        actions.append(
            ActionSpec(
                name="onCreateSuccess",
                description="Handle successful creation",
                effect=NavigateEffect(route="/"),
            )
        )

    elif surface.mode == ir.SurfaceMode.EDIT:
        actions.append(
            ActionSpec(
                name="submitEdit",
                description=f"Update {surface.entity_ref or 'item'}",
                effect=FetchEffect(
                    backend_service=f"update_{surface.entity_ref.lower() if surface.entity_ref else 'item'}",
                    on_success="onUpdateSuccess",
                    on_error="onUpdateError",
                ),
            )
        )
        actions.append(
            ActionSpec(
                name="onUpdateSuccess",
                description="Handle successful update",
                effect=NavigateEffect(route="/"),
            )
        )

    # Add actions from surface definition
    for surface_action in surface.actions:
        actions.append(
            ActionSpec(
                name=surface_action.name,
                description=surface_action.label,
                # Effect would be inferred from outcome
            )
        )

    return actions


# =============================================================================
# State Generation
# =============================================================================


def _generate_state(
    surface: ir.SurfaceSpec,
) -> list[StateSpec]:
    """Generate component state based on surface mode."""
    state: list[StateSpec] = []

    if surface.mode == ir.SurfaceMode.LIST:
        # List state
        state.extend(
            [
                StateSpec(name="items", scope=StateScope.LOCAL, initial=[]),
                StateSpec(name="loading", scope=StateScope.LOCAL, initial=True),
                StateSpec(name="selectedId", scope=StateScope.LOCAL, initial=None),
            ]
        )

        # Filter state if UX spec has filters
        if surface.ux and surface.ux.filter:
            state.append(StateSpec(name="filters", scope=StateScope.LOCAL, initial={}))

    elif surface.mode in (ir.SurfaceMode.CREATE, ir.SurfaceMode.EDIT):
        # Form state
        state.extend(
            [
                StateSpec(name="formData", scope=StateScope.LOCAL, initial={}),
                StateSpec(name="errors", scope=StateScope.LOCAL, initial={}),
                StateSpec(name="submitting", scope=StateScope.LOCAL, initial=False),
            ]
        )

    elif surface.mode == ir.SurfaceMode.VIEW:
        # Detail view state
        state.extend(
            [
                StateSpec(name="loading", scope=StateScope.LOCAL, initial=True),
            ]
        )

    return state


# =============================================================================
# View Generation
# =============================================================================


def _generate_view(
    surface: ir.SurfaceSpec,
    entity: ir.EntitySpec | None,
) -> ElementNode:
    """Generate a basic view tree for the surface."""
    component_type = _surface_mode_to_component(surface.mode)

    if surface.mode == ir.SurfaceMode.LIST:
        # Generate table columns from surface sections
        return ElementNode(
            as_=component_type,
            props={
                "title": LiteralBinding(value=surface.title or surface.name),
            },
        )

    elif surface.mode == ir.SurfaceMode.VIEW:
        return ElementNode(
            as_="Card",
            props={
                "title": LiteralBinding(value=surface.title or surface.name),
            },
        )

    elif surface.mode in (ir.SurfaceMode.CREATE, ir.SurfaceMode.EDIT):
        return ElementNode(
            as_="Form",
            props={
                "title": LiteralBinding(value=surface.title or surface.name),
            },
        )

    else:
        return ElementNode(
            as_="Page",
            props={
                "title": LiteralBinding(value=surface.title or surface.name),
            },
        )


# =============================================================================
# Surface Conversion
# =============================================================================


def convert_surface_to_component(
    surface: ir.SurfaceSpec,
    entity: ir.EntitySpec | None = None,
) -> ComponentSpec:
    """
    Convert a Dazzle IR SurfaceSpec to DNR UISpec ComponentSpec.

    Args:
        surface: Dazzle IR surface specification
        entity: Optional entity specification for type inference

    Returns:
        DNR UISpec component specification
    """
    return ComponentSpec(
        name=_generate_component_name(surface),
        description=surface.title,
        category="custom",
        props_schema=_generate_props_schema(surface, entity),
        view=_generate_view(surface, entity),
        state=_generate_state(surface),
        actions=_generate_actions(surface),
    )


def convert_surfaces_to_components(
    surfaces: list[ir.SurfaceSpec],
    domain: ir.DomainSpec | None = None,
) -> list[ComponentSpec]:
    """
    Convert a list of Dazzle IR surfaces to DNR UISpec components.

    Args:
        surfaces: List of Dazzle IR surface specifications
        domain: Optional domain spec for entity lookup

    Returns:
        List of DNR UISpec component specifications
    """
    components: list[ComponentSpec] = []

    for surface in surfaces:
        entity = None
        if domain and surface.entity_ref:
            entity = domain.get_entity(surface.entity_ref)

        components.append(convert_surface_to_component(surface, entity))

    return components
