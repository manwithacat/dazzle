"""
Surface converter - converts Dazzle IR SurfaceSpec to DNR UISpec ComponentSpec.

This module transforms Dazzle's surface definitions into DNR UI components,
mapping surface modes to appropriate UI patterns.
"""

from dazzle.core import ir
from dazzle.core.strings import to_api_plural
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
    TextNode,
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


def _generate_dazzle_attrs(
    surface: ir.SurfaceSpec,
    entity: ir.EntitySpec | None,
) -> dict:
    """Generate semantic dazzle attributes for the surface."""
    entity_name = entity.name if entity else surface.entity_ref
    mode_map = {
        ir.SurfaceMode.LIST: "list",
        ir.SurfaceMode.VIEW: "detail",
        ir.SurfaceMode.CREATE: "create",
        ir.SurfaceMode.EDIT: "edit",
        ir.SurfaceMode.CUSTOM: "custom",
    }
    mode_suffix = mode_map.get(surface.mode, "custom")
    view_name = f"{entity_name.lower()}_{mode_suffix}" if entity_name else surface.name

    return {
        "view": view_name,
        "entity": entity_name,
        "formMode": mode_suffix
        if surface.mode in (ir.SurfaceMode.CREATE, ir.SurfaceMode.EDIT)
        else None,
    }


def _get_field_spec(entity: ir.EntitySpec | None, field_name: str) -> ir.FieldSpec | None:
    """Look up a field spec from an entity by name."""
    if not entity or not entity.fields:
        return None
    for field in entity.fields:
        if field.name == field_name:
            return field
    return None


def _generate_field_element(
    field_name: str,
    field_label: str,
    field_spec: ir.FieldSpec | None,
    entity_name: str | None,
) -> ElementNode:
    """
    Generate the appropriate input element based on field type.

    Returns an Input, Select, or Checkbox component based on the field's type.
    """
    dazzle_attrs = {
        "field": f"{entity_name}.{field_name}" if entity_name else field_name,
        "entity": entity_name,
    }

    # Determine the field type
    if field_spec and field_spec.type:
        field_type = field_spec.type
        type_kind = field_type.kind.value if field_type.kind else "str"

        # Handle enum fields -> Select component
        if type_kind == "enum" and field_type.enum_values:
            return ElementNode(
                as_="Select",
                props={
                    "placeholder": LiteralBinding(value=f"Select {field_label}"),
                    "options": LiteralBinding(value=field_type.enum_values),
                    "dazzle": LiteralBinding(value=dazzle_attrs),
                },
            )

        # Handle boolean fields -> Checkbox component
        if type_kind == "bool":
            return ElementNode(
                as_="Checkbox",
                props={
                    "label": LiteralBinding(value=field_label),
                    "dazzle": LiteralBinding(value=dazzle_attrs),
                },
            )

        # Handle date/datetime fields -> Input with type
        if type_kind == "date":
            return ElementNode(
                as_="Input",
                props={
                    "fieldType": LiteralBinding(value="date"),
                    "placeholder": LiteralBinding(value=field_label),
                    "dazzle": LiteralBinding(value=dazzle_attrs),
                },
            )

        if type_kind == "datetime":
            return ElementNode(
                as_="Input",
                props={
                    "fieldType": LiteralBinding(value="datetime"),
                    "placeholder": LiteralBinding(value=field_label),
                    "dazzle": LiteralBinding(value=dazzle_attrs),
                },
            )

        # Handle numeric fields
        if type_kind in ("int", "float", "decimal"):
            return ElementNode(
                as_="Input",
                props={
                    "fieldType": LiteralBinding(value=type_kind),
                    "placeholder": LiteralBinding(value=field_label),
                    "dazzle": LiteralBinding(value=dazzle_attrs),
                },
            )

        # Handle text fields (multiline)
        if type_kind == "text":
            return ElementNode(
                as_="Input",
                props={
                    "fieldType": LiteralBinding(value="text"),
                    "multiline": LiteralBinding(value=True),
                    "placeholder": LiteralBinding(value=field_label),
                    "dazzle": LiteralBinding(value=dazzle_attrs),
                },
            )

    # Default: standard text input
    return ElementNode(
        as_="Input",
        props={
            "placeholder": LiteralBinding(value=field_label),
            "dazzle": LiteralBinding(value=dazzle_attrs),
        },
    )


def _generate_form_fields(
    surface: ir.SurfaceSpec,
    entity: ir.EntitySpec | None,
) -> list[ElementNode]:
    """Generate form field children for a form surface."""
    children: list[ElementNode] = []
    entity_name = entity.name if entity else surface.entity_ref

    # Collect fields to render: (field_name, label, field_spec)
    fields_to_render: list[tuple[str, str, ir.FieldSpec | None]] = []

    if surface.sections:
        for section in surface.sections:
            for element in section.elements:
                field_spec = _get_field_spec(entity, element.field_name)
                label = element.label or element.field_name.replace("_", " ").title()
                fields_to_render.append((element.field_name, label, field_spec))
    elif entity and entity.fields:
        # Use all non-pk entity fields
        for field in entity.fields:
            if not field.is_primary_key:
                label = field.name.replace("_", " ").title()
                fields_to_render.append((field.name, label, field))

    # Generate form groups for each field
    for field_name, field_label, field_spec in fields_to_render:
        # For checkbox/boolean fields, the label is inline with the component
        is_checkbox = (
            field_spec and field_spec.type and field_spec.type.kind == ir.FieldTypeKind.BOOL
        )

        if is_checkbox:
            # Checkbox has built-in label
            children.append(
                _generate_field_element(field_name, field_label, field_spec, entity_name)
            )
        else:
            # Create label element
            children.append(
                ElementNode(
                    as_="Text",
                    props={
                        "variant": LiteralBinding(value="label"),
                        "dazzle": LiteralBinding(value={"label": f"{entity_name}.{field_name}"}),
                    },
                    children=[TextNode(content=LiteralBinding(value=field_label))],
                )
            )
            # Create appropriate input element
            children.append(
                _generate_field_element(field_name, field_label, field_spec, entity_name)
            )

    return children


def _generate_table_columns(
    surface: ir.SurfaceSpec,
    entity: ir.EntitySpec | None,
) -> list[dict]:
    """
    Generate column definitions for a list surface.

    Returns a list of column configs: [{"key": "field_name", "label": "Field Label"}, ...]
    """
    columns: list[dict] = []

    # Get columns from surface sections, or entity fields if not defined
    if surface.sections:
        for section in surface.sections:
            for element in section.elements:
                columns.append(
                    {
                        "key": element.field_name,
                        "label": element.label or element.field_name.replace("_", " ").title(),
                    }
                )
    elif entity and entity.fields:
        # Use all non-pk entity fields as columns
        for field in entity.fields:
            if not field.is_primary_key:
                columns.append(
                    {
                        "key": field.name,
                        "label": field.name.replace("_", " ").title(),
                    }
                )

    return columns


def _generate_form_actions(
    surface: ir.SurfaceSpec,
    entity: ir.EntitySpec | None,
) -> list[ElementNode]:
    """Generate form action buttons (Save/Cancel)."""
    entity_name = entity.name if entity else surface.entity_ref
    mode = "create" if surface.mode == ir.SurfaceMode.CREATE else "update"
    action_name = f"{entity_name}.{mode}" if entity_name else mode

    children: list[ElementNode] = []

    # Action buttons container (horizontal stack)
    action_children: list[ElementNode] = []

    # Save/Submit button
    action_children.append(
        ElementNode(
            as_="Button",
            props={
                "variant": LiteralBinding(value="primary"),
                "type": LiteralBinding(value="submit"),
                "label": LiteralBinding(value="Save" if mode == "update" else "Create"),
                "dazzle": LiteralBinding(
                    value={
                        "action": action_name,
                        "actionRole": "primary",
                    }
                ),
            },
        )
    )

    # Cancel button
    action_children.append(
        ElementNode(
            as_="Button",
            props={
                "variant": LiteralBinding(value="secondary"),
                "type": LiteralBinding(value="button"),
                "label": LiteralBinding(value="Cancel"),
                "dazzle": LiteralBinding(
                    value={
                        "action": f"{entity_name}.cancel" if entity_name else "cancel",
                        "actionRole": "cancel",
                    }
                ),
            },
        )
    )

    # Wrap in Stack
    children.append(
        ElementNode(
            as_="Stack",
            props={
                "direction": LiteralBinding(value="row"),
                "gap": LiteralBinding(value="sm"),
            },
            children=action_children,
        )
    )

    return children


def _generate_view(
    surface: ir.SurfaceSpec,
    entity: ir.EntitySpec | None,
) -> ElementNode:
    """Generate a basic view tree for the surface."""
    component_type = _surface_mode_to_component(surface.mode)
    dazzle_attrs = _generate_dazzle_attrs(surface, entity)

    if surface.mode == ir.SurfaceMode.LIST:
        # Generate table columns from surface sections or entity fields
        columns = _generate_table_columns(surface, entity)
        entity_name = dazzle_attrs.get("entity") or surface.entity_ref
        api_endpoint = f"/{to_api_plural(entity_name)}" if entity_name else None

        return ElementNode(
            as_=component_type,
            props={
                "title": LiteralBinding(value=surface.title or surface.name),
                "entity": LiteralBinding(value=entity_name),
                "columns": LiteralBinding(value=columns),
                "apiEndpoint": LiteralBinding(value=api_endpoint),
                "dazzle": LiteralBinding(value=dazzle_attrs),
            },
        )

    elif surface.mode == ir.SurfaceMode.VIEW:
        return ElementNode(
            as_="Card",
            props={
                "title": LiteralBinding(value=surface.title or surface.name),
                "dazzle": LiteralBinding(value=dazzle_attrs),
            },
        )

    elif surface.mode in (ir.SurfaceMode.CREATE, ir.SurfaceMode.EDIT):
        # Generate form with field inputs and action buttons
        form_fields = _generate_form_fields(surface, entity)
        form_actions = _generate_form_actions(surface, entity)

        return ElementNode(
            as_="Form",
            props={
                "title": LiteralBinding(value=surface.title or surface.name),
                "entity": LiteralBinding(value=dazzle_attrs.get("entity")),
                "mode": LiteralBinding(value=dazzle_attrs.get("formMode")),
                "dazzle": LiteralBinding(value=dazzle_attrs),
            },
            children=form_fields + form_actions,
        )

    else:
        return ElementNode(
            as_="Page",
            props={
                "title": LiteralBinding(value=surface.title or surface.name),
                "dazzle": LiteralBinding(value=dazzle_attrs),
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
    dazzle_attrs = _generate_dazzle_attrs(surface, entity)

    return ComponentSpec(
        name=_generate_component_name(surface),
        description=surface.title,
        category="custom",
        props_schema=_generate_props_schema(surface, entity),
        view=_generate_view(surface, entity),
        state=_generate_state(surface),
        actions=_generate_actions(surface),
        # Add semantic info for DOM contract
        view_name=dazzle_attrs.get("view"),
        entity_name=dazzle_attrs.get("entity"),
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
