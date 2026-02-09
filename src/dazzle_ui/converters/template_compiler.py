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
from dazzle_ui.runtime.template_context import (
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


def _infer_filter_type(
    field_spec: ir.FieldSpec | None,
    entity: ir.EntitySpec | None,
    field_name: str,
) -> tuple[str, list[dict[str, str]]]:
    """Infer filter UI type and options from a field spec.

    Returns:
        (filter_type, filter_options) — "select" with options for enums/bools/state machines,
        "text" with empty options otherwise.
    """
    if field_spec and field_spec.type:
        kind = field_spec.type.kind
        if kind == FieldTypeKind.ENUM and field_spec.type.enum_values:
            return "select", [
                {"value": v, "label": v.replace("_", " ").title()}
                for v in field_spec.type.enum_values
            ]
        if kind == FieldTypeKind.BOOL:
            return "select", [
                {"value": "true", "label": "Yes"},
                {"value": "false", "label": "No"},
            ]
    # Check state machine field
    if entity and entity.state_machine:
        sm = entity.state_machine
        if field_name == "status" or (
            hasattr(sm, "field") and getattr(sm, "field", None) == field_name
        ):
            return "select", [{"value": s, "label": s.replace("_", " ").title()} for s in sm.states]
    return "text", []


def _build_columns(
    surface: ir.SurfaceSpec,
    entity: ir.EntitySpec | None,
    ux_spec: ir.UXSpec | None = None,
) -> list[ColumnContext]:
    """Build table column definitions from surface sections or entity fields."""
    columns: list[ColumnContext] = []
    has_sort = bool(ux_spec and ux_spec.sort)
    filter_fields = set(ux_spec.filter) if ux_spec and ux_spec.filter else set()

    if surface.sections:
        for section in surface.sections:
            for element in section.elements:
                field_spec = _get_field_spec(entity, element.field_name)
                filterable = element.field_name in filter_fields
                filter_type, filter_options = (
                    _infer_filter_type(field_spec, entity, element.field_name)
                    if filterable
                    else ("text", [])
                )
                # Money fields: use expanded _minor column key
                col_key = element.field_name
                if field_spec and field_spec.type and field_spec.type.kind == FieldTypeKind.MONEY:
                    col_key = f"{element.field_name}_minor"
                columns.append(
                    ColumnContext(
                        key=col_key,
                        label=element.label or element.field_name.replace("_", " ").title(),
                        type=_field_type_to_column_type(field_spec),
                        sortable=has_sort,
                        filterable=filterable,
                        filter_type=filter_type,
                        filter_options=filter_options,
                    )
                )
    elif entity and entity.fields:
        for field in entity.fields:
            if not field.is_primary_key:
                filterable = field.name in filter_fields
                filter_type, filter_options = (
                    _infer_filter_type(field, entity, field.name) if filterable else ("text", [])
                )
                # Money fields: use expanded _minor column key
                col_key = field.name
                if field.type and field.type.kind == FieldTypeKind.MONEY:
                    col_key = f"{field.name}_minor"
                columns.append(
                    ColumnContext(
                        key=col_key,
                        label=field.name.replace("_", " ").title(),
                        type=_field_type_to_column_type(field),
                        sortable=has_sort,
                        filterable=filterable,
                        filter_type=filter_type,
                        filter_options=filter_options,
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
        # Money fields expand into _minor (number) + _currency (text) pair
        if field_spec and field_spec.type and field_spec.type.kind == FieldTypeKind.MONEY:
            currency_code = field_spec.type.currency_code or "GBP"
            display_label = label or field_name.replace("_", " ").title()
            fields.append(
                FieldContext(
                    name=f"{field_name}_minor",
                    label=f"{display_label} (Minor Units)",
                    type="number",
                    required=bool(field_spec.is_required),
                    placeholder="Amount in minor units (e.g. pence)",
                    options=[],
                )
            )
            fields.append(
                FieldContext(
                    name=f"{field_name}_currency",
                    label=f"{display_label} Currency",
                    type="text",
                    required=False,
                    placeholder=currency_code,
                    options=[],
                )
            )
            continue

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
            # Try the centralised resolver first (uses pre-built fragment_sources)
            try:
                from dazzle_ui.runtime.template_context import build_field_source_context

                # fragment_sources may be attached to the module-level cache
                _fs = getattr(_build_form_fields, "_fragment_sources", {})
                source_ctx = build_field_source_context(source_ref, _fs)
            except Exception:
                source_ctx = None

            # Fall back to direct API pack resolution
            if source_ctx is None:
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
                except Exception:
                    pass  # Fall back to default field type

            if source_ctx:
                form_type = "search_select"

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
    app_prefix: str = "",
) -> PageContext:
    """
    Convert a Surface IR to a PageContext for template rendering.

    This replaces the UISpec generation path. The PageContext contains
    all data needed to render the appropriate Jinja2 template.

    Args:
        surface: IR surface specification.
        entity: Optional entity specification for field metadata.
        app_prefix: URL prefix for page routes (e.g. "/app"). Not applied to API paths.

    Returns:
        PageContext ready for template rendering.
    """
    entity_name = entity.name if entity else (surface.entity_ref or "Item")
    api_endpoint = f"/{to_api_plural(entity_name)}"
    entity_slug = entity_name.lower().replace("_", "-")

    if surface.mode == SurfaceMode.LIST:
        ux = surface.ux
        columns = _build_columns(surface, entity, ux)
        default_sort_field = ux.sort[0].field if ux and ux.sort else ""
        default_sort_dir = ux.sort[0].direction if ux and ux.sort else "asc"
        search_fields = list(ux.search) if ux and ux.search else []
        empty_message = ux.empty_message if ux and ux.empty_message else "No items found."
        table_id = f"dt-{surface.name}"
        return PageContext(
            page_title=surface.title or f"{entity_name} List",
            template="components/filterable_table.html",
            table=TableContext(
                entity_name=entity_name,
                title=surface.title or f"{entity_name}s",
                columns=columns,
                api_endpoint=api_endpoint,
                create_url=f"{app_prefix}/{entity_slug}/create",
                detail_url_template=f"{app_prefix}/{entity_slug}/{{id}}",
                search_enabled=bool(search_fields),
                default_sort_field=default_sort_field,
                default_sort_dir=default_sort_dir,
                sort_field=default_sort_field,
                sort_dir=default_sort_dir,
                search_fields=search_fields,
                empty_message=empty_message,
                table_id=table_id,
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
                cancel_url=f"{app_prefix}/{entity_slug}",
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
                cancel_url=f"{app_prefix}/{entity_slug}/{{id}}",
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
                edit_url=f"{app_prefix}/{entity_slug}/{{id}}/edit",
                delete_url=f"{api_endpoint}/{{id}}",
                back_url=f"{app_prefix}/{entity_slug}",
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
    app_prefix: str = "",
) -> dict[str, PageContext]:
    """
    Compile all surfaces in an AppSpec to PageContexts.

    Returns a mapping of route path -> PageContext for each surface.

    Args:
        appspec: Complete application specification.
        app_prefix: URL prefix for page routes (e.g. "/app"). Not applied to API paths.

    Returns:
        Dictionary mapping URL paths to PageContext objects.
    """
    contexts: dict[str, PageContext] = {}
    domain = appspec.domain

    # Build nav items from workspaces
    nav_items: list[NavItemContext] = []
    for ws in appspec.workspaces:
        route = f"{app_prefix}/workspaces/{ws.name}"
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

        ctx = compile_surface_to_context(surface, entity, app_prefix=app_prefix)
        ctx.app_name = appspec.title or appspec.name.replace("_", " ").title()
        ctx.nav_items = nav_items
        ctx.view_name = surface.name

        # Determine the route for this surface
        entity_name = entity.name if entity else (surface.entity_ref or "item")
        entity_slug = entity_name.lower().replace("_", "-")

        route_map = {
            SurfaceMode.LIST: f"{app_prefix}/{entity_slug}",
            SurfaceMode.CREATE: f"{app_prefix}/{entity_slug}/create",
            SurfaceMode.EDIT: f"{app_prefix}/{entity_slug}/{{id}}/edit",
            SurfaceMode.VIEW: f"{app_prefix}/{entity_slug}/{{id}}",
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
        root_ctx = compile_surface_to_context(first_list, entity, app_prefix=app_prefix)
        root_ctx.app_name = appspec.title or appspec.name.replace("_", " ").title()
        root_ctx.nav_items = nav_items
        root_ctx.view_name = first_list.name
        root_ctx.current_route = "/"
        contexts["/"] = root_ctx

    return contexts
