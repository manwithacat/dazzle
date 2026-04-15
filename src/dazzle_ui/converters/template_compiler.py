"""
Template compiler - converts Dazzle IR to template contexts.

Replaces the UISpec generation path for server-rendered pages.
Converts SurfaceSpec + EntitySpec into PageContext/TableContext/FormContext
that can be directly rendered by Jinja2 templates.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from dazzle.core import ir
from dazzle.core.ir import FieldTypeKind, SurfaceMode
from dazzle.core.ir.money import CURRENCY_SCALES, get_currency_scale
from dazzle.core.strings import to_api_plural
from dazzle_ui.runtime.template_context import (
    ColumnContext,
    DetailContext,
    ExternalLinkAction,
    FieldContext,
    FieldSourceContext,
    FormContext,
    FormSectionContext,
    NavItemContext,
    PageContext,
    RelatedGroupContext,
    RelatedTabContext,
    ReviewActionContext,
    ReviewContext,
    TableContext,
    TransitionContext,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

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


def _field_type_to_column_type(
    field_spec: ir.FieldSpec | None,
    field_name: str = "",
) -> str:
    """Map an IR field type to a table column display type.

    When *field_spec* is ``None`` (e.g. framework-injected timestamp columns
    like ``created_at`` / ``updated_at``), the *field_name* is used as a
    heuristic: names ending with ``_at`` are treated as date columns so the
    template renders them through the ``dateformat`` filter instead of as raw
    ISO-8601 text.
    """
    if not field_spec or not field_spec.type:
        if field_name.endswith("_at"):
            return "date"
        return "text"
    kind = field_spec.type.kind
    type_map = {
        FieldTypeKind.BOOL: "bool",
        FieldTypeKind.DATE: "date",
        FieldTypeKind.DATETIME: "date",
        FieldTypeKind.MONEY: "currency",
        FieldTypeKind.DECIMAL: "text",
        FieldTypeKind.ENUM: "badge",
        FieldTypeKind.REF: "ref",
        FieldTypeKind.BELONGS_TO: "ref",
    }
    return type_map.get(kind, "text")


def _file_accept_attr(field_spec: ir.FieldSpec) -> str:
    """Build an HTML accept attribute value for a file input."""
    # Check BackendSpec file_config if available
    ft = field_spec.type
    if ft and hasattr(ft, "file_config") and ft.file_config:
        allowed = getattr(ft.file_config, "allowed_types", None)
        if allowed:
            return ",".join(allowed)
    return "*/*"


_WIDGET_KIND_TO_FORM_TYPE: dict[str, str] = {}  # WidgetKind → form type string


def _init_widget_form_map() -> None:
    """Lazily initialise the WidgetKind→form-type mapping.

    Deferred to first call so that the import of ``triples`` happens after
    all IR modules are fully initialised.
    """
    global _WIDGET_KIND_TO_FORM_TYPE  # noqa: PLW0603
    if _WIDGET_KIND_TO_FORM_TYPE:
        return
    from dazzle.core.ir.triples import WidgetKind

    _WIDGET_KIND_TO_FORM_TYPE.update(
        {
            WidgetKind.TEXT_INPUT: "text",
            WidgetKind.TEXTAREA: "textarea",
            WidgetKind.NUMBER_INPUT: "number",
            WidgetKind.CHECKBOX: "checkbox",
            WidgetKind.DATE_PICKER: "date",
            WidgetKind.DATETIME_PICKER: "datetime",
            WidgetKind.ENUM_SELECT: "select",
            WidgetKind.SEARCH_SELECT: "ref",
            WidgetKind.EMAIL_INPUT: "email",
            WidgetKind.MONEY_INPUT: "money",
            WidgetKind.FILE_UPLOAD: "file",
        }
    )


def _field_type_to_form_type(field_spec: ir.FieldSpec | None) -> str:
    """Map an IR field type to a form input type via the canonical widget map."""
    if not field_spec or not field_spec.type:
        return "text"
    from dazzle.core.ir.triples import resolve_widget

    _init_widget_form_map()
    widget = resolve_widget(field_spec, has_source=False)
    return _WIDGET_KIND_TO_FORM_TYPE.get(widget, "text")


def _get_field_spec(entity: ir.EntitySpec | None, field_name: str) -> ir.FieldSpec | None:
    """Look up a field spec from an entity by name.

    When the exact name isn't found, tries ``field_name + "_id"`` so that
    surfaces using the relation name (e.g. ``field school``) resolve to the
    underlying FK column (``school_id``) and get the correct ref type.
    """
    if not entity or not entity.fields:
        return None
    for field in entity.fields:
        if field.name == field_name:
            return field
    # Fallback: try the _id suffixed name for FK / belongs_to relations
    if not field_name.endswith("_id"):
        fk_name = field_name + "_id"
        for field in entity.fields:
            if (
                field.name == fk_name
                and field.type
                and field.type.kind
                in (
                    FieldTypeKind.REF,
                    FieldTypeKind.BELONGS_TO,
                )
            ):
                return field
    return None


def _infer_filter_type(
    field_spec: ir.FieldSpec | None,
    entity: ir.EntitySpec | None,
    field_name: str,
    enums: list[ir.EnumSpec] | None = None,
) -> tuple[str, list[dict[str, str]]]:
    """Infer filter UI type and options from a field spec.

    Returns:
        (filter_type, filter_options) — "select" with options for enums/bools/state machines,
        "text" with empty options otherwise.
    """
    if field_spec and field_spec.type:
        kind = field_spec.type.kind
        if kind == FieldTypeKind.ENUM and field_spec.type.enum_values:
            # Check if a named EnumSpec matches these values and has titles
            label_map: dict[str, str] = {}
            if enums:
                vals_set = set(field_spec.type.enum_values)
                for enum_spec in enums:
                    enum_names = {ev.name for ev in enum_spec.values}
                    if enum_names == vals_set:
                        label_map = {ev.name: ev.title for ev in enum_spec.values if ev.title}
                        break
            return "select", [
                {
                    "value": v,
                    "label": label_map.get(v, v.replace("_", " ").title()),
                }
                for v in field_spec.type.enum_values
            ]
        if kind == FieldTypeKind.BOOL:
            return "select", [
                {"value": "true", "label": "Yes"},
                {"value": "false", "label": "No"},
            ]
        if kind in (FieldTypeKind.REF, FieldTypeKind.BELONGS_TO):
            return "select", []  # options populated via HTMX at render time
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
    enums: list[ir.EnumSpec] | None = None,
) -> list[ColumnContext]:
    """Build table column definitions from surface sections or entity fields."""
    columns: list[ColumnContext] = []
    has_sort = bool(ux_spec and ux_spec.sort)
    filter_fields = set(ux_spec.filter) if ux_spec and ux_spec.filter else set()

    if surface.sections:
        for section in surface.sections:
            # Section-level visible: directive applies to all columns in section
            _sec_vis = getattr(section, "visible", None)
            _section_vis_cond = _sec_vis.model_dump() if _sec_vis is not None else None
            for element in section.elements:
                field_spec = _get_field_spec(entity, element.field_name)
                filterable = element.field_name in filter_fields
                filter_type, filter_options = (
                    _infer_filter_type(field_spec, entity, element.field_name, enums)
                    if filterable
                    else ("text", [])
                )
                # Money fields: use expanded _minor column key
                # Ref/belongs_to fields: use relation name (strip _id) so templates
                # access the eagerly-loaded dict, not the raw FK UUID.
                col_key = element.field_name
                col_currency = ""
                if field_spec and field_spec.type and field_spec.type.kind == FieldTypeKind.MONEY:
                    col_key = f"{element.field_name}_minor"
                    col_currency = field_spec.type.currency_code or "GBP"
                elif (
                    field_spec
                    and field_spec.type
                    and field_spec.type.kind
                    in (
                        FieldTypeKind.REF,
                        FieldTypeKind.BELONGS_TO,
                    )
                ):
                    col_key = (
                        element.field_name[:-3]
                        if element.field_name.endswith("_id")
                        else element.field_name
                    )
                # Sensitive fields are masked in list views (show last 4 chars)
                is_sensitive = bool(field_spec and field_spec.is_sensitive)
                col_type = (
                    "sensitive"
                    if is_sensitive
                    else _field_type_to_column_type(field_spec, element.field_name)
                )
                col_label = element.label or col_key.replace("_", " ").title()
                # Element visible: takes precedence; fall back to section visible (#585)
                _el_vis = getattr(element, "visible", None)
                _col_vis = _el_vis.model_dump() if _el_vis else _section_vis_cond
                # Ref entity name for ref/belongs_to filter dropdowns
                _ref_ent = (
                    field_spec.type.ref_entity
                    if field_spec
                    and field_spec.type
                    and field_spec.type.kind in (FieldTypeKind.REF, FieldTypeKind.BELONGS_TO)
                    and field_spec.type.ref_entity
                    else ""
                )
                _ref_api = f"/{to_api_plural(_ref_ent)}" if _ref_ent else ""
                columns.append(
                    ColumnContext(
                        key=col_key,
                        label=col_label,
                        type=col_type,
                        sortable=has_sort,
                        filterable=filterable and not is_sensitive,
                        filter_type=filter_type,
                        filter_options=filter_options,
                        filter_ref_entity=_ref_ent,
                        filter_ref_api=_ref_api,
                        currency_code=col_currency,
                        visible_condition=_col_vis,
                    )
                )
    elif entity and entity.fields:
        for field in entity.fields:
            if not field.is_primary_key:
                is_sensitive = field.is_sensitive
                filterable = field.name in filter_fields and not is_sensitive
                filter_type, filter_options = (
                    _infer_filter_type(field, entity, field.name, enums)
                    if filterable
                    else ("text", [])
                )
                # Money fields: use expanded _minor column key
                # Ref/belongs_to fields: use relation name (strip _id)
                col_key = field.name
                col_currency = ""
                if field.type and field.type.kind == FieldTypeKind.MONEY:
                    col_key = f"{field.name}_minor"
                    col_currency = field.type.currency_code or "GBP"
                elif field.type and field.type.kind in (
                    FieldTypeKind.REF,
                    FieldTypeKind.BELONGS_TO,
                ):
                    col_key = field.name[:-3] if field.name.endswith("_id") else field.name
                col_type = (
                    "sensitive" if is_sensitive else _field_type_to_column_type(field, field.name)
                )
                _ref_ent = (
                    field.type.ref_entity
                    if field.type
                    and field.type.kind in (FieldTypeKind.REF, FieldTypeKind.BELONGS_TO)
                    and field.type.ref_entity
                    else ""
                )
                _ref_api = f"/{to_api_plural(_ref_ent)}" if _ref_ent else ""
                columns.append(
                    ColumnContext(
                        key=col_key,
                        label=col_key.replace("_", " ").title(),
                        type=col_type,
                        sortable=has_sort,
                        filterable=filterable,
                        filter_type=filter_type,
                        filter_options=filter_options,
                        filter_ref_entity=_ref_ent,
                        filter_ref_api=_ref_api,
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
        logger.warning(
            "Failed to resolve field source '%s' via centralised resolver",
            source_ref,
            exc_info=True,
        )
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
            logger.warning(
                "Failed to resolve field source '%s' via API pack", source_ref, exc_info=True
            )

    return source_ctx


def _build_form_fields(
    surface: ir.SurfaceSpec,
    entity: ir.EntitySpec | None,
) -> list[FieldContext]:
    """Build form field definitions from surface sections or entity fields."""
    fields: list[FieldContext] = []

    fields_to_process: list[
        tuple[str, str | None, ir.FieldSpec | None, dict[str, Any], str, dict[str, Any] | None]
    ] = []

    if surface.sections:
        for section in surface.sections:
            # Merge section-level visible with element-level visible
            _sec_vis = getattr(section, "visible", None)
            section_vis = _sec_vis.model_dump() if _sec_vis is not None else None
            for element in section.elements:
                field_spec = _get_field_spec(entity, element.field_name)
                when_str = str(element.when_expr) if element.when_expr else ""
                # Element visible takes precedence; fall back to section visible
                _el_vis = getattr(element, "visible", None)
                vis = _el_vis.model_dump() if _el_vis else section_vis
                fields_to_process.append(
                    (element.field_name, element.label, field_spec, element.options, when_str, vis)
                )
    elif entity and entity.fields:
        for field in entity.fields:
            if not field.is_primary_key:
                fields_to_process.append((field.name, None, field, {}, "", None))

    for (
        field_name,
        label,
        field_spec,
        element_options,
        when_expr_str,
        vis_cond,
    ) in fields_to_process:
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

        # Widget override from DSL: field name "Label" widget=rich_text
        widget_hint = element_options.get("widget")

        # Default widget fallback for date/datetime fields (cycle 232).
        # The form-field macro branches on `field.widget == "picker"` to
        # activate the Flatpickr datepicker; it also has a fallback branch
        # on `field.type == "date"` that just emits a plain HTML5
        # `<input type="date">`, which is functional but ugly and not the
        # contracted widget. The IR unambiguously says "use the datepicker
        # for date fields" (WidgetKind.DATE_PICKER in triples.py's
        # FIELD_TYPE_TO_WIDGET map), but that resolution never reached
        # the template because `_build_form_fields` was only setting
        # `widget` from explicit DSL overrides. Propagate the intent by
        # defaulting to "picker" for date/datetime fields when the DSL
        # didn't override it.
        if widget_hint is None and field_spec and field_spec.type:
            _k = field_spec.type.kind
            if _k in (FieldTypeKind.DATE, FieldTypeKind.DATETIME):
                widget_hint = "picker"

        # Ref / belongs_to auto-wiring (cycle 236 — closes EX-044).
        # When a field is a plain `ref Entity` with no explicit `source:`
        # override, the form_type resolves to "ref" via the canonical widget
        # map (triples.FIELD_TYPE_TO_WIDGET) but nothing in the template
        # knew the target entity name, so ref fields silently fell through
        # to `<input type="text">`. Populate ref_entity/ref_api here so the
        # form_field.html macro can render an entity-backed select that
        # fetches options from the entity's list API.
        ref_entity_name = ""
        ref_api = ""
        if (
            source_ctx is None
            and field_spec
            and field_spec.type
            and field_spec.type.kind in (FieldTypeKind.REF, FieldTypeKind.BELONGS_TO)
            and field_spec.type.ref_entity
        ):
            ref_entity_name = field_spec.type.ref_entity
            ref_api = f"/{to_api_plural(ref_entity_name)}"

        extra: dict[str, Any] = {}
        if form_type == "file" and field_spec and field_spec.type:
            accept_override = element_options.get("accept")
            extra["accept"] = accept_override if accept_override else _file_accept_attr(field_spec)
            capture = element_options.get("capture")
            if capture:
                extra["capture"] = capture

        fields.append(
            FieldContext(
                name=field_name,
                label=display_label,
                type=form_type,
                required=is_required,
                placeholder=display_label
                if form_type not in ("checkbox", "select", "file")
                else "",
                options=options,
                source=source_ctx,
                extra=extra,
                widget=widget_hint,
                ref_entity=ref_entity_name,
                ref_api=ref_api,
                when_expr=when_expr_str,
                visible_condition=vis_cond,
            )
        )

    return fields


def _build_form_sections(
    surface: ir.SurfaceSpec,
    entity: ir.EntitySpec | None,
) -> list[FormSectionContext]:
    """Build form section contexts when surface has multiple sections.

    Each section becomes a wizard stage with its own field group.
    Only returns sections when the surface defines 2+ sections
    (single-section forms render normally without a stepper).
    """
    if not surface.sections or len(surface.sections) < 2:
        return []

    sections: list[FormSectionContext] = []
    for section in surface.sections:
        _sec_vis = getattr(section, "visible", None)
        section_vis = _sec_vis.model_dump() if _sec_vis is not None else None
        section_fields: list[FieldContext] = []
        for element in section.elements:
            field_spec = _get_field_spec(entity, element.field_name)

            if field_spec and field_spec.type and field_spec.type.kind == FieldTypeKind.MONEY:
                section_fields.append(
                    _build_money_field(element.field_name, element.label, field_spec)
                )
                continue

            display_label = element.label or element.field_name.replace("_", " ").title()
            form_type = _field_type_to_form_type(field_spec)
            options = _build_enum_field_options(field_spec)

            if not options:
                sm_options, sm_type = _build_state_machine_field_options(element.field_name, entity)
                if sm_options:
                    options = sm_options
                    form_type = sm_type or form_type

            is_required = bool(field_spec and field_spec.is_required)

            source_ctx: FieldSourceContext | None = None
            source_ref = element.options.get("source")
            if source_ref:
                source_ctx = _resolve_field_source(source_ref)
                if source_ctx:
                    form_type = "search_select"

            # Widget override from DSL: field name "Label" widget=rich_text
            widget_hint = element.options.get("widget")

            # Default widget fallback for date/datetime fields (cycle 232).
            if widget_hint is None and field_spec and field_spec.type:
                _k = field_spec.type.kind
                if _k in (FieldTypeKind.DATE, FieldTypeKind.DATETIME):
                    widget_hint = "picker"

            # Ref / belongs_to auto-wiring (cycle 236 — closes EX-044).
            ref_entity_name = ""
            ref_api = ""
            if (
                source_ctx is None
                and field_spec
                and field_spec.type
                and field_spec.type.kind in (FieldTypeKind.REF, FieldTypeKind.BELONGS_TO)
                and field_spec.type.ref_entity
            ):
                ref_entity_name = field_spec.type.ref_entity
                ref_api = f"/{to_api_plural(ref_entity_name)}"

            extra: dict[str, Any] = {}
            if form_type == "file" and field_spec and field_spec.type:
                accept_override = element.options.get("accept")
                extra["accept"] = (
                    accept_override if accept_override else _file_accept_attr(field_spec)
                )
                capture = element.options.get("capture")
                if capture:
                    extra["capture"] = capture

            when_str = str(element.when_expr) if element.when_expr else ""
            vis = element.visible.model_dump() if element.visible else None

            section_fields.append(
                FieldContext(
                    name=element.field_name,
                    label=display_label,
                    type=form_type,
                    required=is_required,
                    placeholder=(
                        display_label if form_type not in ("checkbox", "select", "file") else ""
                    ),
                    options=options,
                    source=source_ctx,
                    extra=extra,
                    widget=widget_hint,
                    ref_entity=ref_entity_name,
                    ref_api=ref_api,
                    when_expr=when_str,
                    visible_condition=vis,
                )
            )

        sections.append(
            FormSectionContext(
                name=section.name,
                title=section.title or section.name.replace("_", " ").title(),
                fields=section_fields,
                visible_condition=section_vis,
            )
        )

    return sections


def _compile_list_surface(
    surface: ir.SurfaceSpec,
    entity: ir.EntitySpec | None,
    entity_name: str,
    api_endpoint: str,
    entity_slug: str,
    app_prefix: str,
    enums: list[ir.EnumSpec] | None = None,
) -> PageContext:
    """Compile a LIST mode surface to a PageContext with table context."""
    ux = surface.ux
    columns = _build_columns(surface, entity, ux, enums)
    default_sort_field = ux.sort[0].field if ux and ux.sort else ""
    default_sort_dir = ux.sort[0].direction if ux and ux.sort else "asc"
    search_fields = list(ux.search) if ux and ux.search else []
    search_first = bool(ux and ux.search_first)
    empty_message = (
        ux.empty_message
        if ux and ux.empty_message
        else ("Use search or filters to find results." if search_first else "No items found.")
    )
    table_id = f"dt-{surface.name}"

    # Derive inline-editable columns from field types.
    # Editable: text, bool, badge (enum), date.
    # Not editable: pk, ref, computed, sensitive, money, _id FK columns.
    _EDITABLE_COL_TYPES = {"text", "bool", "badge", "date"}
    _NON_EDITABLE_KEYS = {"id", "created_at", "updated_at"}
    inline_editable = [
        col.key
        for col in columns
        if col.type in _EDITABLE_COL_TYPES
        and col.key not in _NON_EDITABLE_KEYS
        and not col.key.endswith("_id")
    ]

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
            search_first=search_first,
            table_id=table_id,
            inline_editable=inline_editable,
            bulk_actions=True,
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
    sections = _build_form_sections(surface, entity)
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
                sections=sections,
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
                sections=sections,
            ),
        )


def _build_entity_columns(entity: ir.EntitySpec) -> list[ColumnContext]:
    """Build table columns from an entity's fields, excluding PK and FK fields."""
    columns: list[ColumnContext] = []
    for field in entity.fields:
        if field.is_primary_key:
            continue
        # Skip relationship fields (has_many, has_one, embeds) — not tabular
        if field.type and field.type.kind in (
            FieldTypeKind.HAS_MANY,
            FieldTypeKind.HAS_ONE,
        ):
            continue
        col_key = field.name
        col_currency = ""
        if field.type and field.type.kind == FieldTypeKind.MONEY:
            col_key = f"{field.name}_minor"
            col_currency = field.type.currency_code or "GBP"
        elif field.type and field.type.kind in (FieldTypeKind.REF, FieldTypeKind.BELONGS_TO):
            col_key = field.name[:-3] if field.name.endswith("_id") else field.name
        columns.append(
            ColumnContext(
                key=col_key,
                label=col_key.replace("_", " ").title(),
                type=_field_type_to_column_type(field, field.name),
                currency_code=col_currency,
            )
        )
    return columns


def _compile_view_surface(
    surface: ir.SurfaceSpec,
    entity: ir.EntitySpec | None,
    entity_name: str,
    api_endpoint: str,
    entity_slug: str,
    app_prefix: str,
    reverse_refs: list[tuple[str, str, ir.EntitySpec]] | None = None,
    poly_refs: list[tuple[str, str, str, str, ir.EntitySpec]] | None = None,
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

    # Build section-to-visible-condition map for propagating to related tabs (#501)
    _section_vis_map: dict[str, dict[str, Any]] = {}
    if surface.sections:
        for _sec in surface.sections:
            _sec_vis = getattr(_sec, "visible", None)
            if _sec_vis is not None:
                # Index by section name (lowercase) for fuzzy matching
                _section_vis_map[_sec.name.lower()] = _sec_vis.model_dump()

    # Build related entity tabs from reverse references
    related_tabs: list[RelatedTabContext] = []
    for ref_entity_name, fk_field, ref_entity in reverse_refs or []:
        ref_slug = ref_entity_name.lower().replace("_", "-")
        ref_api = f"/{to_api_plural(ref_entity_name)}"
        tab_label = (ref_entity.title or ref_entity_name).replace("_", " ")
        # Build columns from the related entity's fields (exclude FK to parent)
        tab_columns = [c for c in _build_entity_columns(ref_entity) if c.key != fk_field]
        # Match section visible condition to tab (#501)
        _ref_lower = ref_entity_name.lower()
        _tab_vis = (
            _section_vis_map.get(_ref_lower)
            or _section_vis_map.get(_ref_lower.replace("_", ""))
            or _section_vis_map.get(ref_slug.replace("-", "_"))
        )
        related_tabs.append(
            RelatedTabContext(
                tab_id=f"tab-{ref_slug}",
                label=tab_label,
                entity_name=ref_entity_name,
                api_endpoint=ref_api,
                filter_field=fk_field,
                columns=tab_columns,
                detail_url_template=f"{app_prefix}/{ref_slug}/{{id}}",
                create_url=f"{app_prefix}/{ref_slug}/create",
                visible_condition=_tab_vis,
            )
        )

    # Polymorphic FK tabs (#321): entity_type + entity_id pattern
    for src_name, type_field, id_field, type_val, src_entity in poly_refs or []:
        ref_slug = src_name.lower().replace("_", "-")
        ref_api = f"/{to_api_plural(src_name)}"
        tab_label = (src_entity.title or src_name).replace("_", " ")
        # Exclude both the type and id fields from displayed columns
        exclude = {type_field, id_field}
        tab_columns = [c for c in _build_entity_columns(src_entity) if c.key not in exclude]
        # Match section visible condition to tab (#501)
        _src_lower = src_name.lower()
        _poly_vis = _section_vis_map.get(_src_lower) or _section_vis_map.get(
            _src_lower.replace("_", "")
        )
        related_tabs.append(
            RelatedTabContext(
                tab_id=f"tab-{ref_slug}-{type_val}",
                label=tab_label,
                entity_name=src_name,
                api_endpoint=ref_api,
                filter_field=id_field,
                columns=tab_columns,
                detail_url_template=f"{app_prefix}/{ref_slug}/{{id}}",
                create_url=f"{app_prefix}/{ref_slug}/create",
                filter_type_field=type_field,
                filter_type_value=type_val,
                visible_condition=_poly_vis,
            )
        )

    # Group related tabs by surface-declared related groups
    related_groups_ctx: list[RelatedGroupContext] = []
    if surface.related_groups:
        claimed: set[str] = set()
        for group in surface.related_groups:
            group_tabs = [t for t in related_tabs if t.entity_name in group.show]
            claimed.update(group.show)
            if group_tabs:
                related_groups_ctx.append(
                    RelatedGroupContext(
                        group_id=f"group-{group.name}",
                        label=group.title or group.name.replace("_", " ").title(),
                        display=group.display.value,
                        tabs=group_tabs,
                    )
                )
        # Auto-group unclaimed tabs into "Other"
        unclaimed = [t for t in related_tabs if t.entity_name not in claimed]
        if unclaimed:
            related_groups_ctx.append(
                RelatedGroupContext(
                    group_id="group-other",
                    label="Other",
                    display="table",
                    tabs=unclaimed,
                    is_auto=True,
                )
            )
    elif related_tabs:
        # No related groups declared — auto-group everything
        related_groups_ctx.append(
            RelatedGroupContext(
                group_id="group-auto",
                label="Related",
                display="table",
                tabs=related_tabs,
                is_auto=True,
            )
        )

    # Build external link actions from surface actions with EXTERNAL outcomes
    external_links: list[ExternalLinkAction] = []
    for action in surface.actions:
        if action.outcome.kind == ir.OutcomeKind.EXTERNAL and action.outcome.url:
            label = action.label or action.name.replace("_", " ").title()
            external_links.append(
                ExternalLinkAction(
                    name=action.name,
                    label=label,
                    url=action.outcome.url,
                    new_tab=action.outcome.new_tab,
                )
            )

    return PageContext(
        page_title=surface.title or f"{entity_name} Details",
        template="components/detail_view.html",
        detail=DetailContext(
            entity_name=entity_name,
            title=surface.title or f"{entity_name} Details",
            fields=fields,
            api_endpoint=f"{api_endpoint}/{{id}}",
            edit_url=f"{app_prefix}/{entity_slug}/{{id}}/edit",
            delete_url=f"{api_endpoint}/{{id}}",
            back_url=f"{app_prefix}/{entity_slug}",
            transitions=transitions,
            status_field=status_field,
            related_groups=related_groups_ctx,
            external_link_actions=external_links,
        ),
    )


def _compile_review_surface(
    surface: ir.SurfaceSpec,
    entity: ir.EntitySpec | None,
    entity_name: str,
    api_endpoint: str,
    entity_slug: str,
    app_prefix: str,
) -> PageContext:
    """Compile a REVIEW mode surface to a PageContext with review queue context.

    Review mode displays entities one-at-a-time from a filtered queue with
    approve/return action buttons and queue navigation.
    """
    fields = _build_form_fields(surface, entity)

    # Build review actions from state machine transitions
    actions: list[ReviewActionContext] = []
    status_field = "status"
    if entity and entity.state_machine:
        sm = entity.state_machine
        status_field = sm.status_field if hasattr(sm, "status_field") else "status"

        # Map common transition patterns to review actions
        _ACTION_STYLES: dict[str, tuple[str, str]] = {
            "approved": ("Approve", "primary"),
            "reviewed": ("Approve", "primary"),
            "completed": ("Complete", "primary"),
            "accepted": ("Accept", "primary"),
            "closed": ("Close", "primary"),
            "draft": ("Return", "error"),
            "returned": ("Return", "error"),
            "rejected": ("Reject", "error"),
            "flagged": ("Flag", "error"),
        }
        seen_targets: set[str] = set()
        for t in sm.transitions:
            if t.to_state not in seen_targets:
                seen_targets.add(t.to_state)
                label, style = _ACTION_STYLES.get(
                    t.to_state,
                    (t.to_state.replace("_", " ").title(), "ghost"),
                )
                # "Return" actions require notes
                require_notes = style == "error"
                actions.append(
                    ReviewActionContext(
                        label=label,
                        event=t.to_state,
                        style=style,
                        transition_url=f"{api_endpoint}/{{id}}",
                        to_state=t.to_state,
                        require_notes=require_notes,
                    )
                )

    review_base = f"{app_prefix}/{entity_slug}/review"

    return PageContext(
        page_title=surface.title or f"Review {entity_name}",
        template="components/review_queue.html",
        review=ReviewContext(
            entity_name=entity_name,
            title=surface.title or f"Review {entity_name}",
            fields=fields,
            api_endpoint=api_endpoint,
            back_url=f"{app_prefix}/{entity_slug}",
            status_field=status_field,
            actions=actions,
            queue_url=review_base,
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
    reverse_refs: list[tuple[str, str, ir.EntitySpec]] | None = None,
    poly_refs: list[tuple[str, str, str, str, ir.EntitySpec]] | None = None,
    enums: list[ir.EnumSpec] | None = None,
) -> PageContext:
    """
    Convert a Surface IR to a PageContext for template rendering.

    This replaces the UISpec generation path. The PageContext contains
    all data needed to render the appropriate Jinja2 template.

    Args:
        surface: IR surface specification.
        entity: Optional entity specification for field metadata.
        app_prefix: URL prefix for page routes (e.g. "/app"). Not applied to API paths.
        reverse_refs: Entities with ref fields pointing to this entity
            (entity_name, fk_field, entity_spec). Used for related tabs on detail pages.
        poly_refs: Polymorphic FK reverse refs pointing to this entity (#321).
            Each tuple: (source_entity, type_field, id_field, type_value, source_spec).
        enums: Named enum definitions for human-readable filter labels.

    Returns:
        PageContext ready for template rendering.
    """
    entity_name = entity.name if entity else (surface.entity_ref or "Item")
    api_endpoint = f"/{to_api_plural(entity_name)}"
    entity_slug = entity_name.lower().replace("_", "-")

    if surface.mode == SurfaceMode.LIST:
        return _compile_list_surface(
            surface, entity, entity_name, api_endpoint, entity_slug, app_prefix, enums
        )
    elif surface.mode in (SurfaceMode.CREATE, SurfaceMode.EDIT):
        return _compile_form_surface(
            surface, entity, entity_name, api_endpoint, entity_slug, app_prefix
        )
    elif surface.mode == SurfaceMode.VIEW:
        return _compile_view_surface(
            surface,
            entity,
            entity_name,
            api_endpoint,
            entity_slug,
            app_prefix,
            reverse_refs=reverse_refs,
            poly_refs=poly_refs,
        )
    elif surface.mode == SurfaceMode.REVIEW:
        return _compile_review_surface(
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
    # Track which personas each workspace allows (for entity nav below)
    _ws_personas: dict[str, list[str]] = {}
    # Delegate workspace-access resolution to the shared helper so the sidebar
    # nav and the server-side access enforcement agree on who sees what.
    # Before manwithacat/dazzle#775 was fixed, this block had its own divergent rule and
    # ghost nav links appeared in 4 example apps.
    from dazzle_ui.converters.workspace_converter import workspace_allowed_personas

    _personas_list = list(getattr(appspec, "personas", []) or [])
    _all_pids = [p.id for p in _personas_list if p.id]

    for ws in appspec.workspaces:
        route = f"{app_prefix}/workspaces/{ws.name}"
        item = NavItemContext(
            label=ws.title or ws.name.replace("_", " ").title(),
            route=route,
        )
        nav_items.append(item)

        allowed = workspace_allowed_personas(ws, _personas_list)
        # None means "open to all authenticated" → add to every persona.
        # Empty list means "no one" — leave out of every persona's nav.
        # Non-empty list means "only these personas".
        pids_for_this_ws = _all_pids if allowed is None else list(allowed)
        _ws_personas[ws.name] = pids_for_this_ws
        for pid in pids_for_this_ws:
            nav_by_persona.setdefault(pid, []).append(item)

    # Add entity surface links derived from workspace regions so that
    # entity pages show the same nav items as workspace pages.
    _list_surfaces_by_entity: dict[str, Any] = {}
    for surface in appspec.surfaces:
        if surface.mode.value == "list" and surface.entity_ref:
            _list_surfaces_by_entity.setdefault(surface.entity_ref, surface)

    _entity_nav_items: dict[str, Any] = {}  # entity name -> NavItemContext
    for ws in appspec.workspaces:
        ws_pids = _ws_personas.get(ws.name, [])
        for region in getattr(ws, "regions", []) or []:
            source = getattr(region, "source", None)
            if not source:
                continue
            # Create nav item once per entity, reuse for additional personas
            if source not in _entity_nav_items:
                list_surface = _list_surfaces_by_entity.get(source)
                if not list_surface:
                    continue
                entity_slug = source.lower().replace("_", "-")
                entity_item = NavItemContext(
                    label=list_surface.title or source.replace("_", " ").title(),
                    route=f"{app_prefix}/{entity_slug}",
                )
                _entity_nav_items[source] = entity_item
                nav_items.append(entity_item)
            # Always add to this workspace's personas
            entity_item = _entity_nav_items[source]
            for pid in ws_pids:
                persona_nav = nav_by_persona.setdefault(pid, [])
                if entity_item not in persona_nav:
                    persona_nav.append(entity_item)

    # Build reverse-ref map: for each entity, find other entities that have
    # ref fields pointing to it.  Used to populate related-entity tabs on
    # detail pages (hub-and-spoke pattern, issue #301).
    _reverse_refs: dict[str, list[tuple[str, str, ir.EntitySpec]]] = {}
    # Polymorphic FK map (#321): target_entity → list of
    # (source_entity_name, type_field, id_field, type_value, source_entity_spec)
    _poly_refs: dict[str, list[tuple[str, str, str, str, ir.EntitySpec]]] = {}
    if domain:
        entity_names_lower = {e.name.lower().replace("_", ""): e.name for e in domain.entities}
        # Also map snake_case versions (e.g. "sole_trader" → "SoleTrader")
        for e in domain.entities:
            # Convert PascalCase to snake_case for matching
            snake_form = ""
            for i, ch in enumerate(e.name):
                if ch.isupper() and i > 0:
                    snake_form += "_"
                snake_form += ch.lower()
            entity_names_lower[snake_form] = e.name

        for ent in domain.entities:
            fields_by_name = {f.name: f for f in ent.fields}
            for field in ent.fields:
                # Direct FK refs
                if field.type and field.type.kind == FieldTypeKind.REF and field.type.ref_entity:
                    _reverse_refs.setdefault(field.type.ref_entity, []).append(
                        (ent.name, field.name, ent)
                    )
                # Polymorphic FK detection (#321): *_type (enum) + *_id (uuid) pairs
                if (
                    field.type
                    and field.type.kind == FieldTypeKind.ENUM
                    and field.type.enum_values
                    and field.name.endswith("_type")
                ):
                    id_suffix = field.name[: -len("_type")] + "_id"
                    id_field = fields_by_name.get(id_suffix)
                    if id_field and id_field.type and id_field.type.kind == FieldTypeKind.UUID:
                        for val in field.type.enum_values:
                            target = entity_names_lower.get(val.lower().replace("_", ""))
                            if not target:
                                target = entity_names_lower.get(val.lower())
                            if target:
                                _poly_refs.setdefault(target, []).append(
                                    (ent.name, field.name, id_suffix, val, ent)
                                )

    _route_surfaces: dict[str, ir.SurfaceSpec] = {}

    for surface in appspec.surfaces:
        entity: ir.EntitySpec | None = None
        if domain and surface.entity_ref:
            entity = domain.get_entity(surface.entity_ref)

        entity_name = entity.name if entity else (surface.entity_ref or "Item")
        ctx = compile_surface_to_context(
            surface,
            entity,
            app_prefix=app_prefix,
            reverse_refs=_reverse_refs.get(entity_name),
            poly_refs=_poly_refs.get(entity_name),
            enums=list(appspec.enums) if appspec.enums else None,
        )
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
            SurfaceMode.REVIEW: f"{app_prefix}/{entity_slug}/review/{{id}}",
        }
        route = route_map.get(surface.mode, f"/{surface.name}")

        if route in contexts:
            # Route collision: two surfaces produce the same URL.
            # Prefer the surface with explicit sections (more specific field
            # definitions) over one that relies on entity-field fallback.
            prev = _route_surfaces[route]
            if surface.sections and not prev.sections:
                logger.debug(
                    "Route %s: preferring surface '%s' (has sections) over '%s'",
                    route,
                    surface.name,
                    prev.name,
                )
                contexts[route] = ctx
                _route_surfaces[route] = surface
            else:
                logger.debug(
                    "Route %s: keeping surface '%s' over '%s'",
                    route,
                    prev.name,
                    surface.name,
                )
        else:
            contexts[route] = ctx
            _route_surfaces[route] = surface

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
            root_ctx = compile_surface_to_context(
                first_list,
                entity,
                app_prefix=app_prefix,
                enums=list(appspec.enums) if appspec.enums else None,
            )
            root_ctx.app_name = appspec.title or appspec.name.replace("_", " ").title()
            root_ctx.nav_items = nav_items
            root_ctx.nav_by_persona = nav_by_persona
            root_ctx.view_name = first_list.name
            root_ctx.current_route = "/"
            contexts["/"] = root_ctx

    return contexts
