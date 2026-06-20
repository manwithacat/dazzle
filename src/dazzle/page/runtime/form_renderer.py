"""Form-field renderer (Phase 4, v0.67.74).

Inline Python port of `macros/form_field.html`'s `render_field` macro
plus `fragments/search_select.html` and `fragments/form_stepper.html`.
All branches preserved:
  - field.type == "checkbox" — inline checkbox with wrap label
  - field.source — search-select (was a Jinja include)
  - field.ref_entity — entity-ref combobox (TomSelect with remote load)
  - field.widget in {"combobox", "multi_select", "tags", "picker",
    "range", "color", "rich_text", "slider"} — vendored-widget paths
  - else dispatch on field.type: textarea / select / date / datetime /
    money / number / email / file / default (text)

All Alpine bindings (`x-data`, `:checked`, `@click`, `x-show`, etc.)
are emitted verbatim — the dzMoney / dzFileUpload / dzColorWidget /
dzRangeTooltip Alpine controllers keep working unchanged.

CSS class names match the legacy template byte-for-byte
(`dz-form-*`, `dz-file-upload-*`, etc.) so existing styles continue
to apply.
"""

from __future__ import annotations

import json
from os.path import basename
from typing import Any
from urllib.parse import urlparse

from dazzle.render.html import esc as _esc


def _basename_or_url(value: Any) -> str:
    """Mirror of the `basename_or_url` Jinja filter — return the last
    path segment, or the value verbatim if it's a URL with no path."""
    if value is None:
        return ""
    s = str(value)
    parsed = urlparse(s)
    if parsed.scheme:
        # URL — strip query/fragment, use path basename if present
        path_basename = basename(parsed.path.rstrip("/"))
        return path_basename or s
    return basename(s) or s


def _describedby_attr(field: Any, error: str, *, suffix_help: bool = True) -> str:
    """Build `aria-describedby` attribute when there's an error and/or
    a help message. Returns empty string when neither applies."""
    name = _esc(getattr(field, "name", ""), quote=True)
    help_text = getattr(field, "help", "") or ""
    parts: list[str] = []
    if error:
        parts.append(f"error-{name}")
    if help_text and suffix_help:
        parts.append(f"hint-{name}")
    if not parts:
        return ""
    return f' aria-describedby="{" ".join(parts)}"'


def _required_indicator(field: Any) -> str:
    """The `<span class="dz-form-required">*</span>` + a11y label,
    rendered only when the field is required."""
    if not getattr(field, "required", False):
        return ""
    return (
        '<span class="dz-form-required" aria-hidden="true">*</span>'
        '<span class="visually-hidden">(required)</span>'
    )


def _hint_paragraph(field: Any, hint_id: str) -> str:
    """The optional `<p class="dz-form-hint">` help paragraph."""
    help_text = getattr(field, "help", "") or ""
    if not help_text:
        return ""
    return f'<p id="{hint_id}" class="dz-form-hint">{_esc(help_text)}</p>'


def _error_paragraph(field: Any, error: str, error_id: str) -> str:
    """The optional `<p class="dz-form-error">` error message."""
    if not error:
        return ""
    return f'<p id="{error_id}" class="dz-form-error" role="alert">{_esc(error)}</p>'


def _aria_invalid(error: str) -> str:
    """Inline ` aria-invalid="true"` attr when error is set."""
    return ' aria-invalid="true"' if error else ""


def _required_attrs(field: Any) -> str:
    """Inline ` required aria-required="true"` attr when required."""
    return ' required aria-required="true"' if getattr(field, "required", False) else ""


def _label_block(field: Any, field_id: str) -> str:
    """The standard `<label>` + optional required indicator."""
    field_id_attr = _esc(field_id, quote=True)
    label = _esc(getattr(field, "label", ""))
    return (
        f'<label for="{field_id_attr}" class="dz-form-label">{label}'
        f"{_required_indicator(field)}</label>"
    )


# ---------------------------------------------------------------------------
# Individual variant renderers
# ---------------------------------------------------------------------------


def _render_checkbox(field: Any, value: Any, error: str, hint_id: str) -> str:
    name_attr = _esc(getattr(field, "name", ""), quote=True)
    field_id_attr = _esc(f"field-{getattr(field, 'name', '')}", quote=True)
    label_text = _esc(getattr(field, "label", ""))
    checked_attr = " checked" if value else ""
    return (
        '<label class="dz-form-checkbox-label">'
        f'<input type="checkbox" name="{name_attr}" '  # nosemgrep
        f'id="{field_id_attr}" data-dazzle-field="{name_attr}" '
        f'class="dz-form-checkbox"'
        f"{_aria_invalid(error)}"
        f"{_describedby_attr(field, error)}"
        f"{checked_attr} />"
        f"<span>{label_text}</span>"
        "</label>"
        f"{_hint_paragraph(field, hint_id)}"
    )


def _render_search_select(field: Any, value: Any, errors: dict[str, Any]) -> str:
    """Port of `fragments/search_select.html`."""
    name = getattr(field, "name", "")
    name_attr = _esc(name, quote=True)
    label_text = _esc(getattr(field, "label", ""))
    placeholder_raw = (
        getattr(field, "placeholder", "") or f"Search {getattr(field, 'label', '')}..."
    )
    placeholder_attr = _esc(placeholder_raw, quote=True)
    source = getattr(field, "source", None) or {}
    source_endpoint = _esc(getattr(source, "endpoint", "") or "", quote=True)
    debounce_ms = int(getattr(source, "debounce_ms", 300) or 300)
    min_chars_raw = getattr(source, "min_chars", 0) or 0
    error = errors.get(name, "") if errors else ""

    # Resolve initial value
    init_id = ""
    init_display = ""
    if isinstance(value, dict):
        init_id = str(value.get("id", "") or "")
        init_display = str(
            value.get("name")
            or value.get("title")
            or value.get("label")
            or value.get("email")
            or value.get("id", "")
            or ""
        )
    elif value:
        init_id = str(value)
        init_display = str(value)

    init_id_attr = _esc(init_id, quote=True)
    init_display_attr = _esc(init_display, quote=True)

    hidden_describedby = _describedby_attr(field, error)
    hx_min_chars = f" hx-vals='{{\"min_chars\": {int(min_chars_raw)}}}'" if min_chars_raw else ""
    invalid_attr = ' aria-invalid="true"' if error else ""
    prompt_min_chars = int(min_chars_raw or 0)

    return (
        '<div class="dz-search-select" x-data="{ open: false }" data-dz-widget="search_select">'
        f'<input type="hidden" name="{name_attr}" id="field-{name_attr}" '  # nosemgrep
        f'data-dazzle-field="{name_attr}" '
        f'value="{init_id_attr}"'
        f"{_required_attrs(field)}{hidden_describedby} />"
        '<input type="text" '
        f'id="search-input-{name_attr}" '
        f'class="dz-search-select-input" '
        f'placeholder="{placeholder_attr}" '
        f'autocomplete="off" role="combobox"'
        f"{invalid_attr} "
        ':aria-expanded="open" '
        f'aria-controls="search-results-{name_attr}" '
        f'aria-autocomplete="list" aria-haspopup="listbox" '
        f'value="{init_display_attr}" '
        f'hx-get="{source_endpoint}" '
        f'hx-trigger="keyup changed delay:{debounce_ms}ms" '
        f'hx-target="#search-results-{name_attr}" '
        f'hx-indicator="#search-spinner-{name_attr}" '
        f'hx-params="q"'
        f"{hx_min_chars} "
        '@focus="open = true" '
        '@blur="setTimeout(() => { open = false }, 200)" />'
        f'<span id="search-spinner-{name_attr}" '
        'class="htmx-indicator dz-search-select-spinner" '
        'role="status" aria-label="Searching">'
        '<svg class="dz-search-select-spinner-icon" fill="none" viewBox="0 0 24 24" '
        'aria-hidden="true">'
        '<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" '
        'stroke-width="4"></circle>'
        '<path class="opacity-75" fill="currentColor" '
        'd="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"></path>'
        "</svg></span>"
        f'<div id="search-results-{name_attr}" '
        'x-show="open" x-cloak role="listbox" '
        f'aria-label="{label_text} suggestions" '
        'class="dz-search-select-results">'
        '<div class="dz-search-select-prompt" role="option" aria-disabled="true">'
        f"Type at least {prompt_min_chars} characters to search..."
        "</div></div></div>"
    )


def _render_ref_entity(field: Any, value: Any, error: str, hint_id: str) -> str:
    """Entity-ref combobox (TomSelect with remote load)."""
    name = getattr(field, "name", "")
    name_attr = _esc(name, quote=True)
    field_id_attr = _esc(f"field-{name}", quote=True)
    ref_entity_attr = _esc(getattr(field, "ref_entity", ""), quote=True)
    ref_api_attr = _esc(getattr(field, "ref_api", ""), quote=True)
    placeholder = getattr(field, "placeholder", "")
    placeholder_attr = f' placeholder="{_esc(placeholder, quote=True)}"' if placeholder else ""
    selected_html = ""
    if value:
        v_attr = _esc(value, quote=True)
        v_text = _esc(value)
        selected_html = f'<option value="{v_attr}" selected>{v_text}</option>'
    return (
        f"{_label_block(field, f'field-{name}')}"
        f"{_hint_paragraph(field, hint_id)}"
        f'<select id="{field_id_attr}" name="{name_attr}" '  # nosemgrep
        f'data-dazzle-field="{name_attr}" '
        'data-dz-widget="combobox" '
        f'data-dz-ref-entity="{ref_entity_attr}" '
        f'data-dz-ref-api="{ref_api_attr}" '
        "data-dz-options='{}' "
        'class="dz-form-input"'
        f"{placeholder_attr}{_required_attrs(field)}"
        f"{_aria_invalid(error)}{_describedby_attr(field, error)}>"
        f"{selected_html}</select>"
    )


def _render_combobox(field: Any, value: Any, error: str, hint_id: str) -> str:
    """TomSelect combobox dropdown (widget=combobox)."""
    name = getattr(field, "name", "")
    name_attr = _esc(name, quote=True)
    field_id_attr = _esc(f"field-{name}", quote=True)
    placeholder = getattr(field, "placeholder", "")
    placeholder_attr = f' placeholder="{_esc(placeholder, quote=True)}"' if placeholder else ""
    options: list[str] = []
    options.append(f'<option value="">{_esc(placeholder or "Select...")}</option>')
    str_value = str(value) if value is not None else None
    for opt in getattr(field, "options", None) or []:
        opt_value_raw = opt.get("value") if isinstance(opt, dict) else getattr(opt, "value", "")
        opt_label_raw = opt.get("label") if isinstance(opt, dict) else getattr(opt, "label", "")
        sel = " selected" if str_value is not None and str(opt_value_raw) == str_value else ""
        options.append(
            f'<option value="{_esc(opt_value_raw, quote=True)}"{sel}>{_esc(opt_label_raw)}</option>'
        )
    return (
        f"{_label_block(field, f'field-{name}')}"
        f"{_hint_paragraph(field, hint_id)}"
        f'<select id="{field_id_attr}" name="{name_attr}" '  # nosemgrep
        'data-dz-widget="combobox" '
        "data-dz-options='{}' "
        'class="dz-form-input"'
        f"{placeholder_attr}{_required_attrs(field)}"
        f"{_aria_invalid(error)}{_describedby_attr(field, error)}>"
        f"{''.join(options)}</select>"
    )


def _render_multi_select(field: Any, value: Any, error: str, hint_id: str) -> str:
    name = getattr(field, "name", "")
    name_attr = _esc(name, quote=True)
    field_id_attr = _esc(f"field-{name}", quote=True)
    placeholder = getattr(field, "placeholder", "")
    placeholder_attr = f' placeholder="{_esc(placeholder, quote=True)}"' if placeholder else ""
    selected_set = {str(v) for v in (value or [])} if isinstance(value, list) else set()
    options: list[str] = []
    for opt in getattr(field, "options", None) or []:
        opt_value_raw = opt.get("value") if isinstance(opt, dict) else getattr(opt, "value", "")
        opt_label_raw = opt.get("label") if isinstance(opt, dict) else getattr(opt, "label", "")
        sel = " selected" if str(opt_value_raw) in selected_set else ""
        options.append(
            f'<option value="{_esc(opt_value_raw, quote=True)}"{sel}>{_esc(opt_label_raw)}</option>'
        )
    return (
        f"{_label_block(field, f'field-{name}')}"
        f"{_hint_paragraph(field, hint_id)}"
        f'<select id="{field_id_attr}" name="{name_attr}" '  # nosemgrep
        'data-dz-widget="multiselect" '
        'data-dz-options=\'{"plugins":["remove_button"]}\' '
        'class="dz-form-input" multiple'
        f"{placeholder_attr}{_required_attrs(field)}"
        f"{_aria_invalid(error)}{_describedby_attr(field, error)}>"
        f"{''.join(options)}</select>"
    )


def _render_tags(field: Any, value: Any, error: str, hint_id: str) -> str:
    name = getattr(field, "name", "")
    name_attr = _esc(name, quote=True)
    field_id_attr = _esc(f"field-{name}", quote=True)
    placeholder = getattr(field, "placeholder", "")
    placeholder_attr = f' placeholder="{_esc(placeholder, quote=True)}"' if placeholder else ""
    value_attr = _esc(value if value is not None else "", quote=True)
    return (
        f"{_label_block(field, f'field-{name}')}"
        f"{_hint_paragraph(field, hint_id)}"
        f'<input id="{field_id_attr}" name="{name_attr}" type="text" '  # nosemgrep
        'data-dz-widget="tags" '
        'data-dz-options=\'{"create":true,"plugins":["remove_button"]}\' '
        f'class="dz-form-input" value="{value_attr}"'
        f"{placeholder_attr}{_required_attrs(field)}"
        f"{_aria_invalid(error)}{_describedby_attr(field, error)} />"
    )


def _render_date_picker(field: Any, value: Any, error: str, hint_id: str) -> str:
    """Flatpickr single-date picker (widget=picker, type in date/datetime)."""
    name = getattr(field, "name", "")
    name_attr = _esc(name, quote=True)
    field_id_attr = _esc(f"field-{name}", quote=True)
    ftype = str(getattr(field, "type", "") or "")
    is_datetime = ftype == "datetime"
    date_format = "Y-m-d H:i" if is_datetime else "Y-m-d"
    enable_time = ',"enableTime":true' if is_datetime else ""
    placeholder = getattr(field, "placeholder", "")
    placeholder_attr = f' placeholder="{_esc(placeholder, quote=True)}"' if placeholder else ""
    fallback = value if value not in (None, "") else getattr(field, "default", "") or ""
    value_attr = _esc(fallback, quote=True)
    return (
        f"{_label_block(field, f'field-{name}')}"
        f"{_hint_paragraph(field, hint_id)}"
        f'<input id="{field_id_attr}" name="{name_attr}" type="text" '  # nosemgrep
        'data-dz-widget="datepicker" '
        f'data-dz-options=\'{{"dateFormat":"{date_format}"{enable_time}}}\' '
        f'class="dz-form-input" value="{value_attr}"'
        f"{placeholder_attr}{_required_attrs(field)}"
        f"{_aria_invalid(error)}{_describedby_attr(field, error)} />"
    )


def _render_date_range(field: Any, value: Any, error: str, hint_id: str) -> str:
    """Flatpickr range picker (widget=range, type in date/datetime)."""
    name = getattr(field, "name", "")
    name_attr = _esc(name, quote=True)
    field_id_attr = _esc(f"field-{name}", quote=True)
    placeholder_raw = getattr(field, "placeholder", "") or "Select date range..."
    placeholder_attr = _esc(placeholder_raw, quote=True)
    value_attr = _esc(value if value is not None else "", quote=True)
    return (
        f"{_label_block(field, f'field-{name}')}"
        f"{_hint_paragraph(field, hint_id)}"
        f'<input id="{field_id_attr}" name="{name_attr}" type="text" '  # nosemgrep
        'data-dz-widget="daterange" '
        'data-dz-options=\'{"mode":"range","dateFormat":"Y-m-d"}\' '
        f'class="dz-form-input" value="{value_attr}" '
        f'placeholder="{placeholder_attr}"'
        f"{_required_attrs(field)}"
        f"{_aria_invalid(error)}{_describedby_attr(field, error)} />"
    )


def _render_color(field: Any, value: Any, error: str, hint_id: str) -> str:
    name = getattr(field, "name", "")
    name_attr = _esc(name, quote=True)
    field_id_attr = _esc(f"field-{name}", quote=True)
    initial_value_raw = (
        value if value not in (None, "") else (getattr(field, "default", "") or "#3b82f6")
    )
    init_attr = _esc(initial_value_raw, quote=True)
    init_text = _esc(initial_value_raw)
    return (
        f"{_label_block(field, f'field-{name}')}"
        f"{_hint_paragraph(field, hint_id)}"
        f'<div class="dz-form-color-group" '  # nosemgrep
        f"x-data=\"{{ value: '{init_attr}' }}\">"
        f'<input type="color" id="{field_id_attr}" '
        f'name="{name_attr}" '
        'class="dz-form-color-input" '
        'x-model="value"'
        f"{_required_attrs(field)}"
        f"{_aria_invalid(error)}{_describedby_attr(field, error)}>"
        '<span class="dz-form-color-hex" aria-hidden="true" '
        f'x-text="value">{init_text}</span>'
        "</div>"
    )


def _render_rich_text(field: Any, value: Any, error: str, hint_id: str) -> str:
    name = getattr(field, "name", "")
    name_attr = _esc(name, quote=True)
    field_id_attr = _esc(f"field-{name}", quote=True)
    value_attr = _esc(value if value is not None else "", quote=True)
    rt_opts: dict[str, Any] = {}
    extra = getattr(field, "extra", None) or {}
    if isinstance(extra, dict):
        if extra.get("rich_text_toolbar"):
            rt_opts["toolbar"] = extra["rich_text_toolbar"]
        if extra.get("rich_text_max_length"):
            rt_opts["maxLength"] = extra["rich_text_max_length"]
    rt_opts_json = _esc(json.dumps(rt_opts), quote=True)
    invalid_outer = ' aria-invalid="true"' if error else ""
    return (
        f"{_label_block(field, f'field-{name}')}"
        f"{_hint_paragraph(field, hint_id)}"
        '<div data-dz-widget="richtext" '
        f"data-dz-options='{rt_opts_json}' "
        f'class="dz-form-richtext"{invalid_outer}>'
        f'<input type="hidden" id="{field_id_attr}" name="{name_attr}" '  # nosemgrep
        f'value="{value_attr}"'
        f"{_required_attrs(field)}"
        f"{_aria_invalid(error)}{_describedby_attr(field, error)}>"
        "<div data-dz-editor></div>"
        "</div>"
    )


def _render_slider(field: Any, value: Any, error: str, hint_id: str) -> str:
    name = getattr(field, "name", "")
    name_attr = _esc(name, quote=True)
    field_id_attr = _esc(f"field-{name}", quote=True)
    extra = getattr(field, "extra", None) or {}
    if not isinstance(extra, dict):
        extra = {}
    min_val = extra.get("min", 0)
    max_val = extra.get("max", 100)
    step_val = extra.get("step", 1)
    fallback = value if value not in (None, "") else getattr(field, "default", "") or "50"
    value_attr = _esc(fallback, quote=True)
    value_text = _esc(fallback)
    return (
        f"{_label_block(field, f'field-{name}')}"
        f"{_hint_paragraph(field, hint_id)}"
        '<div data-dz-widget="range-tooltip" class="dz-form-slider-group">'
        f'<input id="{field_id_attr}" name="{name_attr}" type="range" '  # nosemgrep
        'data-dz-slider class="dz-form-slider" '
        f'min="{_esc(min_val, quote=True)}" '
        f'max="{_esc(max_val, quote=True)}" '
        f'step="{_esc(step_val, quote=True)}" '
        f'value="{value_attr}"'
        f"{_required_attrs(field)}"
        f"{_aria_invalid(error)}{_describedby_attr(field, error)}>"
        '<span data-dz-range-value class="dz-form-slider-value" '
        f'aria-hidden="true">{value_text}</span>'
        "</div>"
    )


def _render_textarea(field: Any, value: Any, error: str, hint_id: str) -> str:
    name = getattr(field, "name", "")
    name_attr = _esc(name, quote=True)
    field_id_attr = _esc(f"field-{name}", quote=True)
    placeholder_attr = _esc(getattr(field, "placeholder", "") or "", quote=True)
    value_text = _esc(value if value is not None else "")
    return (
        f'<textarea id="{field_id_attr}" name="{name_attr}" '  # nosemgrep
        f'data-dazzle-field="{name_attr}" '
        f'class="dz-form-input dz-form-textarea" '
        f'placeholder="{placeholder_attr}"'
        f"{_required_attrs(field)}"
        f"{_aria_invalid(error)}{_describedby_attr(field, error)} "
        f'rows="4">{value_text}</textarea>'
    )


def _render_select(field: Any, value: Any, error: str, hint_id: str) -> str:
    name = getattr(field, "name", "")
    name_attr = _esc(name, quote=True)
    field_id_attr = _esc(f"field-{name}", quote=True)
    placeholder_text = getattr(field, "placeholder", "") or f"Select {getattr(field, 'label', '')}"
    placeholder_html = _esc(placeholder_text)
    options: list[str] = []
    options.append(
        f'<option value="" disabled{" selected" if not value else ""}>{placeholder_html}</option>'
    )
    for opt in getattr(field, "options", None) or []:
        opt_value_raw = opt.get("value") if isinstance(opt, dict) else getattr(opt, "value", "")
        opt_label_raw = opt.get("label") if isinstance(opt, dict) else getattr(opt, "label", "")
        sel = " selected" if value is not None and value == opt_value_raw else ""
        options.append(
            f'<option value="{_esc(opt_value_raw, quote=True)}"{sel}>{_esc(opt_label_raw)}</option>'
        )
    return (
        f'<select id="{field_id_attr}" name="{name_attr}" '  # nosemgrep
        f'data-dazzle-field="{name_attr}" '
        f'class="dz-form-input"'
        f"{_required_attrs(field)}"
        f"{_aria_invalid(error)}{_describedby_attr(field, error)}>"
        f"{''.join(options)}</select>"
    )


def _render_input(
    field: Any,
    value: Any,
    error: str,
    *,
    input_type: str,
) -> str:
    """text / number / email / date / datetime inputs."""
    name = getattr(field, "name", "")
    name_attr = _esc(name, quote=True)
    field_id_attr = _esc(f"field-{name}", quote=True)
    value_attr = _esc(value if value is not None else "", quote=True)
    placeholder_attr = _esc(getattr(field, "placeholder", "") or "", quote=True)
    placeholder_html = (
        f' placeholder="{placeholder_attr}"' if input_type not in ("date", "datetime-local") else ""
    )
    return (
        f'<input id="{field_id_attr}" type="{input_type}" name="{name_attr}" '  # nosemgrep
        f'data-dazzle-field="{name_attr}" '
        f'class="dz-form-input" '
        f'value="{value_attr}"'
        f"{placeholder_html}"
        f"{_required_attrs(field)}"
        f"{_aria_invalid(error)}{_describedby_attr(field, error)} />"
    )


def _render_money(field: Any, value: Any, error: str, hint_id: str, values: dict[str, Any]) -> str:
    name = getattr(field, "name", "")
    name_attr = _esc(name, quote=True)
    field_id_attr = _esc(f"field-{name}", quote=True)
    label_text = _esc(getattr(field, "label", ""))
    extra = getattr(field, "extra", None) or {}
    if not isinstance(extra, dict):
        extra = {}
    minor_val = ""
    if values:
        minor_val = str(values.get(f"{name}_minor", "") or "")
    minor_attr = _esc(minor_val, quote=True)
    currency_code = extra.get("currency_code", "")
    scale = extra.get("scale", "")
    symbol = extra.get("symbol", "")
    currency_fixed = extra.get("currency_fixed", True)

    if currency_fixed:
        return (
            '<div x-data="dzMoney" '  # nosemgrep
            f'data-dz-currency="{_esc(currency_code, quote=True)}" '
            f'data-dz-scale="{_esc(scale, quote=True)}">'
            '<div class="dz-form-money-group">'
            f'<span class="dz-form-money-prefix" aria-hidden="true">{_esc(symbol)}</span>'
            f'<input type="text" inputmode="decimal" id="{field_id_attr}" '
            f'data-dazzle-field="{name_attr}" '
            'x-model="displayValue" @input="onInput()" @blur="onBlur()" '
            'class="dz-form-input dz-form-input-trailing" '
            'placeholder="0.00" '
            f'aria-label="{label_text} ({_esc(currency_code)})"'
            f"{_required_attrs(field)}"
            f"{_aria_invalid(error)}{_describedby_attr(field, error)} />"
            "</div>"
            f'<input type="hidden" name="{name_attr}_minor" x-model="minorValue" '
            f"x-init=\"minorValue = '{minor_attr}'\" />"
            f'<input type="hidden" name="{name_attr}_currency" '
            f'value="{_esc(currency_code, quote=True)}" />'
            "</div>"
        )
    # Unpinned currency selector
    currency_opts: list[str] = []
    for opt in extra.get("currency_options", []) or []:
        code = opt.get("code", "") if isinstance(opt, dict) else getattr(opt, "code", "")
        opt_scale = opt.get("scale", "") if isinstance(opt, dict) else getattr(opt, "scale", "")
        opt_symbol = opt.get("symbol", "") if isinstance(opt, dict) else getattr(opt, "symbol", "")
        sel = " selected" if code == currency_code else ""
        currency_opts.append(
            f'<option value="{_esc(code, quote=True)}" '  # nosemgrep
            f'data-scale="{_esc(opt_scale, quote=True)}" '
            f'data-symbol="{_esc(opt_symbol, quote=True)}"{sel}>'
            f"{_esc(opt_symbol)} {_esc(code)}</option>"
        )
    return (
        f'<div x-data="dzMoney" data-dz-scale="{_esc(scale, quote=True)}">'  # nosemgrep
        '<div class="dz-form-money-group">'
        f'<select name="{name_attr}_currency" '
        '@change="onCurrencyChange($event)" '
        'class="dz-form-money-select" '
        f'aria-label="Currency for {label_text}">'
        f"{''.join(currency_opts)}"
        "</select>"
        f'<input type="text" inputmode="decimal" id="{field_id_attr}" '
        f'data-dazzle-field="{name_attr}" '
        'x-model="displayValue" @input="onInput()" @blur="onBlur()" '
        'class="dz-form-input dz-form-input-trailing" '
        'placeholder="0.00" '
        f'aria-label="{label_text}"'
        f"{_required_attrs(field)}"
        f"{_aria_invalid(error)}{_describedby_attr(field, error)} />"
        "</div>"
        f'<input type="hidden" name="{name_attr}_minor" x-model="minorValue" '
        f"x-init=\"minorValue = '{minor_attr}'\" />"
        "</div>"
    )


def _render_file(field: Any, value: Any, error: str) -> str:
    name = getattr(field, "name", "")
    name_attr = _esc(name, quote=True)
    field_id_attr = _esc(f"field-{name}", quote=True)
    value_attr = _esc(value if value is not None else "", quote=True)
    extra = getattr(field, "extra", None) or {}
    if not isinstance(extra, dict):
        extra = {}
    accept_attr = _esc(extra.get("accept", "*/*"), quote=True)
    capture_val = extra.get("capture")
    capture_attr = f' capture="{_esc(capture_val, quote=True)}"' if capture_val else ""
    # #1213: file ui_mode threads through `extra["ui_mode"]`. Emit a
    # data-dz-file-mode attr so dzFileUpload.upload() can branch on it
    # at the JS layer (ticket flow vs simple /files/upload POST).
    ui_mode = extra.get("ui_mode")
    ui_mode_attr = f' data-dz-file-mode="{_esc(ui_mode, quote=True)}"' if ui_mode else ""
    init_filename = _basename_or_url(value) if value else ""
    x_init_attr = ""
    if value:
        x_init_attr = f" x-init='hasFile = true; filename = {json.dumps(init_filename)}'"
    required_when_empty = ""
    if getattr(field, "required", False) and not value:
        required_when_empty = ' required aria-required="true"'

    return (
        f'<div x-data="dzFileUpload" data-dz-file="{name_attr}"{ui_mode_attr} '  # nosemgrep
        f'class="dz-file-upload"{x_init_attr}>'
        f'<input type="hidden" name="{name_attr}" id="{field_id_attr}" '
        f'data-dazzle-field="{name_attr}" data-dz-file-value '
        f'value="{value_attr}"'
        f"{_aria_invalid(error)}{_describedby_attr(field, error)} />"
        '<div x-show="hasFile" class="dz-file-upload-preview">'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'class="dz-file-upload-preview-icon" fill="none" viewBox="0 0 24 24" '
        'stroke="currentColor" aria-hidden="true">'
        '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" '
        'd="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>'
        '<span class="dz-file-upload-preview-name" x-text="filename"></span>'
        '<button type="button" @click="clear()" '
        'class="dz-file-upload-preview-clear" aria-label="Remove file">'
        '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" '
        'fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">'
        '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" '
        'd="M6 18L18 6M6 6l12 12" /></svg></button></div>'
        '<label x-show="!hasFile" '
        '@dragover.prevent="dragging = true" '
        '@dragleave="dragging = false" '
        '@drop="onDrop($event)" '
        ":class=\"dragging && 'dragging'\" "
        'class="dz-file-upload-zone">'
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'class="dz-file-upload-zone-icon" fill="none" viewBox="0 0 24 24" '
        'stroke="currentColor" aria-hidden="true">'
        '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" '
        'd="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 '
        '0l-3 3m3-3v12" /></svg>'
        '<p class="dz-file-upload-zone-prompt">Click to upload or drag and drop</p>'
        '<input type="file" hidden data-dz-file-input '
        '@change="selectFile($event)" '
        f'accept="{accept_attr}"'
        f"{capture_attr}{required_when_empty} />"
        "</label>"
        '<div x-show="uploading">'
        '<progress data-dz-file-progress class="dz-file-upload-progress" '
        ':value="progress" max="100"></progress></div>'
        '<p x-show="error" class="dz-form-error" x-text="error" role="alert"></p>'
        "</div>"
    )


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def render_form_field(
    field: Any,
    values: dict[str, Any] | None = None,
    errors: dict[str, Any] | None = None,
) -> str:
    """Render one form field — port of `macros/form_field.html::render_field`.

    Returns the HTML string the field would have produced via Jinja.
    """
    values = values or {}
    errors = errors or {}
    name = getattr(field, "name", "")
    field_id = f"field-{name}"
    error_id = f"error-{name}"
    hint_id = f"hint-{name}" if getattr(field, "help", "") else ""

    fallback = getattr(field, "default", None)
    value = values.get(name, fallback) if values else fallback
    error = str(errors.get(name, "") or "") if errors else ""

    ftype = str(getattr(field, "type", "") or "")
    widget = getattr(field, "widget", None)
    has_source = bool(getattr(field, "source", None))
    has_ref_entity = bool(getattr(field, "ref_entity", ""))

    if ftype == "checkbox":
        body = _render_checkbox(field, value, error, hint_id)
    elif has_source:
        body = (
            f"{_label_block(field, f'search-input-{name}')}"
            f"{_hint_paragraph(field, hint_id)}"
            f"{_render_search_select(field, value, errors)}"
        )
    elif has_ref_entity:
        body = _render_ref_entity(field, value, error, hint_id)
    elif widget == "combobox":
        body = _render_combobox(field, value, error, hint_id)
    elif widget == "multi_select":
        body = _render_multi_select(field, value, error, hint_id)
    elif widget == "tags":
        body = _render_tags(field, value, error, hint_id)
    elif widget == "picker" and ftype in ("date", "datetime"):
        body = _render_date_picker(field, value, error, hint_id)
    elif widget == "range" and ftype in ("date", "datetime"):
        body = _render_date_range(field, value, error, hint_id)
    elif widget == "color":
        body = _render_color(field, value, error, hint_id)
    elif widget == "rich_text":
        body = _render_rich_text(field, value, error, hint_id)
    elif widget == "slider":
        body = _render_slider(field, value, error, hint_id)
    else:
        # Standard fields with label above
        label_html = _label_block(field, field_id)
        hint_html = _hint_paragraph(field, hint_id)

        if ftype == "textarea":
            inner = _render_textarea(field, value, error, hint_id)
        elif ftype == "select":
            inner = _render_select(field, value, error, hint_id)
        elif ftype == "date":
            inner = _render_input(field, value, error, input_type="date")
        elif ftype == "datetime":
            inner = _render_input(field, value, error, input_type="datetime-local")
        elif ftype == "money":
            inner = _render_money(field, value, error, hint_id, values)
        elif ftype == "number":
            inner = _render_input(field, value, error, input_type="number")
        elif ftype == "email":
            inner = _render_input(field, value, error, input_type="email")
        elif ftype == "file":
            inner = _render_file(field, value, error)
        else:
            inner = _render_input(field, value, error, input_type="text")
        body = f"{label_html}{hint_html}{inner}"

    return f'<div class="dz-form-field">{body}{_error_paragraph(field, error, error_id)}</div>'


def render_form_stepper(form_ctx: Any) -> str:
    """Port of `fragments/form_stepper.html` — the wizard stage tabs.

    Alpine-driven: `step` is the current wizard index (live on the
    surrounding dzWizard scope). The stepper renders checkmark SVGs
    for completed stages and the bare index for the current/pending
    ones; `isActive()` and `isCurrent()` are dzWizard helpers.
    """
    sections = getattr(form_ctx, "sections", None) or []
    if not sections:
        return ""
    n = len(sections)
    items: list[str] = []
    for idx, section in enumerate(sections):
        title = (
            section.get("title", "") if isinstance(section, dict) else getattr(section, "title", "")
        )
        title_html = _esc(title)
        is_last = idx == n - 1
        not_last_cls = "" if is_last else " is-not-last"
        connector = ""
        if not is_last:
            connector = (
                '<span class="dz-form-stepper-connector" '  # nosemgrep
                f":class=\"{{ 'is-active': isActive({idx + 1}) }}\" "
                'aria-hidden="true"></span>'
            )
        items.append(
            f'<li class="dz-form-stepper-item{not_last_cls}" '  # nosemgrep
            f'@click="goToStep({idx})" '
            f":aria-current=\"isCurrent({idx}) ? 'step' : false\">"
            '<span class="dz-form-stepper-circle" '
            f":class=\"{{ 'is-active': isActive({idx}) }}\">"
            f'<template x-if="step > {idx}">'
            '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" '
            'stroke="currentColor" stroke-width="3" aria-hidden="true">'
            '<path stroke-linecap="round" stroke-linejoin="round" '
            'd="M5 13l4 4L19 7" /></svg></template>'
            f'<template x-if="step <= {idx}"><span>{idx + 1}</span></template>'
            "</span>"
            '<span class="dz-form-stepper-label" '
            f":class=\"{{ 'is-active': isActive({idx}) }}\">{title_html}</span>"
            '<span class="visually-hidden" '
            f"x-text=\"step > {idx} ? 'completed' : "
            f"(isCurrent({idx}) ? 'current' : 'pending')\"></span>"
            f"{connector}"
            "</li>"
        )
    return (
        f'<ol class="dz-form-stepper" role="list" aria-label="Form progress">{"".join(items)}</ol>'
    )
