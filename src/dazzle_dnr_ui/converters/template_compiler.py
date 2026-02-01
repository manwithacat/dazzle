"""
Template compiler - converts Dazzle IR to template contexts.

Replaces the UISpec generation path for server-rendered pages.
Converts SurfaceSpec + EntitySpec into PageContext/TableContext/FormContext
that can be directly rendered by Jinja2 templates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from dazzle.core import ir
from dazzle.core.ir import FieldTypeKind, SurfaceMode
from dazzle.core.strings import to_api_plural
from dazzle_dnr_ui.runtime.template_context import (
    ColumnContext,
    DetailContext,
    FieldContext,
    FieldSourceContext,
    FormContext,
    NavItemContext,
    PageContext,
    TableContext,
    TransitionContext,
)

if TYPE_CHECKING:
    pass


def _field_type_to_column_type(field_spec: ir.FieldSpec | None) -> str:
    """Map an IR field type to a table column display type."""
    if not field_spec or not field_spec.type:
        return "text"
    kind = field_spec.type.kind
    type_map = {
        FieldTypeKind.BOOL: "bool",
        FieldTypeKind.DATE: "date",
        FieldTypeKind.DATETIME: "date",
        FieldTypeKind.MONEY: "currency",
        FieldTypeKind.DECIMAL: "text",
        FieldTypeKind.ENUM: "badge",
    }
    return type_map.get(kind, "text")


def _field_type_to_form_type(field_spec: ir.FieldSpec | None) -> str:
    """Map an IR field type to a form input type."""
    if not field_spec or not field_spec.type:
        return "text"
    kind = field_spec.type.kind
    type_map = {
        FieldTypeKind.BOOL: "checkbox",
        FieldTypeKind.DATE: "date",
        FieldTypeKind.DATETIME: "datetime",
        FieldTypeKind.INT: "number",
        FieldTypeKind.DECIMAL: "number",
        FieldTypeKind.MONEY: "number",
        FieldTypeKind.TEXT: "textarea",
        FieldTypeKind.EMAIL: "email",
        FieldTypeKind.URL: "text",
        FieldTypeKind.ENUM: "select",
    }
    return type_map.get(kind, "text")


def _get_field_spec(entity: ir.EntitySpec | None, field_name: str) -> ir.FieldSpec | None:
    """Look up a field spec from an entity by name."""
    if not entity or not entity.fields:
        return None
    for field in entity.fields:
        if field.name == field_name:
            return field
    return None


def _build_columns(
    surface: ir.SurfaceSpec,
    entity: ir.EntitySpec | None,
) -> list[ColumnContext]:
    """Build table column definitions from surface sections or entity fields."""
    columns: list[ColumnContext] = []

    if surface.sections:
        for section in surface.sections:
            for element in section.elements:
                field_spec = _get_field_spec(entity, element.field_name)
                columns.append(
                    ColumnContext(
                        key=element.field_name,
                        label=element.label or element.field_name.replace("_", " ").title(),
                        type=_field_type_to_column_type(field_spec),
                    )
                )
    elif entity and entity.fields:
        for field in entity.fields:
            if not field.is_primary_key:
                columns.append(
                    ColumnContext(
                        key=field.name,
                        label=field.name.replace("_", " ").title(),
                        type=_field_type_to_column_type(field),
                    )
                )

    return columns


def _build_form_fields(
    surface: ir.SurfaceSpec,
    entity: ir.EntitySpec | None,
) -> list[FieldContext]:
    """Build form field definitions from surface sections or entity fields."""
    fields: list[FieldContext] = []

    fields_to_process: list[tuple[str, str | None, ir.FieldSpec | None, dict[str, Any]]] = []

    if surface.sections:
        for section in surface.sections:
            for element in section.elements:
                field_spec = _get_field_spec(entity, element.field_name)
                fields_to_process.append(
                    (element.field_name, element.label, field_spec, element.options)
                )
    elif entity and entity.fields:
        for field in entity.fields:
            if not field.is_primary_key:
                fields_to_process.append((field.name, None, field, {}))

    for field_name, label, field_spec, element_options in fields_to_process:
        display_label = label or field_name.replace("_", " ").title()
        form_type = _field_type_to_form_type(field_spec)

        # Build options for select/enum fields
        options: list[dict[str, str]] = []
        if (
            field_spec
            and field_spec.type
            and field_spec.type.kind == FieldTypeKind.ENUM
            and field_spec.type.enum_values
        ):
            options = [
                {"value": v, "label": v.replace("_", " ").title()}
                for v in field_spec.type.enum_values
            ]

        # Check if field has state machine (also renders as select)
        if not options and entity and entity.state_machine:
            sm = entity.state_machine
            if field_name == "status" or (
                hasattr(sm, "field") and getattr(sm, "field", None) == field_name
            ):
                options = [{"value": s, "label": s.replace("_", " ").title()} for s in sm.states]
                form_type = "select"

        is_required = bool(field_spec and field_spec.is_required)

        # Build FieldSourceContext from source= option (e.g. source=pack.operation)
        source_ctx: FieldSourceContext | None = None
        source_ref = element_options.get("source")
        if source_ref and "." in source_ref:
            pack_name, op_name = source_ref.rsplit(".", 1)
            try:
                from dazzle.api_kb import load_pack

                pack = load_pack(pack_name)
                if pack:
                    source_config = pack.generate_fragment_source(op_name)
                    source_ctx = FieldSourceContext(
                        endpoint="/api/_fragments/search",
                        display_key=source_config.get("display_key", "name"),
                        value_key=source_config.get("value_key", "id"),
                        secondary_key=source_config.get("secondary_key", ""),
                        autofill=source_config.get("autofill", {}),
                    )
                    form_type = "search_select"
            except Exception:
                pass  # Fall back to default field type

        fields.append(
            FieldContext(
                name=field_name,
                label=display_label,
                type=form_type,
                required=is_required,
                placeholder=display_label if form_type not in ("checkbox", "select") else "",
                options=options,
                source=source_ctx,
            )
        )

    return fields


def compile_surface_to_context(
    surface: ir.SurfaceSpec,
    entity: ir.EntitySpec | None,
) -> PageContext:
    """
    Convert a Surface IR to a PageContext for template rendering.

    This replaces the UISpec generation path. The PageContext contains
    all data needed to render the appropriate Jinja2 template.

    Args:
        surface: IR surface specification.
        entity: Optional entity specification for field metadata.

    Returns:
        PageContext ready for template rendering.
    """
    entity_name = entity.name if entity else (surface.entity_ref or "Item")
    api_endpoint = f"/{to_api_plural(entity_name)}"
    entity_slug = entity_name.lower().replace("_", "-")

    if surface.mode == SurfaceMode.LIST:
        columns = _build_columns(surface, entity)
        return PageContext(
            page_title=surface.title or f"{entity_name} List",
            template="components/filterable_table.html",
            table=TableContext(
                entity_name=entity_name,
                title=surface.title or f"{entity_name}s",
                columns=columns,
                api_endpoint=api_endpoint,
                create_url=f"/{entity_slug}/create",
                detail_url_template=f"/{entity_slug}/{{id}}",
            ),
        )

    elif surface.mode == SurfaceMode.CREATE:
        fields = _build_form_fields(surface, entity)
        return PageContext(
            page_title=surface.title or f"Create {entity_name}",
            template="components/form.html",
            form=FormContext(
                entity_name=entity_name,
                title=surface.title or f"Create {entity_name}",
                fields=fields,
                action_url=api_endpoint,
                method="post",
                mode="create",
                cancel_url=f"/{entity_slug}",
            ),
        )

    elif surface.mode == SurfaceMode.EDIT:
        fields = _build_form_fields(surface, entity)
        return PageContext(
            page_title=surface.title or f"Edit {entity_name}",
            template="components/form.html",
            form=FormContext(
                entity_name=entity_name,
                title=surface.title or f"Edit {entity_name}",
                fields=fields,
                action_url=f"{api_endpoint}/{{id}}",
                method="put",
                mode="edit",
                cancel_url=f"/{entity_slug}/{{id}}",
            ),
        )

    elif surface.mode == SurfaceMode.VIEW:
        fields = _build_form_fields(surface, entity)
        # Build transition contexts from entity state machine
        transitions: list[TransitionContext] = []
        status_field = "status"
        if entity and entity.state_machine:
            sm = entity.state_machine
            status_field = sm.status_field if hasattr(sm, "status_field") else "status"
            # Collect all unique target states from transitions
            seen_targets: set[str] = set()
            for t in sm.transitions:
                if t.to_state not in seen_targets:
                    seen_targets.add(t.to_state)
                    transitions.append(
                        TransitionContext(
                            to_state=t.to_state,
                            label=t.to_state.replace("_", " ").title(),
                            api_url=f"{api_endpoint}/{{id}}",
                        )
                    )
        return PageContext(
            page_title=surface.title or f"{entity_name} Details",
            template="components/detail_view.html",
            detail=DetailContext(
                entity_name=entity_name,
                title=surface.title or f"{entity_name} Details",
                fields=fields,
                edit_url=f"/{entity_slug}/{{id}}/edit",
                delete_url=f"{api_endpoint}/{{id}}",
                back_url=f"/{entity_slug}",
                transitions=transitions,
                status_field=status_field,
            ),
        )

    else:
        # CUSTOM mode — minimal page
        return PageContext(
            page_title=surface.title or surface.name,
            template="components/detail_view.html",
        )


def compile_appspec_to_templates(
    appspec: ir.AppSpec,
) -> dict[str, PageContext]:
    """
    Compile all surfaces in an AppSpec to PageContexts.

    Returns a mapping of route path -> PageContext for each surface.

    Args:
        appspec: Complete application specification.

    Returns:
        Dictionary mapping URL paths to PageContext objects.
    """
    contexts: dict[str, PageContext] = {}
    domain = appspec.domain

    # Build nav items from workspaces
    nav_items: list[NavItemContext] = []
    for i, ws in enumerate(appspec.workspaces):
        route = "/" if i == 0 else f"/{ws.name.replace('_', '-')}"
        nav_items.append(
            NavItemContext(
                label=ws.title or ws.name.replace("_", " ").title(),
                route=route,
            )
        )

    for surface in appspec.surfaces:
        entity: ir.EntitySpec | None = None
        if domain and surface.entity_ref:
            entity = domain.get_entity(surface.entity_ref)

        ctx = compile_surface_to_context(surface, entity)
        ctx.app_name = appspec.title or appspec.name.replace("_", " ").title()
        ctx.nav_items = nav_items
        ctx.view_name = surface.name

        # Determine the route for this surface
        entity_name = entity.name if entity else (surface.entity_ref or "item")
        entity_slug = entity_name.lower().replace("_", "-")

        route_map = {
            SurfaceMode.LIST: f"/{entity_slug}",
            SurfaceMode.CREATE: f"/{entity_slug}/create",
            SurfaceMode.EDIT: f"/{entity_slug}/{{id}}/edit",
            SurfaceMode.VIEW: f"/{entity_slug}/{{id}}",
        }
        route = route_map.get(surface.mode, f"/{surface.name}")
        contexts[route] = ctx

    # If we have a list surface, also register it at "/" for the primary entity
    list_surfaces = [s for s in appspec.surfaces if s.mode == SurfaceMode.LIST]
    if list_surfaces and "/" not in contexts:
        first_list = list_surfaces[0]
        entity = None
        if domain and first_list.entity_ref:
            entity = domain.get_entity(first_list.entity_ref)
        root_ctx = compile_surface_to_context(first_list, entity)
        root_ctx.app_name = appspec.title or appspec.name.replace("_", " ").title()
        root_ctx.nav_items = nav_items
        root_ctx.view_name = first_list.name
        root_ctx.current_route = "/"
        contexts["/"] = root_ctx

    return contexts
