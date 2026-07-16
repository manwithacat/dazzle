"""PageContext → renderer-registry flat ctx dict.

Extracted from page_routes to keep the request router file smaller and
drop cyclomatic complexity of the former monolithic ``_build_dispatch_ctx``
(CC ~135). Public entrypoint remains ``_build_dispatch_ctx`` (re-exported
from page_routes for existing imports).
"""

from __future__ import annotations

from typing import Any

from dazzle.core import ir
from dazzle.render.fragment.form_field import field_context_to_dict


def _dispatch_ctx_from_table(
    render_ctx: Any, surface: ir.SurfaceSpec | None, table: Any
) -> dict[str, Any]:
    """LIST-mode: TableContext → flat list-adapter ctx."""
    columns_out: list[dict[str, Any]] = []
    for col in getattr(table, "columns", []) or []:
        columns_out.append(
            {
                "key": getattr(col, "key", ""),
                "label": getattr(col, "label", "") or getattr(col, "key", ""),
                "type": getattr(col, "type", "text"),
                "sortable": getattr(col, "sortable", False),
                "filterable": getattr(col, "filterable", False),
                "hidden": getattr(col, "hidden", False),
                "filter_type": getattr(col, "filter_type", "text") or "text",
                "filter_ref_entity": getattr(col, "filter_ref_entity", "") or "",
                "filter_ref_api": getattr(col, "filter_ref_api", "") or "",
                "filter_options": [
                    (str(o.get("value", "")), str(o.get("label", o.get("value", ""))))
                    for o in (getattr(col, "filter_options", []) or [])
                ],
            }
        )
    _peek = getattr(surface, "peek", None)
    peek_mode = "off" if _peek is None else (getattr(_peek, "value", None) or str(_peek))
    return {
        "items": list(getattr(table, "rows", []) or []),
        "columns": columns_out,
        "peek_mode": peek_mode,
        "endpoint": getattr(table, "api_endpoint", "") or "",
        "total": int(getattr(table, "total", 0) or 0),
        "page": int(getattr(table, "page", 1) or 1),
        "page_size": int(getattr(table, "page_size", 20) or 20),
        "region_name": getattr(surface, "name", "") or getattr(table, "table_id", "") or "",
        "empty_message": getattr(table, "empty_message", "") or "No items found.",
        "empty_collection": getattr(table, "empty_collection", "") or "",
        "empty_filtered": getattr(table, "empty_filtered", "") or "",
        "empty_forbidden": getattr(table, "empty_forbidden", "") or "",
        "empty_kind": getattr(table, "empty_kind", "") or "collection",
        "create_url": getattr(table, "create_url", "") or "",
        "create_label": getattr(table, "create_label", "") or "",
        "entity_title": getattr(table, "entity_title", "") or "",
        "detail_url_template": getattr(table, "detail_url_template", "") or "",
        "detail_url_candidates": list(getattr(table, "detail_url_candidates", None) or []),
        "detail_url_fallback_template": getattr(table, "detail_url_fallback_template", "") or "",
        "search_enabled": bool(getattr(table, "search_enabled", False)),
        "search_fields": list(getattr(table, "search_fields", []) or []),
        "filter_values": dict(getattr(table, "filter_values", {}) or {}),
        "sort_field": str(getattr(table, "sort_field", "") or ""),
        "sort_dir": str(getattr(table, "sort_dir", "asc") or "asc"),
        "bulk_actions": bool(getattr(table, "bulk_actions", False)),
        "inline_editable": list(getattr(table, "inline_editable", []) or []),
        "refresh_interval": getattr(table, "refresh_interval", None),
        "pagination_mode": str(getattr(table, "pagination_mode", "pages") or "pages"),
        "search_first": bool(getattr(table, "search_first", False)),
    }


def _dispatch_ctx_from_form(form: Any) -> dict[str, Any]:
    """CREATE/EDIT: FormContext → flat form-adapter ctx."""
    initial_values = getattr(form, "initial_values", {}) or {}
    fields_out: list[dict[str, Any]] = [
        field_context_to_dict(field, initial_values) for field in getattr(form, "fields", []) or []
    ]
    is_edit = str(getattr(form, "mode", "create")).lower() == "edit"
    form_sections = getattr(form, "sections", []) or []
    sections_out: list[dict[str, Any]] = []
    if len(form_sections) >= 2:
        field_index = {entry["name"]: entry for entry in fields_out}
        for section in form_sections:
            section_fields = []
            for sf in getattr(section, "fields", []) or []:
                sf_name = getattr(sf, "name", "")
                matched = field_index.get(sf_name)
                if matched is not None:
                    section_fields.append(matched)
            sections_out.append(
                {
                    "name": getattr(section, "name", ""),
                    "title": getattr(section, "title", "") or getattr(section, "name", ""),
                    "fields": section_fields,
                    "note": getattr(section, "note", "") or "",
                }
            )
    ctx_out: dict[str, Any] = {
        "fields": fields_out,
        "action": getattr(form, "action_url", "") or "",
        "method": str(getattr(form, "method", "POST") or "POST").upper(),
        "submit_label": "Save" if is_edit else "Create",
        "cancel_url": getattr(form, "cancel_url", "") or "",
        "item_id": str((getattr(form, "initial_values", {}) or {}).get("id", "") or ""),
    }
    if sections_out:
        ctx_out["sections"] = sections_out
    return ctx_out


def _one_detail_field_dict(f: Any, item: dict[str, Any]) -> dict[str, Any]:
    """Map one FieldContext + item → flat detail field dict."""
    field_name = getattr(f, "name", "") or getattr(f, "key", "")
    kind = getattr(f, "type", "text") or "text"
    value = item.get(field_name, "") if isinstance(item, dict) else ""
    if kind == "ref" and isinstance(item, dict):
        rel = field_name[:-3] if field_name.endswith("_id") else field_name
        value = item.get(f"{rel}_display") or item.get(f"{field_name}_display") or value
    extra = getattr(f, "extra", None) or {}
    currency_code = str(extra.get("currency_code", "") or "") if isinstance(extra, dict) else ""
    return {
        "key": field_name,
        "label": getattr(f, "label", "") or field_name,
        "value": "" if value is None else value,
        "kind": kind,
        "currency_code": currency_code,
        "semantic_map": dict(getattr(f, "enum_semantics", {}) or {}),
    }


def _detail_fields_from_context(detail: Any) -> list[dict[str, Any]]:
    """Map DetailContext.fields + item values → adapter field dicts."""
    item = getattr(detail, "item", {}) or {}
    if not isinstance(item, dict):
        item = {}
    return [_one_detail_field_dict(f, item) for f in getattr(detail, "fields", []) or []]


def _detail_sections_from_context(detail: Any) -> list[dict[str, Any]]:
    """#1600 Wedge B: map DetailContext.sections → adapter section dicts."""
    item = getattr(detail, "item", {}) or {}
    if not isinstance(item, dict):
        item = {}
    out: list[dict[str, Any]] = []
    for sec in getattr(detail, "sections", None) or []:
        fields_out = [_one_detail_field_dict(f, item) for f in getattr(sec, "fields", []) or []]
        if not fields_out:
            continue
        out.append(
            {
                "name": getattr(sec, "name", "") or "",
                "title": getattr(sec, "title", "") or getattr(sec, "name", "") or "",
                "note": getattr(sec, "note", None) or "",
                "layout": getattr(sec, "layout", None) or "",
                "fields": fields_out,
            }
        )
    return out


def _append_subtype_panel_fields(
    detail_fields_out: list[dict[str, Any]],
    item: dict[str, Any],
    surface: ir.SurfaceSpec,
    app_spec: Any,
) -> None:
    """#1217 Phase 3e: merge subtype_panel branch fields into the detail list."""
    from dazzle.render.subtype_panel import resolve_subtype_panel_surface

    row_kind = item.get("kind")
    seen_keys = {f["key"] for f in detail_fields_out}
    for section in surface.sections:
        if getattr(section, "subtype_panel", None) is None:
            continue
        resolved = resolve_subtype_panel_surface(section, row_kind, app_spec)
        if resolved is None:
            continue
        for resolved_section in getattr(resolved, "sections", []) or []:
            for element in getattr(resolved_section, "elements", []) or []:
                field_name = getattr(element, "field_name", "") or ""
                if not field_name or field_name in seen_keys:
                    continue
                value = item.get(field_name, "")
                detail_fields_out.append(
                    {
                        "key": field_name,
                        "label": getattr(element, "label", "") or field_name,
                        "value": "" if value is None else value,
                        "kind": "text",
                    }
                )
                seen_keys.add(field_name)


def _related_groups_from_detail(detail: Any) -> list[dict[str, Any]]:
    """Map fetched RelatedGroupContext list → adapter related_groups dicts."""
    related_groups_out: list[dict[str, Any]] = []
    for rg in getattr(detail, "related_groups", []) or []:
        tabs_out: list[dict[str, Any]] = []
        for tab in getattr(rg, "tabs", []) or []:
            if not bool(getattr(tab, "visible", True)):
                continue
            cols_out = [
                {
                    "key": getattr(c, "key", ""),
                    "label": getattr(c, "label", "") or getattr(c, "key", ""),
                    "type": getattr(c, "type", "text") or "text",
                    "currency_code": getattr(c, "currency_code", "") or "",
                }
                for c in (getattr(tab, "columns", []) or [])
            ]
            tabs_out.append(
                {
                    "tab_id": getattr(tab, "tab_id", "") or "",
                    "label": getattr(tab, "label", "") or "",
                    "entity_name": getattr(tab, "entity_name", "") or "",
                    "columns": cols_out,
                    "rows": list(getattr(tab, "rows", []) or []),
                    "total": int(getattr(tab, "total", 0) or 0),
                    "detail_url_template": getattr(tab, "detail_url_template", "") or "",
                    "create_url": getattr(tab, "create_url", "") or "",
                    "filter_field": getattr(tab, "filter_field", "") or "",
                    "filter_type_field": getattr(tab, "filter_type_field", "") or "",
                    "filter_type_value": getattr(tab, "filter_type_value", "") or "",
                }
            )
        related_groups_out.append(
            {
                "group_id": getattr(rg, "group_id", "") or "",
                "label": getattr(rg, "label", "") or "",
                "display": str(getattr(rg, "display", "table") or "table"),
                "is_auto": bool(getattr(rg, "is_auto", False)),
                "tabs": tabs_out,
            }
        )
    return related_groups_out


def _detail_actions_from_context(detail: Any) -> dict[str, Any]:
    """Transitions, integration actions, external links from DetailContext."""
    transitions_out = [
        {
            "to_state": getattr(t, "to_state", "") or "",
            "label": getattr(t, "label", "") or "",
            "api_url": getattr(t, "api_url", "") or "",
        }
        for t in (getattr(detail, "transitions", []) or [])
    ]
    integration_actions_out = [
        {
            "label": getattr(a, "label", "") or "",
            "api_url": getattr(a, "api_url", "") or "",
            "integration_name": getattr(a, "integration_name", "") or "",
            "mapping_name": getattr(a, "mapping_name", "") or "",
        }
        for a in (getattr(detail, "integration_actions", []) or [])
    ]
    external_links_out = [
        {
            "label": getattr(a, "label", "") or "",
            "url": getattr(a, "url", "") or "",
            "new_tab": bool(getattr(a, "new_tab", True)),
            "name": getattr(a, "name", "") or "",
        }
        for a in (getattr(detail, "external_link_actions", []) or [])
    ]
    return {
        "transitions": transitions_out,
        "integration_actions": integration_actions_out,
        "external_link_actions": external_links_out,
    }


def _dispatch_ctx_from_detail(
    detail: Any,
    surface: ir.SurfaceSpec | None,
    *,
    services: Any = None,
) -> dict[str, Any]:
    """VIEW: DetailContext → flat detail-adapter ctx."""
    item = getattr(detail, "item", {}) or {}
    detail_fields_out = _detail_fields_from_context(detail)
    app_spec = getattr(services, "app_spec", None) if services is not None else None
    if (
        app_spec is not None
        and surface is not None
        and getattr(surface, "sections", None)
        and isinstance(item, dict)
    ):
        _append_subtype_panel_fields(detail_fields_out, item, surface, app_spec)
    actions = _detail_actions_from_context(detail)
    return {
        "fields": detail_fields_out,
        "sections": _detail_sections_from_context(detail),
        "region_name": getattr(detail, "entity_name", "") + "_detail",
        "related_groups": _related_groups_from_detail(detail),
        "edit_url": getattr(detail, "edit_url", None) or "",
        "delete_url": getattr(detail, "delete_url", None) or "",
        "back_url": getattr(detail, "back_url", "/") or "/",
        "entity_name": getattr(detail, "entity_name", "") or "",
        "transitions": actions["transitions"],
        "status_field": getattr(detail, "status_field", "status") or "status",
        "integration_actions": actions["integration_actions"],
        "external_link_actions": actions["external_link_actions"],
        "item_id": str(item.get("id", "") or "") if isinstance(item, dict) else "",
        "show_history": bool(getattr(detail, "show_history", False)),
        "detail_context": detail,
    }


def _build_dispatch_ctx(
    render_ctx: Any,
    surface: ir.SurfaceSpec | None = None,
    *,
    services: Any = None,
) -> dict[str, Any]:
    """Translate per-request PageContext into the flat ctx dict adapters consume."""
    table = getattr(render_ctx, "table", None)
    if table is not None:
        return _dispatch_ctx_from_table(render_ctx, surface, table)
    form = getattr(render_ctx, "form", None)
    if form is not None:
        return _dispatch_ctx_from_form(form)
    detail = getattr(render_ctx, "detail", None)
    if detail is not None:
        return _dispatch_ctx_from_detail(detail, surface, services=services)
    return {}
