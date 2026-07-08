"""
Context compiler — converts Dazzle IR to typed render contexts.

Converts SurfaceSpec + EntitySpec into the `PageContext`/`TableContext`/`FormContext`
dataclasses (`dazzle.render.context`) consumed by the typed-Fragment renderers. (Named
"template_compiler" historically; Jinja2 was removed framework-wide in #1042/ADR-0023,
so there are no templates — it builds typed contexts, not Jinja contexts.)
"""

from __future__ import annotations

import functools
import logging
from collections import Counter
from typing import TYPE_CHECKING, Any

from dazzle.core import ir
from dazzle.core.ir import FieldTypeKind, SurfaceMode
from dazzle.core.ir.money import CURRENCY_SCALES, get_currency_scale
from dazzle.core.ir.triples import WidgetKind, resolve_widget
from dazzle.core.strings import to_api_plural
from dazzle.page import app_paths
from dazzle.render.context import (
    ColumnContext,
    CompanionContext,
    CompanionEntryContext,
    CompanionStageContext,
    DetailContext,
    ExternalLinkAction,
    FieldContext,
    FieldSourceContext,
    FormContext,
    FormSectionContext,
    NavItemContext,
    PageContext,
    PdfViewerContext,
    RelatedGroupContext,
    RelatedTabContext,
    TableContext,
    TransitionContext,
)
from dazzle.render.filters import status_tone_map

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
_DEFAULT_CURRENCY_OPTIONS = (
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
)


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
        # datetime stays date-only in dense list cells (time would be noise per
        # row); the detail view renders it as `datetime` with time (#1491 1d).
        FieldTypeKind.DATETIME: "date",
        FieldTypeKind.MONEY: "currency",
        # decimal keeps its natural precision via str() (a price 19.99 must not
        # round); float is rounded to avoid leaking full binary precision (#1491).
        FieldTypeKind.DECIMAL: "text",
        FieldTypeKind.FLOAT: "number",
        FieldTypeKind.JSON: "json",
        FieldTypeKind.ENUM: "badge",
        FieldTypeKind.REF: "ref",
        FieldTypeKind.BELONGS_TO: "ref",
    }
    return type_map.get(kind, "text")


def _enum_semantic_map(
    field_spec: ir.FieldSpec | None,
    enums: list[ir.EnumSpec] | None = None,
    state_machine: Any = None,
) -> dict[str, str]:
    """Effective value→tone map for an enum/status field column (#1493 slice 2).

    Thin FieldSpec→FieldType adapter over the shared `render.filters.status_tone_map`
    (declared `semantic:` binding + state-machine terminal inference), which both
    this page-render builder and the http-workspace builder call, so the logic
    lives in one place.
    """
    return status_tone_map(field_spec.type if field_spec else None, enums, state_machine)


def _file_accept_attr(field_spec: ir.FieldSpec) -> str:
    """Build an HTML accept attribute value for a file input."""
    # Check BackendSpec file_config if available
    ft = field_spec.type
    if ft and hasattr(ft, "file_config") and ft.file_config:
        allowed = getattr(ft.file_config, "allowed_types", None)
        if allowed:
            return ",".join(allowed)
    return "*/*"


@functools.cache
def _widget_kind_to_form_type() -> dict[str, str]:
    """The WidgetKind→form-type mapping, built once on first use.

    `functools.cache` defers the build to first call (so the `triples` import lands
    after all IR modules initialise) and memoises it — no module-level mutable global
    + lazy-init `global` (ADR-0005). The returned dict must be treated read-only.
    """
    return {
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


def _field_type_to_form_type(field_spec: ir.FieldSpec | None) -> str:
    """Map an IR field type to a form input type via the canonical widget map."""
    if not field_spec or not field_spec.type:
        return "text"

    widget = resolve_widget(field_spec, has_source=False)
    return _widget_kind_to_form_type().get(widget, "text")


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
                        semantic_map=_enum_semantic_map(
                            field_spec, enums, entity.state_machine if entity else None
                        ),
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
                        semantic_map=_enum_semantic_map(
                            field, enums, entity.state_machine if entity else None
                        ),
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
        from dazzle.render.context import build_field_source_context

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
                    endpoint="/_dazzle/fragments/search",
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
            # #1213: thread the file ui_mode modifier through so the
            # form renderer can emit the right data-dz-file-mode attr.
            if field_spec.type.ui_mode:
                extra["ui_mode"] = field_spec.type.ui_mode

        # #977 cycle 5 — rich-text DSL knobs. Field-level overrides
        # propagate into the form_field.html data-dz-options JSON; the
        # dz-richtext.js mount reads `options.toolbar` (list of command
        # names) and `options.maxLength` (int).
        if widget_hint == "rich_text":
            toolbar_csv = element_options.get("rich_text_toolbar")
            if toolbar_csv:
                extra["rich_text_toolbar"] = [
                    item.strip() for item in toolbar_csv.split(",") if item.strip()
                ]
            max_len = element_options.get("rich_text_max_length")
            if max_len:
                try:
                    extra["rich_text_max_length"] = int(max_len)
                except ValueError:
                    pass  # silently ignore malformed value; lint catches it

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

            # #977 cycle 5 — rich-text DSL knobs (sectioned forms).
            if widget_hint == "rich_text":
                toolbar_csv = element.options.get("rich_text_toolbar")
                if toolbar_csv:
                    extra["rich_text_toolbar"] = [
                        item.strip() for item in toolbar_csv.split(",") if item.strip()
                    ]
                max_len = element.options.get("rich_text_max_length")
                if max_len:
                    try:
                        extra["rich_text_max_length"] = int(max_len)
                    except ValueError:
                        pass

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
                    help=element.help or "",  # v0.61.88 (#918)
                )
            )

        sections.append(
            FormSectionContext(
                name=section.name,
                title=section.title or section.name.replace("_", " ").title(),
                fields=section_fields,
                visible_condition=section_vis,
                note=section.note or "",  # v0.61.88 (#918)
            )
        )

    return sections


def _extract_surface_purpose(ux: ir.UXSpec | None) -> tuple[str, dict[str, str]]:
    """Extract surface-level purpose + per-persona overrides.

    The surface-level ``ux.purpose`` is the default subtitle for every
    persona. Persona-variant ``purpose`` (from ``for <persona>:`` blocks)
    overrides it at request time via the compile-dict-then-resolve
    pattern proven for ``empty_message`` (cycle 240).

    Closes the UX-048 "purpose unwired" gap. 14+ DSL declarations across
    contact_manager + fieldtest_hub are invisible at render time before
    this wiring lands.
    """
    if ux is None:
        return "", {}
    purpose = ux.purpose or ""
    persona_purposes: dict[str, str] = {}
    for variant in ux.persona_variants or []:
        if variant.purpose:
            persona_purposes[variant.persona] = variant.purpose
    return purpose, persona_purposes


def _compile_list_surface(
    surface: ir.SurfaceSpec,
    entity: ir.EntitySpec | None,
    entity_name: str,
    api_endpoint: str,
    entity_slug: str,
    app_prefix: str,
    enums: list[ir.EnumSpec] | None = None,
    entities_with_create_surface: frozenset[str] | None = None,
) -> PageContext:
    """Compile a LIST mode surface to a PageContext with table context."""
    ux = surface.ux
    columns = _build_columns(surface, entity, ux, enums)
    default_sort_field = ux.sort[0].field if ux and ux.sort else ""
    default_sort_dir = ux.sort[0].direction if ux and ux.sort else "asc"
    search_fields = list(ux.search) if ux and ux.search else []
    search_first = bool(ux and ux.search_first)
    # Handle both empty_message shapes (#807): legacy single-string or
    # the typed EmptyMessages struct. The single-string fallback preserves
    # existing behaviour; the struct fills per-case fields, and the
    # `empty_message` default is still computed for templates that don't
    # yet pick up `empty_kind`.
    _raw_empty = ux.empty_message if ux else None
    empty_collection = ""
    empty_filtered = ""
    empty_forbidden = ""
    if isinstance(_raw_empty, ir.EmptyMessages):
        empty_collection = _raw_empty.collection or ""
        empty_filtered = _raw_empty.filtered or ""
        empty_forbidden = _raw_empty.forbidden or ""
        # Legacy field: use the collection copy as the canonical fallback.
        empty_message = empty_collection or (
            "Use search or filters to find results." if search_first else "No items found."
        )
    elif isinstance(_raw_empty, str):
        empty_message = _raw_empty
    else:
        empty_message = (
            "Use search or filters to find results." if search_first else "No items found."
        )

    # Per-persona PersonaVariant overrides (cycle 240 pilot + cycle 243
    # extension). Collect both `empty_message` and `hide` from every
    # variant and ship them as dicts to the TableContext; the per-request
    # resolver in page_routes.py looks up the current user's persona and
    # applies the overrides before rendering. This is the canonical
    # compile-dict-then-resolve-per-request pattern and is the
    # generalisable shape for wiring any PersonaVariant field through
    # to the runtime.
    persona_empty_messages: dict[str, str] = {}
    persona_hide: dict[str, list[str]] = {}
    persona_read_only: set[str] = set()
    if ux and ux.persona_variants:
        for _variant in ux.persona_variants:
            if _variant.empty_message:
                persona_empty_messages[_variant.persona] = _variant.empty_message
            if _variant.hide:
                persona_hide[_variant.persona] = list(_variant.hide)
            if _variant.read_only:
                persona_read_only.add(_variant.persona)

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

    page_purpose, persona_purposes = _extract_surface_purpose(ux)

    # Caught by the chaos-monkey fuzz: list surfaces on entities with
    # no CREATE surface (virtual entities — SystemHealth, SystemMetric,
    # ProcessRun, LogEntry, EventTrace; framework-only entities —
    # DeployHistory, AuditEntry, AIJob, JobRun) emitted a "Create"
    # button on the list page. Clicking it navigated to
    # `/app/<entity>/create` which 404s because no create route is
    # mounted. The right signal is "is there a CREATE-mode surface
    # for this entity?" — passed as `entities_with_create_surface`.
    create_url: str | None = None
    if entities_with_create_surface is None or entity_name in entities_with_create_surface:
        create_url = app_paths.create_path(app_prefix, entity_slug)

    return PageContext(
        page_title=surface.title or f"{entity_name} List",
        page_purpose=page_purpose,
        persona_purposes=persona_purposes,
        # v0.67.79: PageContext.template field is no longer read by any
        # renderer (table rendering moved to table_renderer.py).
        template="",
        table=TableContext(
            entity_name=entity_name,
            title=surface.title or f"{entity_name}s",
            entity_title=(getattr(entity, "title", "") or "") if entity else "",
            columns=columns,
            api_endpoint=api_endpoint,
            create_url=create_url,
            detail_url_template=app_paths.detail_path(app_prefix, entity_slug),
            search_enabled=bool(search_fields),
            default_sort_field=default_sort_field,
            default_sort_dir=default_sort_dir,
            sort_field=default_sort_field,
            sort_dir=default_sort_dir,
            refresh_interval=getattr(surface, "refresh_interval", None),  # #1399 slice 3
            search_fields=search_fields,
            empty_message=empty_message,
            empty_collection=empty_collection,
            empty_filtered=empty_filtered,
            empty_forbidden=empty_forbidden,
            persona_empty_messages=persona_empty_messages,
            persona_hide=persona_hide,
            persona_read_only=persona_read_only,
            search_first=search_first,
            table_id=table_id,
            inline_editable=inline_editable,
            bulk_actions=True,
        ),
    )


def _build_companion_contexts(surface: ir.SurfaceSpec) -> list[CompanionContext]:
    """Convert IR `CompanionSpec` items into template-render contexts (#923)."""
    out: list[CompanionContext] = []
    for c in getattr(surface, "companions", []):
        out.append(
            CompanionContext(
                name=c.name,
                title=c.title,
                eyebrow=c.eyebrow,
                display=c.display,
                position=str(c.position.value) if c.position else "bottom",
                section_anchor=c.section_anchor,
                aggregate=dict(c.aggregate),
                entries=[
                    CompanionEntryContext(
                        title=e.title, caption=e.caption, state=e.state, icon=e.icon
                    )
                    for e in c.entries
                ],
                stages=[CompanionStageContext(label=s.label, caption=s.caption) for s in c.stages],
                source=c.source,
                limit=c.limit,
            )
        )
    return out


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
    companions = _build_companion_contexts(surface)

    # Cycle 245 — collect persona-variant overrides for form surfaces.
    # Mirrors the cycle 243 list-surface path. Currently wires `hide`
    # and `read_only`; future cycles can extend with `defaults`,
    # `show`, and `action_primary`.
    ux = surface.ux
    persona_hide: dict[str, list[str]] = {}
    persona_read_only: set[str] = set()
    if ux and ux.persona_variants:
        for _variant in ux.persona_variants:
            if _variant.hide:
                persona_hide[_variant.persona] = list(_variant.hide)
            if _variant.read_only:
                persona_read_only.add(_variant.persona)

    page_purpose, persona_purposes = _extract_surface_purpose(ux)
    if surface.mode == SurfaceMode.CREATE:
        return PageContext(
            page_title=surface.title or f"Create {entity_name}",
            page_purpose=page_purpose,
            persona_purposes=persona_purposes,
            # v0.67.74: PageContext.template field is no longer read by any
            # renderer (form rendering moved to the typed substrate, ADR-0049
            # Phase 3b — the legacy form_renderer is deleted). Empty for clarity.
            template="",
            form=FormContext(
                entity_name=entity_name,
                title=surface.title or f"Create {entity_name}",
                fields=fields,
                action_url=api_endpoint,
                method="post",
                mode="create",
                cancel_url=app_paths.list_path(app_prefix, entity_slug),
                sections=sections,
                persona_hide=persona_hide,
                persona_read_only=persona_read_only,
                layout=getattr(surface, "layout", "wizard"),  # v0.61.88 (#918)
                companions=companions,  # v0.61.102 (#923)
            ),
        )
    else:
        return PageContext(
            page_title=surface.title or f"Edit {entity_name}",
            page_purpose=page_purpose,
            persona_purposes=persona_purposes,
            # v0.67.74: PageContext.template field is no longer read by any
            # renderer (form rendering moved to the typed substrate, ADR-0049
            # Phase 3b — the legacy form_renderer is deleted). Empty for clarity.
            template="",
            form=FormContext(
                entity_name=entity_name,
                title=surface.title or f"Edit {entity_name}",
                fields=fields,
                action_url=f"{api_endpoint}/{{id}}",
                method="put",
                mode="edit",
                cancel_url=app_paths.detail_path(app_prefix, entity_slug),
                sections=sections,
                persona_hide=persona_hide,
                persona_read_only=persona_read_only,
                layout=getattr(surface, "layout", "wizard"),  # v0.61.88 (#918)
                companions=companions,  # v0.61.102 (#923)
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
                # No shared-enum registry here (related-tab columns); inline
                # `enum[...]` bindings still resolve via FieldType.enum_semantics,
                # plus SM-terminal inference from the related entity's machine.
                semantic_map=_enum_semantic_map(field, None, entity.state_machine),
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
        # #1558 3c: keep from_state so the request-time detail filter and the
        # list-row render can gate by the record's current state. Dedup by
        # (from_state, to_state) — two edges to the same target from different
        # sources are distinct affordances.
        seen: set[tuple[str, str]] = set()
        for t in sm.transitions:
            key = (t.from_state, t.to_state)
            if key not in seen:
                seen.add(key)
                transitions.append(
                    TransitionContext(
                        from_state=t.from_state,
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

    # Build related entity tabs from reverse references. An entity with more than
    # one FK path to the parent yields one tab per path (#1523): disambiguate the
    # tab_id (the Alpine activeTab key — duplicates render all tabs active) and the
    # label by the FK field, so "Task · assigned to" / "Task · reviewed by" instead
    # of N identical "Task" tabs. Single-path entities keep the historical shape.
    _ref_path_counts = Counter(name for name, _, _ in reverse_refs or [])
    related_tabs: list[RelatedTabContext] = []
    for ref_entity_name, fk_field, ref_entity in reverse_refs or []:
        ref_slug = app_paths.entity_slug(ref_entity_name)
        ref_api = f"/{to_api_plural(ref_entity_name)}"
        tab_label = (ref_entity.title or ref_entity_name).replace("_", " ")
        tab_id = f"tab-{ref_slug}"
        if _ref_path_counts[ref_entity_name] > 1:
            tab_id = f"tab-{ref_slug}-{fk_field.replace('_', '-')}"
            tab_label = f"{tab_label} · {fk_field.replace('_', ' ')}"
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
                tab_id=tab_id,
                label=tab_label,
                entity_name=ref_entity_name,
                api_endpoint=ref_api,
                filter_field=fk_field,
                columns=tab_columns,
                detail_url_template=app_paths.detail_path(app_prefix, ref_slug),
                create_url=app_paths.create_path(app_prefix, ref_slug),
                visible_condition=_tab_vis,
            )
        )

    # Polymorphic FK tabs (#321): entity_type + entity_id pattern
    for src_name, type_field, id_field, type_val, src_entity in poly_refs or []:
        ref_slug = app_paths.entity_slug(src_name)
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
                detail_url_template=app_paths.detail_path(app_prefix, ref_slug),
                create_url=app_paths.create_path(app_prefix, ref_slug),
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

    page_purpose, persona_purposes = _extract_surface_purpose(surface.ux)

    # v0.61.126 (#942): ``display: pdf_viewer`` surface override. Routes
    # the view surface through the built-in PDF viewer chrome instead of
    # the generic detail layout. Storage-bound fields keep precedence
    # (the original #942 shape, ``/api/storage/<name>/proxy`` src); a
    # plain ``file`` field (no storage=) activates document-route mode
    # (#162) — the renderer derives the scope-gated
    # ``/_dazzle/documents`` src instead.
    pdf_viewer_ctx: PdfViewerContext | None = None
    if surface.display == "pdf_viewer" and entity is not None:
        file_fields = [f for f in entity.fields if f.type.kind == FieldTypeKind.FILE]
        storage_bound = next((f for f in file_fields if f.storage), None)
        if storage_bound is not None:
            pdf_viewer_ctx = PdfViewerContext(
                storage_name=storage_bound.storage[0],
                file_field=storage_bound.name,
            )
        elif file_fields:
            pdf_viewer_ctx = PdfViewerContext(
                storage_name=None,
                file_field=file_fields[0].name,
            )

    return PageContext(
        page_title=surface.title or f"{entity_name} Details",
        page_purpose=page_purpose,
        persona_purposes=persona_purposes,
        template="",
        detail=DetailContext(
            entity_name=entity_name,
            title=surface.title or f"{entity_name} Details",
            fields=fields,
            api_endpoint=f"{api_endpoint}/{{id}}",
            edit_url=app_paths.edit_path(app_prefix, entity_slug),
            delete_url=f"{api_endpoint}/{{id}}",
            back_url=app_paths.list_path(app_prefix, entity_slug),
            transitions=transitions,
            status_field=status_field,
            related_groups=related_groups_ctx,
            external_link_actions=external_links,
            show_history=surface.show_history,  # #956 cycle 10
        ),
        pdf_viewer=pdf_viewer_ctx,
    )


def _compile_custom_surface(
    surface: ir.SurfaceSpec,
) -> PageContext:
    """Compile a CUSTOM mode surface to a minimal PageContext."""
    page_purpose, persona_purposes = _extract_surface_purpose(surface.ux)
    return PageContext(
        page_title=surface.title or surface.name,
        page_purpose=page_purpose,
        persona_purposes=persona_purposes,
        # v0.67.75: PageContext.template field is no longer read by any
        # renderer (detail/view rendering moved to the typed substrate,
        # ADR-0049 Phase 2 — the legacy detail_renderer is deleted).
        template="",
    )


def compile_surface_to_context(
    surface: ir.SurfaceSpec,
    entity: ir.EntitySpec | None,
    app_prefix: str = "",
    reverse_refs: list[tuple[str, str, ir.EntitySpec]] | None = None,
    poly_refs: list[tuple[str, str, str, str, ir.EntitySpec]] | None = None,
    enums: list[ir.EnumSpec] | None = None,
    entities_with_create_surface: frozenset[str] | None = None,
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
    entity_slug = app_paths.entity_slug(entity_name)

    if surface.mode == SurfaceMode.LIST:
        return _compile_list_surface(
            surface,
            entity,
            entity_name,
            api_endpoint,
            entity_slug,
            app_prefix,
            enums,
            entities_with_create_surface=entities_with_create_surface,
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
    # #1127: routes that are anon-safe (workspace declared ``access: None``).
    # Used at runtime to swap the sidebar for unauthenticated visitors so
    # ``access: persona(...)`` workspaces don't leak into the nav.
    _anon_safe_routes: set[str] = set()
    _anon_safe_ws_names: set[str] = set()
    # Track which personas each workspace allows (for entity nav below)
    _ws_personas: dict[str, list[str]] = {}
    # Delegate workspace-access resolution to the shared helper so the sidebar
    # nav and the server-side access enforcement agree on who sees what.
    # Before manwithacat/dazzle#775 was fixed, this block had its own divergent rule and
    # ghost nav links appeared in 4 example apps.
    from dazzle.page.converters.workspace_converter import workspace_allowed_personas

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
        # #1127: anon-safe iff the workspace declared no persona gate
        # (``allowed is None``). ``access: persona(...)`` workspaces are
        # never anon-safe regardless of which personas they target.
        if allowed is None:
            _anon_safe_routes.add(route)
            _anon_safe_ws_names.add(ws.name)

    # Add entity surface links derived from workspace regions so that
    # entity pages show the same nav items as workspace pages.
    _list_surfaces_by_entity: dict[str, Any] = {}
    # Track which entities have CREATE-mode surfaces — used to suppress
    # the "Create" button on list pages whose entity has no real
    # /<entity>/create route mounted (auto-injected platform entities
    # like SystemHealth, DeployHistory, AuditEntry; FK-target-only
    # entities). Caught by the chaos-monkey fuzz hitting 404s on the
    # button. Computed once at compile time and threaded into
    # `_compile_list_surface` so every list page gets the right answer.
    _entities_with_create_surface: frozenset[str] = frozenset(
        {s.entity_ref for s in appspec.surfaces if s.mode.value == "create" and s.entity_ref}
    )
    for surface in appspec.surfaces:
        if surface.mode.value == "list" and surface.entity_ref:
            _list_surfaces_by_entity.setdefault(surface.entity_ref, surface)

    _entity_nav_items: dict[str, Any] = {}  # entity name -> NavItemContext
    for ws in appspec.workspaces:
        # Skip auto-discovery for workspaces that declare nav_groups —
        # the author has explicitly curated the entity nav and ungrouped
        # region sources (e.g. ClassEnrolment, QuestionTopic) shouldn't
        # leak in as flat nav items (#873). Mirror page_routes.py.
        if getattr(ws, "nav_groups", None):
            continue
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
                entity_slug = app_paths.entity_slug(source)
                entity_item = NavItemContext(
                    label=list_surface.title or source.replace("_", " ").title(),
                    route=app_paths.list_path(app_prefix, entity_slug),
                )
                _entity_nav_items[source] = entity_item
                nav_items.append(entity_item)
            # Always add to this workspace's personas
            entity_item = _entity_nav_items[source]
            for pid in ws_pids:
                persona_nav = nav_by_persona.setdefault(pid, [])
                if entity_item not in persona_nav:
                    persona_nav.append(entity_item)
            # #1127: entity nav inherits the workspace's anon visibility.
            # Once any anon-safe workspace surfaces this entity, the link
            # is anon-safe — gated workspaces can't retract it.
            if ws.name in _anon_safe_ws_names:
                _anon_safe_routes.add(entity_item.route)

    # v0.61.5 (#863): build nav_groups from each workspace's nav_group
    # declarations — mirrors the logic in page_routes.py line 1676. Entity-
    # list pages (/app/<entity>) then inherit the same collapsible groups
    # the workspace pages show, so the sidebar stays continuous as users
    # navigate between the two page types.
    nav_groups_all: list[dict[str, Any]] = []
    nav_groups_by_persona: dict[str, list[dict[str, Any]]] = {}
    # #1127: groups declared in anon-safe workspaces inherit anon visibility.
    nav_groups_anon: list[dict[str, Any]] = []
    _seen_group_labels: set[str] = set()
    _seen_anon_group_labels: set[str] = set()
    for ws in appspec.workspaces:
        ws_pids = _ws_personas.get(ws.name, [])
        for ng in getattr(ws, "nav_groups", None) or []:
            # Gate children on list-surface existence (#1005). Without this
            # the auto-injected platform-admin Management group emits
            # `/app/user` and `/app/tenant` even though `_ADMIN_SURFACE_DEFS`
            # only mounts list surfaces for 7 of the 10 platform entities —
            # those routes 404. Mirrors the gate on the auto-discovery path
            # 30 lines above. User-authored DSL nav_groups that point at
            # entities without surfaces are also silently dropped, which
            # is the right behaviour: a nav link to nowhere is a bug.
            group_children: list[dict[str, Any]] = []
            for item in ng.items:
                if item.entity not in _list_surfaces_by_entity:
                    continue
                surface = _list_surfaces_by_entity[item.entity]
                group_children.append(
                    {
                        "label": (surface.title or item.entity.replace("_", " ").title()),
                        "route": app_paths.list_path(
                            app_prefix, app_paths.entity_slug(item.entity)
                        ),
                        "icon": item.icon,
                    }
                )
            if not group_children:
                continue
            group: dict[str, Any] = {
                "label": ng.label,
                "icon": ng.icon,
                "collapsed": ng.collapsed,
                "children": group_children,
            }
            # Dedup across workspaces by label: multiple workspaces declaring
            # the same group ("Admin", say) should render once in the global
            # nav (entity-list pages don't know which workspace the user came
            # from — they show the union scoped by the persona-allow map).
            if ng.label not in _seen_group_labels:
                nav_groups_all.append(group)
                _seen_group_labels.add(ng.label)
            for pid in ws_pids:
                persona_groups = nav_groups_by_persona.setdefault(pid, [])
                if not any(g["label"] == ng.label for g in persona_groups):
                    persona_groups.append(group)
            # #1127: anon visitors only see groups from open workspaces.
            if ws.name in _anon_safe_ws_names and ng.label not in _seen_anon_group_labels:
                nav_groups_anon.append(group)
                _seen_anon_group_labels.add(ng.label)

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
            entities_with_create_surface=_entities_with_create_surface,
        )
        ctx.app_name = appspec.title or appspec.name.replace("_", " ").title()
        ctx.nav_items = nav_items
        ctx.nav_by_persona = nav_by_persona
        # #1127: anon-safe variants — items from workspaces with no persona gate.
        ctx.nav_items_anon = [i for i in nav_items if i.route in _anon_safe_routes]
        ctx.nav_groups_anon = nav_groups_anon
        # v0.61.5 (#863): entity-list pages inherit workspace nav groups.
        ctx.nav_groups = nav_groups_all
        ctx.nav_groups_by_persona = nav_groups_by_persona
        ctx.view_name = surface.name
        ctx.entity_ref = surface.entity_ref or ""

        # Determine the route for this surface
        entity_name = entity.name if entity else (surface.entity_ref or "item")
        entity_slug = app_paths.entity_slug(entity_name)

        route_map = {
            SurfaceMode.LIST: app_paths.list_path(app_prefix, entity_slug),
            SurfaceMode.CREATE: app_paths.create_path(app_prefix, entity_slug),
            SurfaceMode.EDIT: app_paths.edit_path(app_prefix, entity_slug),
            SurfaceMode.VIEW: app_paths.detail_path(app_prefix, entity_slug),
        }
        route = route_map.get(surface.mode, f"/{surface.name}")

        if route in contexts:
            # Route collision: two surfaces produce the same default URL.
            # Tiebreak (#1301): prefer a surface with an explicit `render:`
            # clause (a custom renderer is the more-specific intent), then
            # one with explicit sections (specific field definitions) over
            # entity-field fallback. Pre-#1301 only sections were weighed,
            # so a no-render surface declared first silently beat a later
            # `render:` surface — the custom detail viewer never dispatched.
            prev = _route_surfaces[route]
            prev_score = (bool(prev.render), bool(prev.sections))
            new_score = (bool(surface.render), bool(surface.sections))
            winner, loser = (surface, prev) if new_score > prev_score else (prev, surface)
            if new_score > prev_score:
                contexts[route] = ctx
                _route_surfaces[route] = surface
            # Most default-route collisions are benign — the dropped surface
            # is typically reachable via its workspace/experience route, so
            # its default `/app/<entity>/<mode>` URL is vestigial. Only warn
            # when the DROPPED surface carries a `render:` clause: that custom
            # renderer silently won't dispatch on this route (the #1301
            # footgun, now only possible when BOTH surfaces declare render:
            # since render: wins the tiebreak). Benign collisions stay debug.
            log = logger.warning if loser.render else logger.debug
            log(
                "Route %s collision: surface %r renders, %r dropped (winner render=%r, "
                "dropped render=%r)",
                route,
                winner.name,
                loser.name,
                winner.render,
                loser.render,
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
                entities_with_create_surface=_entities_with_create_surface,
            )
            root_ctx.app_name = appspec.title or appspec.name.replace("_", " ").title()
            root_ctx.nav_items = nav_items
            root_ctx.nav_by_persona = nav_by_persona
            # #1127: anon-safe variants for the simple-app "/" fallback too.
            root_ctx.nav_items_anon = [i for i in nav_items if i.route in _anon_safe_routes]
            root_ctx.nav_groups_anon = nav_groups_anon
            root_ctx.nav_groups = nav_groups_all
            root_ctx.nav_groups_by_persona = nav_groups_by_persona
            root_ctx.view_name = first_list.name
            root_ctx.entity_ref = first_list.entity_ref or ""
            root_ctx.current_route = "/"
            contexts["/"] = root_ctx

    # #1421 — synthesize a default detail page for every entity whose list emits a
    # `/app/<slug>/{id}` row link but which has no explicit `mode: view` surface.
    # The list-table + workspace list regions advertise `/app/<slug>/{id}` for
    # every list entity (server.py), and the converter auto-adds the canonical
    # `/<plural>/{id}` READ — but the app-shell detail page route was previously
    # mounted only from a VIEW surface, so list-only entities 404'd on drill-to-
    # detail. Mirror the converter's auto-READ so the emitted link always resolves.
    if domain:
        _detail_entities: set[str] = set(_list_surfaces_by_entity.keys())
        for _ws in appspec.workspaces:
            for _region in getattr(_ws, "regions", []) or []:
                _src = getattr(_region, "source", None)
                if _src:
                    _detail_entities.add(_src)

        for _entity_ref in sorted(_detail_entities):
            _entity = domain.get_entity(_entity_ref)
            if _entity is None:
                continue
            _slug = app_paths.entity_slug(_entity.name)
            _detail_route = app_paths.detail_path(app_prefix, _slug)
            if _detail_route in contexts:
                continue  # an explicit VIEW surface already provides it

            _synthetic = ir.SurfaceSpec(
                name=f"{_slug}_detail", entity_ref=_entity.name, mode=SurfaceMode.VIEW
            )
            _ctx = compile_surface_to_context(
                _synthetic,
                _entity,
                app_prefix=app_prefix,
                reverse_refs=_reverse_refs.get(_entity.name),
                poly_refs=_poly_refs.get(_entity.name),
                enums=list(appspec.enums) if appspec.enums else None,
                entities_with_create_surface=_entities_with_create_surface,
            )
            _ctx.app_name = appspec.title or appspec.name.replace("_", " ").title()
            _ctx.nav_items = nav_items
            _ctx.nav_by_persona = nav_by_persona
            _ctx.nav_items_anon = [i for i in nav_items if i.route in _anon_safe_routes]
            _ctx.nav_groups_anon = nav_groups_anon
            _ctx.nav_groups = nav_groups_all
            _ctx.nav_groups_by_persona = nav_groups_by_persona
            _ctx.view_name = _synthetic.name
            _ctx.entity_ref = _entity.name
            contexts[_detail_route] = _ctx
            _route_surfaces[_detail_route] = _synthetic

    return contexts
