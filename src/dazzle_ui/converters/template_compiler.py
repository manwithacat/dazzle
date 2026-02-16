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
from dazzle.core.ir.money import CURRENCY_SCALES, get_currency_scale
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

# ── Currency metadata ─────────────────────────────────────────────────

CURRENCY_SYMBOLS: dict[str, str] = {
    "GBP": "\u00a3",
    "USD": "$",
    "EUR": "\u20ac",
    "AUD": "A$",
    "CAD": "C$",
    "CHF": "CHF",
    "CNY": "\u00a5",
    "INR": "\u20b9",
    "NZD": "NZ$",
    "SGD": "S$",
    "HKD": "HK$",
    "SEK": "kr",
    "NOK": "kr",
    "DKK": "kr",
    "ZAR": "R",
    "MXN": "MX$",
    "BRL": "R$",
    "JPY": "\u00a5",
    "KRW": "\u20a9",
    "VND": "\u20ab",
    "CLP": "CLP",
    "ISK": "kr",
    "BHD": "BHD",
    "KWD": "KWD",
    "OMR": "OMR",
    "TND": "TND",
    "JOD": "JOD",
    "IQD": "IQD",
    "LYD": "LYD",
}

# Default currencies shown in unpinned money dropdowns
_DEFAULT_CURRENCY_OPTIONS = [
    "GBP",
    "USD",
    "EUR",
    "AUD",
    "CAD",
    "CHF",
    "JPY",
    "CNY",
    "INR",
    "SGD",
    "HKD",
    "SEK",
    "NOK",
    "DKK",
    "NZD",
]


def _build_currency_options(
    selected_code: str = "GBP",
) -> list[dict[str, Any]]:
    """Build currency option dicts for unpinned money field dropdown."""
    options: list[dict[str, Any]] = []
    for code in _DEFAULT_CURRENCY_OPTIONS:
        options.append(
            {
                "code": code,
                "scale": CURRENCY_SCALES.get(code, 2),
                "symbol": CURRENCY_SYMBOLS.get(code, code),
            }
        )
    # Ensure selected_code is in the list
    if selected_code not in _DEFAULT_CURRENCY_OPTIONS:
        options.insert(
            0,
            {
                "code": selected_code,
                "scale": CURRENCY_SCALES.get(selected_code, 2),
                "symbol": CURRENCY_SYMBOLS.get(selected_code, selected_code),
            },
        )
    return options


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
        FieldTypeKind.MONEY: "money",
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
                col_currency = ""
                if field_spec and field_spec.type and field_spec.type.kind == FieldTypeKind.MONEY:
                    col_key = f"{element.field_name}_minor"
                    col_currency = field_spec.type.currency_code or "GBP"
                # Sensitive fields are masked in list views (show last 4 chars)
                is_sensitive = bool(field_spec and field_spec.is_sensitive)
                col_type = "sensitive" if is_sensitive else _field_type_to_column_type(field_spec)
                columns.append(
                    ColumnContext(
                        key=col_key,
                        label=element.label or element.field_name.replace("_", " ").title(),
                        type=col_type,
                        sortable=has_sort,
                        filterable=filterable and not is_sensitive,
                        filter_type=filter_type,
                        filter_options=filter_options,
                        currency_code=col_currency,
                    )
                )
    elif entity and entity.fields:
        for field in entity.fields:
            if not field.is_primary_key:
                is_sensitive = field.is_sensitive
                filterable = field.name in filter_fields and not is_sensitive
                filter_type, filter_options = (
                    _infer_filter_type(field, entity, field.name) if filterable else ("text", [])
                )
                # Money fields: use expanded _minor column key
                col_key = field.name
                col_currency = ""
                if field.type and field.type.kind == FieldTypeKind.MONEY:
                    col_key = f"{field.name}_minor"
                    col_currency = field.type.currency_code or "GBP"
                col_type = "sensitive" if is_sensitive else _field_type_to_column_type(field)
                columns.append(
                    ColumnContext(
                        key=col_key,
                        label=field.name.replace("_", " ").title(),
                        type=col_type,
                        sortable=has_sort,
                        filterable=filterable,
                        filter_type=filter_type,
                        filter_options=filter_options,
                        currency_code=col_currency,
                    )
                )

    return columns


def _build_money_field(
    field_name: str,
    label: str | None,
    field_spec: ir.FieldSpec,
) -> FieldContext:
    """Build a FieldContext for a money/currency field."""
    currency_code = field_spec.type.currency_code or ""
    currency_fixed = bool(currency_code)
    if not currency_code:
        currency_code = "GBP"  # default for unpinned
    scale = get_currency_scale(currency_code)
    symbol = CURRENCY_SYMBOLS.get(currency_code, currency_code)
    display_label = label or field_name.replace("_", " ").title()
    extra: dict[str, Any] = {
        "currency_code": currency_code,
        "currency_fixed": currency_fixed,
        "scale": scale,
        "symbol": symbol,
        "currency_options": (_build_currency_options(currency_code) if not currency_fixed else []),
    }
    return FieldContext(
        name=field_name,
        label=display_label,
        type="money",
        required=bool(field_spec.is_required),
        extra=extra,
    )


def _build_enum_field_options(
    field_spec: ir.FieldSpec | None,
) -> list[dict[str, str]]:
    """Build select options for an enum field."""
    if (
        field_spec
        and field_spec.type
        and field_spec.type.kind == FieldTypeKind.ENUM
        and field_spec.type.enum_values
    ):
        return [
            {"value": v, "label": v.replace("_", " ").title()} for v in field_spec.type.enum_values
        ]
    return []


def _build_state_machine_field_options(
    field_name: str,
    entity: ir.EntitySpec | None,
) -> tuple[list[dict[str, str]], str | None]:
    """Build select options for a state machine field.

    Returns:
        (options, form_type_override) — options list and "select" if matched, else ([], None).
    """
    if entity and entity.state_machine:
        sm = entity.state_machine
        if field_name == "status" or (
            hasattr(sm, "field") and getattr(sm, "field", None) == field_name
        ):
            options = [{"value": s, "label": s.replace("_", " ").title()} for s in sm.states]
            return options, "select"
    return [], None


def _resolve_field_source(
    source_ref: str,
) -> FieldSourceContext | None:
    """Resolve a source= option (e.g. pack.operation) to a FieldSourceContext."""
    if not source_ref or "." not in source_ref:
        return None

    # Try the centralised resolver first (uses pre-built fragment_sources)
    source_ctx: FieldSourceContext | None = None
    try:
        from dazzle_ui.runtime.template_context import build_field_source_context

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

    return source_ctx


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
        # Money fields: single widget with major-unit display + hidden minor-unit value
        if field_spec and field_spec.type and field_spec.type.kind == FieldTypeKind.MONEY:
            fields.append(_build_money_field(field_name, label, field_spec))
            continue

        display_label = label or field_name.replace("_", " ").title()
        form_type = _field_type_to_form_type(field_spec)

        options = _build_enum_field_options(field_spec)

        if not options:
            sm_options, sm_type = _build_state_machine_field_options(field_name, entity)
            if sm_options:
                options = sm_options
                form_type = sm_type or form_type

        is_required = bool(field_spec and field_spec.is_required)

        source_ctx: FieldSourceContext | None = None
        source_ref = element_options.get("source")
        if source_ref:
            source_ctx = _resolve_field_source(source_ref)
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


def _compile_list_surface(
    surface: ir.SurfaceSpec,
    entity: ir.EntitySpec | None,
    entity_name: str,
    api_endpoint: str,
    entity_slug: str,
    app_prefix: str,
) -> PageContext:
    """Compile a LIST mode surface to a PageContext with table context."""
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


def _compile_form_surface(
    surface: ir.SurfaceSpec,
    entity: ir.EntitySpec | None,
    entity_name: str,
    api_endpoint: str,
    entity_slug: str,
    app_prefix: str,
) -> PageContext:
    """Compile a CREATE or EDIT mode surface to a PageContext with form context."""
    fields = _build_form_fields(surface, entity)
    if surface.mode == SurfaceMode.CREATE:
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
    else:
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


def _compile_view_surface(
    surface: ir.SurfaceSpec,
    entity: ir.EntitySpec | None,
    entity_name: str,
    api_endpoint: str,
    entity_slug: str,
    app_prefix: str,
) -> PageContext:
    """Compile a VIEW mode surface to a PageContext with detail context."""
    fields = _build_form_fields(surface, entity)
    transitions: list[TransitionContext] = []
    status_field = "status"
    if entity and entity.state_machine:
        sm = entity.state_machine
        status_field = sm.status_field if hasattr(sm, "status_field") else "status"
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


def _compile_custom_surface(
    surface: ir.SurfaceSpec,
) -> PageContext:
    """Compile a CUSTOM mode surface to a minimal PageContext."""
    return PageContext(
        page_title=surface.title or surface.name,
        template="components/detail_view.html",
    )


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
        return _compile_list_surface(
            surface, entity, entity_name, api_endpoint, entity_slug, app_prefix
        )
    elif surface.mode in (SurfaceMode.CREATE, SurfaceMode.EDIT):
        return _compile_form_surface(
            surface, entity, entity_name, api_endpoint, entity_slug, app_prefix
        )
    elif surface.mode == SurfaceMode.VIEW:
        return _compile_view_surface(
            surface, entity, entity_name, api_endpoint, entity_slug, app_prefix
        )
    else:
        return _compile_custom_surface(surface)


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

    # Build nav items from workspaces — both a flat list (all workspaces)
    # and per-persona variants using workspace access declarations.
    nav_items: list[NavItemContext] = []
    nav_by_persona: dict[str, list[NavItemContext]] = {}
    for ws in appspec.workspaces:
        route = f"{app_prefix}/workspaces/{ws.name}"
        item = NavItemContext(
            label=ws.title or ws.name.replace("_", " ").title(),
            route=route,
        )
        nav_items.append(item)

        # Build per-persona nav: workspace access declarations determine
        # which personas can see each workspace in the nav sidebar.
        ws_access = getattr(ws, "access", None)
        if ws_access:
            allow = getattr(ws_access, "allow_personas", None) or []
            deny = getattr(ws_access, "deny_personas", None) or []
            level = str(getattr(ws_access, "level", ""))
            if allow and "persona" in level.lower():
                # Only add to allowed personas
                for persona_id in allow:
                    nav_by_persona.setdefault(persona_id, []).append(item)
                continue
            if deny:
                # Add to all personas except denied ones
                for p in getattr(appspec, "personas", []) or []:
                    pid = getattr(p, "name", None) or getattr(p, "id", "")
                    if pid and pid not in deny:
                        nav_by_persona.setdefault(pid, []).append(item)
                continue
        # No access restriction — add to all personas
        for p in getattr(appspec, "personas", []) or []:
            pid = getattr(p, "name", None) or getattr(p, "id", "")
            if pid:
                nav_by_persona.setdefault(pid, []).append(item)

    for surface in appspec.surfaces:
        entity: ir.EntitySpec | None = None
        if domain and surface.entity_ref:
            entity = domain.get_entity(surface.entity_ref)

        ctx = compile_surface_to_context(surface, entity, app_prefix=app_prefix)
        ctx.app_name = appspec.title or appspec.name.replace("_", " ").title()
        ctx.nav_items = nav_items
        ctx.nav_by_persona = nav_by_persona
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

    # Register a "/" fallback only for simple apps (no workspaces).
    # When workspaces exist, the page router adds a redirect to the first
    # workspace instead — see create_page_routes() in page_routes.py.
    if not appspec.workspaces:
        list_surfaces = [s for s in appspec.surfaces if s.mode == SurfaceMode.LIST]
        if list_surfaces and "/" not in contexts:
            first_list = list_surfaces[0]
            entity = None
            if domain and first_list.entity_ref:
                entity = domain.get_entity(first_list.entity_ref)
            root_ctx = compile_surface_to_context(first_list, entity, app_prefix=app_prefix)
            root_ctx.app_name = appspec.title or appspec.name.replace("_", " ").title()
            root_ctx.nav_items = nav_items
            root_ctx.nav_by_persona = nav_by_persona
            root_ctx.view_name = first_list.name
            root_ctx.current_route = "/"
            contexts["/"] = root_ctx

    return contexts
