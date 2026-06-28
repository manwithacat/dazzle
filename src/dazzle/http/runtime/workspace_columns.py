"""Column-metadata builders for workspace regions (#1057).

Pre-v0.67.100 these three helpers lived inline in
`workspace_rendering.py` (which clocks at 4,483 lines). Extracted as
the first cut of the per-concern decomposition — they're self-contained,
take IR specs in and return plain dicts out, and have no dependency on
the request/response cycle.

Public API:
- ``field_kind_to_col_type(field, entity)`` — map a FieldSpec to a
  column rendering type (``badge`` / ``bool`` / ``date`` / ``currency``
  / ``text``).
- ``build_surface_columns(entity_spec, surface_spec)`` — derive
  columns from a LIST surface's section elements, preserving the
  author's field order and threading per-element ``visible:``
  predicates through to the column metadata.
- ``build_entity_columns(entity_spec)`` — fallback column derivation
  from the entity's full field list when a surface doesn't pin its
  own projection. Hard-caps at 8 columns to avoid runaway tables.
"""

from __future__ import annotations

from typing import Any

from dazzle.core.strings import to_api_plural
from dazzle.render.filters import status_tone_map


def field_kind_to_col_type(field: Any, entity: Any = None) -> str:
    """Map an IR field to a column rendering type for workspace templates.

    Args:
        field: FieldSpec IR object.
        entity: Optional EntitySpec — when provided, checks if this field
                is the state-machine status field and returns ``"badge"``.
    """
    kind = field.type.kind
    kind_val: str = kind.value if hasattr(kind, "value") else str(kind) if kind else ""
    if kind_val == "enum":
        return "badge"
    if kind_val == "bool":
        return "bool"
    if kind_val in ("date", "datetime"):
        return "date"
    if kind_val == "money":
        return "currency"
    # State-machine status field renders as badge
    if entity is not None:
        sm = entity.state_machine
        if sm and sm.status_field == field.name:
            return "badge"
    return "text"


def build_surface_columns(
    entity_spec: Any, surface_spec: Any, enums: Any = None
) -> list[dict[str, Any]]:
    """Build column metadata from a list surface's field projection.

    Uses the surface's section elements to determine which entity fields to
    show and in what order, rather than dumping all entity fields.

    ``enums`` (the app's shared `enum` blocks) lets a badge column carry its
    declared `semantic:` value→tone map (#1493 slice 2); pass the appspec's
    ``enums`` so shared-enum bindings resolve (inline `enum[...]` bindings
    resolve without it).
    """
    if not entity_spec or not hasattr(entity_spec, "fields"):
        return []

    # Collect field names from surface sections (preserving order). Carry the
    # element-level (or fallback section-level) visible: predicate so the
    # request handler can hide columns the persona shouldn't see (#872).
    surface_fields: list[str] = []
    field_visible_conditions: dict[str, dict[str, Any] | None] = {}
    # #1470 Phase 2: per-field explicit format: override (None when unannotated).
    field_formats: dict[str, Any] = {}
    for section in surface_spec.sections:
        _sec_vis = getattr(section, "visible", None)
        _section_vis_cond = _sec_vis.model_dump() if _sec_vis is not None else None
        for element in section.elements:
            fn = element.field_name
            if fn and fn != "id" and fn not in surface_fields:
                surface_fields.append(fn)
                _el_vis = getattr(element, "visible", None)
                field_visible_conditions[fn] = (
                    _el_vis.model_dump() if _el_vis else _section_vis_cond
                )
                field_formats[fn] = getattr(element, "format", None)

    if not surface_fields:
        return build_entity_columns(entity_spec, enums)

    # Build a lookup from entity fields
    field_map: dict[str, Any] = {f.name: f for f in entity_spec.fields}

    columns: list[dict[str, Any]] = []
    for fn in surface_fields:
        f = field_map.get(fn)
        if not f:
            continue
        _vis_cond = field_visible_conditions.get(fn)
        _fmt = field_formats.get(fn)
        ft = f.type
        kind = ft.kind
        kind_val: str = kind.value if hasattr(kind, "value") else str(kind) if kind else ""
        # Ref and belongs_to fields
        if kind_val in ("ref", "belongs_to"):
            rel_name = f.name[:-3] if f.name.endswith("_id") else f.name
            ref_entity = getattr(ft, "ref_entity", None)
            ref_route = f"/{to_api_plural(str(ref_entity))}/{{id}}" if ref_entity else ""
            ref_col: dict[str, Any] = {
                "key": rel_name,
                "label": rel_name.replace("_", " ").title(),
                "type": "ref",
                "sortable": False,
                "ref_route": ref_route,
            }
            if _vis_cond:
                ref_col["visible_condition"] = _vis_cond
            if _fmt is not None:
                ref_col["format_kind"] = _fmt.kind
                ref_col["format_arg"] = _fmt.arg or ""
            columns.append(ref_col)
            continue
        # Skip non-displayable types
        if kind_val in ("uuid", "has_many", "has_one", "embeds"):
            continue
        col_type = field_kind_to_col_type(f, entity_spec)
        col_key = f"{f.name}_minor" if kind_val == "money" else f.name
        col: dict[str, Any] = {
            "key": col_key,
            "label": f.name.replace("_", " ").title(),
            "type": col_type,
            "sortable": True,
        }
        if _vis_cond:
            col["visible_condition"] = _vis_cond
        if _fmt is not None:
            col["format_kind"] = _fmt.kind
            col["format_arg"] = _fmt.arg or ""
        if kind_val == "money":
            col["currency_code"] = getattr(ft, "currency_code", None) or "GBP"
        if col_type == "badge":
            # #1493 slice 2: declared `semantic:` binding + SM-terminal inference.
            _sem = status_tone_map(ft, enums, entity_spec.state_machine)
            if _sem:
                col["semantic_map"] = _sem
            if kind_val == "enum":
                ev = getattr(ft, "enum_values", None)
                if ev:
                    col["filterable"] = True
                    col["filter_options"] = list(ev)
            else:
                sm = entity_spec.state_machine
                if sm:
                    states = sm.states
                    if states:
                        col["filterable"] = True
                        col["filter_options"] = list(states)
        if col_type == "bool":
            col["filterable"] = True
            col["filter_options"] = ["true", "false"]
        columns.append(col)
    return columns


def build_entity_columns(entity_spec: Any, enums: Any = None) -> list[dict[str, Any]]:
    """Pre-compute column metadata from an entity spec (constant-folded at startup).

    This replaces per-request column derivation with a one-time computation.
    All data comes from IR (field types, enum values, state machines) and
    never changes during the lifetime of the server. ``enums`` carries the app's
    shared `enum` blocks so badge columns pick up their declared `semantic:`
    value→tone map (#1493 slice 2).
    """
    columns: list[dict[str, Any]] = []
    if not entity_spec or not hasattr(entity_spec, "fields"):
        return columns

    for f in entity_spec.fields:
        if f.name == "id":
            continue
        ft = f.type
        kind = ft.kind
        kind_val: str = kind.value if hasattr(kind, "value") else str(kind) if kind else ""
        # Show ref/belongs_to columns with resolved display name; hide other relation types
        if kind_val in ("ref", "belongs_to"):
            rel_name = f.name[:-3] if f.name.endswith("_id") else f.name
            ref_entity = getattr(ft, "ref_entity", None)
            # Ensure ref_entity is a plain string (not a pydantic/Cython object)
            ref_route = f"/{to_api_plural(str(ref_entity))}/{{id}}" if ref_entity else ""
            columns.append(
                {
                    "key": rel_name,
                    "label": rel_name.replace("_", " ").title(),
                    "type": "ref",
                    "sortable": False,
                    "ref_route": ref_route,
                }
            )
            continue
        if kind_val in ("uuid", "has_many", "has_one", "embeds"):
            continue
        if f.name.endswith("_id"):
            continue
        col_type = field_kind_to_col_type(f, entity_spec)
        col_key = f.name
        if kind_val == "money":
            col_key = f"{f.name}_minor"
        col: dict[str, Any] = {
            "key": col_key,
            "label": f.name.replace("_", " ").title(),
            "type": col_type,
            "sortable": True,
        }
        if kind_val == "money":
            col["currency_code"] = getattr(ft, "currency_code", None) or "GBP"
        if col_type == "badge":
            # #1493 slice 2: declared `semantic:` binding + SM-terminal inference.
            _sem = status_tone_map(ft, enums, entity_spec.state_machine)
            if _sem:
                col["semantic_map"] = _sem
            if kind_val == "enum":
                ev = getattr(ft, "enum_values", None)
                if ev:
                    col["filterable"] = True
                    col["filter_options"] = list(ev)
            else:
                sm = entity_spec.state_machine
                if sm:
                    states = sm.states
                    if states:
                        col["filterable"] = True
                        col["filter_options"] = list(states)
        if col_type == "bool":
            col["filterable"] = True
            col["filter_options"] = ["true", "false"]
        columns.append(col)
        if len(columns) >= 8:
            break
    return columns
