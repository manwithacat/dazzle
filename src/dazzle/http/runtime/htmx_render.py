"""Inline HTMX / HTML response rendering for generated routes.

Extracted verbatim from ``route_generator.py`` (#1361 slice 2). This is the
HTMX renderer family: the inline mirrors of the retired Jinja list-fragment
templates (table rows / cells / inline edit / empty state / pagination /
infinite-scroll sentinel, v0.67.65-v0.67.68), the detail-fields fragment
renderer (``_render_detail_html``, v0.67.64), and the HX-Trigger mutation
response wrapper (``_with_htmx_triggers``). All HTML is built with
``html.escape`` on the typed-Fragment substrate; no Jinja2 (#1042,
ADR-0023). This module is listed in
``tests/unit/test_typed_runtime_no_jinja.py`` so the gate keeps covering
the moved HTML.

A leaf module by design: it must not import ``route_generator`` at module
level (``route_generator`` imports these names back at module level so the
``route_generator.X`` call sites, patch points, and re-exports keep
working). The shared HTMX request utils it needs (``_is_htmx_request`` /
``_wants_html``) come from the ``route_support`` leaf at top level —
extracted there in the 2026-06-20 smells round to break the import cycle
that previously forced lazy in-function imports.

Deliberately NOT named ``*_routes.py`` — the runtime-urls api-surface walker
globs that pattern and this module defines no routes.
"""

import logging
from typing import Any

from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse, JSONResponse

from dazzle.http.runtime.htmx_response import htmx_trigger_headers

# Shared CRUD route-dispatch surface — from the route_support LEAF (smells round
# 2026-06-20). Was lazily imported from route_generator to dodge an import cycle;
# route_support is a leaf, so these are now plain top-level imports.
from dazzle.http.runtime.route_support import (
    _is_htmx_request,
    _wants_html,
)

logger = logging.getLogger(__name__)


def _build_table_url_params(table: dict[str, Any], page: int, *, with_search: bool = True) -> str:
    """Construct the query string used by `_render_table_*` (URL parts only,
    no leading `?`). Mirrors the legacy Jinja template's per-attr concat
    so the output is byte-equivalent."""
    import html as _html_mod

    parts = [f"page={page}", f"page_size={table.get('page_size', 50)}"]
    if table.get("sort_field"):
        parts.append(f"sort={_html_mod.escape(str(table['sort_field']), quote=True)}")
        parts.append(f"dir={_html_mod.escape(str(table.get('sort_dir', '')), quote=True)}")
    if with_search and table.get("search_query"):
        parts.append(f"search={_html_mod.escape(str(table['search_query']), quote=True)}")
    for k, v in (table.get("filter_values") or {}).items():
        k_attr = _html_mod.escape(str(k), quote=True)
        v_attr = _html_mod.escape(str(v), quote=True)
        parts.append(f"filter[{k_attr}]={v_attr}")
    return "&amp;".join(parts)


def _render_table_pagination(table: dict[str, Any]) -> str:
    """Inline mirror of `fragments/table_pagination.html` (v0.67.65).

    Emits the pagination summary + ellipsis-collapsed page buttons.
    Returns empty string when `total <= page_size` (matches Jinja `{% if %}`)."""
    import html as _html_mod

    from dazzle.render.filters import _pagination_pages

    if not table:
        return ""
    total = int(table.get("total", 0) or 0)
    page_size = int(table.get("page_size", 50) or 50)
    if total <= page_size:
        return ""
    total_pages = (total + page_size - 1) // page_size
    current_page = int(table.get("page", 1) or 1)
    table_id = _html_mod.escape(str(table.get("table_id") or "dt-table"), quote=True)
    endpoint_attr = _html_mod.escape(str(table.get("api_endpoint", "") or ""), quote=True)
    rows_label = "row" if total == 1 else "rows"

    buttons: list[str] = []
    for p in _pagination_pages(current_page, total_pages):
        if p is None:
            buttons.append('<span class="dz-pagination-ellipsis" aria-hidden="true">…</span>')
            continue
        is_current = p == current_page
        current_cls = " is-current" if is_current else ""
        current_attr = ' aria-current="page"' if is_current else ""
        url_q = _build_table_url_params(table, p)
        buttons.append(
            f'<button class="dz-pagination-page{current_cls}"{current_attr} '  # nosemgrep
            f'hx-get="{endpoint_attr}?{url_q}" '
            f'hx-target="#{table_id}-body" '
            f'hx-swap="innerMorph" '
            f'hx-headers=\'{{"Accept": "text/html"}}\' '
            f'hx-indicator="#{table_id}-loading">{p}</button>'
        )

    return (
        '<div class="dz-pagination">'
        '<span class="dz-pagination-summary">'
        '<span class="dz-bulk-summary-selected">'
        f"<span data-dz-bulk-count-target>0</span> of {total} selected"
        "</span>"
        f'<span class="dz-bulk-summary-rows">{total} {rows_label}</span>'
        "</span>"
        f'<div class="dz-pagination-pages">{"".join(buttons)}</div>'
        "</div>"
    )


def _render_inline_edit(item: dict[str, Any], col: dict[str, Any], value: Any) -> str:
    """Inline mirror of `fragments/inline_edit.html` (v0.67.68).

    4 input variants keyed off `col.type`:
      - text (default)
      - bool (checkbox)
      - badge (enum select)
      - date (date input)
    All variants emit identical Alpine bindings the legacy template did
    so the dzTable controller (`editing`, `commitEdit`, `cancelEdit`,
    `isEditing`) keeps working unchanged.
    """
    import html as _html_mod
    import json

    col_key = _html_mod.escape(str(col.get("key", "")), quote=True)
    col_type = str(col.get("type", "") or "")
    col_label = _html_mod.escape(str(col.get("label", "")), quote=True)

    if col_type == "bool":
        checked_init = "true" if value else "false"
        editor = (
            '<div class="dz-inline-edit-bool-row">'
            f'<input type="checkbox" name="{col_key}" '  # nosemgrep
            f":checked=\"editing ? (editing.originalValue === 'true' || "
            f'editing.originalValue === true) : {checked_init}" '
            f':disabled="editing && editing.saving" '
            f'x-init="$el.focus()" '
            f'@change="commitEdit($el.checked)" '
            f'@keydown.escape.prevent="cancelEdit()" '
            f'class="dz-inline-edit-checkbox" '
            f'aria-label="Edit {col_label}" />'
            f'<label class="dz-inline-edit-bool-label">{col_label}</label>'
            "</div>"
        )
    elif col_type == "badge":
        opts: list[str] = []
        for opt in col.get("filter_options", []) or []:
            opt_value = _html_mod.escape(str(opt.get("value", "")), quote=True)
            opt_label = _html_mod.escape(str(opt.get("label", "")), quote=False)
            selected = " selected" if str(opt.get("value", "")) == str(value) else ""
            opts.append(f'<option value="{opt_value}"{selected}>{opt_label}</option>')
        editor = (
            f'<select name="{col_key}" '  # nosemgrep
            f':disabled="editing && editing.saving" '
            f'x-init="$el.focus()" '
            f'@change="commitEdit($el.value)" '
            f'@keydown.escape.prevent="cancelEdit()" '
            f':data-dz-edit-error="!!(editing && editing.error)" '
            f'class="dz-inline-edit-input dz-inline-edit-select" '
            f'aria-label="Edit {col_label}">'
            f"{''.join(opts)}</select>"
        )
    else:
        # text or date variant
        editor_value_json = json.dumps(value if value is not None else "")
        input_type = "date" if col_type == "date" else "text"
        editor = (
            f'<input type="{input_type}" name="{col_key}" '  # nosemgrep
            f":value='editing ? editing.originalValue : {editor_value_json}' "
            f':disabled="editing && editing.saving" '
            f'x-init="$el.focus(); $el.select()" '
            f'@keydown.enter.prevent="commitEdit($el.value)" '
            f'@keydown.tab.prevent="commitEdit($el.value)" '
            f'@keydown.escape.prevent="cancelEdit()" '
            f':data-dz-edit-error="!!(editing && editing.error)" '
            f'class="dz-inline-edit-input" '
            f'aria-label="Edit {col_label}" />'
        )

    spinner = (
        '<div x-show="editing && editing.saving" aria-hidden="true" '
        'class="dz-inline-edit-spinner">'
        '<svg class="dz-inline-edit-spinner-icon" viewBox="0 0 24 24" '
        'fill="none" xmlns="http://www.w3.org/2000/svg">'
        '<circle class="opacity-25" cx="12" cy="12" r="10" '
        'stroke="currentColor" stroke-width="2"/>'
        '<path class="opacity-75" fill="currentColor" '
        'd="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>'
        "</svg></div>"
    )
    error = (
        '<div x-show="editing && editing.error" '
        'x-text="editing && editing.error" role="alert" '
        'class="dz-inline-edit-error"></div>'
    )
    return f'<div class="dz-inline-edit">{editor}{spinner}{error}</div>'


def _render_cell_display(col: dict[str, Any], value: Any) -> str:
    """Render the display-mode value for one table cell.

    Mirrors the type-dispatch in `table_rows.html` (badge / bool /
    date / currency / sensitive / ref / percentage / text default).
    """
    import html as _html_mod

    from dazzle.render.filters import (
        _bool_icon_filter,
        _currency_filter,
        _date_filter,
        _ref_display_name,
        _truncate_filter,
    )

    col_type = str(col.get("type", "") or "")
    if col_type == "badge":
        if value in (None, "", "—"):
            return '<span class="dz-badge-empty" aria-label="No status">—</span>'
        # #1493 slice 2: a declared `semantic:` binding (col["semantic_map"]) wins
        # over the spelling-based name guess; None/empty → byte-identical default.
        from dazzle.render.filters import badge_icon_html, resolve_status_tone

        tone = resolve_status_tone(value, col.get("semantic_map"))
        label = str(value).replace("_", " ").title()
        # #1493 slice 2 part 3: WCAG colour+icon+text (neutral → "" = unchanged).
        icon = badge_icon_html(tone)
        return (
            f'<span class="dz-badge" data-dz-tone="{_html_mod.escape(tone, quote=True)}" '
            f'role="status" aria-label="Status: {_html_mod.escape(label, quote=True)}">'
            f"{icon}{_html_mod.escape(label, quote=False)}</span>"
        )
    if col_type == "bool":
        # `_bool_icon_filter` returns Markup with raw HTML — safe to emit.
        return str(_bool_icon_filter(value))
    if col_type == "date":
        return _html_mod.escape(_date_filter(value), quote=False)
    if col_type == "currency":
        currency_code = col.get("currency_code") or "GBP"
        return _html_mod.escape(_currency_filter(value, currency_code), quote=False)
    if col_type == "sensitive":
        raw = "" if value is None else str(value)
        if len(raw) > 4:
            return f"****{_html_mod.escape(raw[-4:], quote=False)}"
        if raw:
            return "****"
        return ""
    if col_type == "ref":
        # Prefer explicit `_display` column; otherwise resolve the dict.
        explicit = ""
        # The caller supplies the row item; the column-level display
        # column key is `<col.key>_display` per legacy convention. Look
        # up the original `value` and the explicit pair.
        if isinstance(value, dict):
            return _html_mod.escape(_ref_display_name(value), quote=False)
        return _html_mod.escape(explicit or str(value or ""), quote=False)
    if col_type == "percentage":
        if value is None:
            return "—"
        return _html_mod.escape(f"{value}%", quote=False)
    # Default text cell — truncated.
    return (
        '<span class="dz-tr-cell-truncate">'
        f"{_html_mod.escape(_truncate_filter(value or ''), quote=False)}"
        "</span>"
    )


def _render_table_row(table: dict[str, Any], item: dict[str, Any]) -> str:
    """Inline mirror of `fragments/table_rows.html`'s row branch (v0.67.68).

    Emits the `<tr>` for one row including:
      - row-state Alpine binds (is-selected / is-saving / is-error)
      - optional checkbox cell when `bulk_actions` is set
      - per-column data cells (inline-editable + display dispatch)
      - hover row-action buttons (view / edit / delete)
    """
    import html as _html_mod
    import json

    from dazzle.render.filters import _ref_display_name

    columns = table.get("columns") or []
    bulk_actions = bool(table.get("bulk_actions"))
    detail_url_template = table.get("detail_url_template") or ""
    entity_name = str(table.get("entity_name") or "Item")
    entity_name_attr = _html_mod.escape(entity_name, quote=True)
    entity_name_lower = entity_name.lower()
    api_endpoint = _html_mod.escape(str(table.get("api_endpoint", "") or ""), quote=True)
    inline_editable = set(table.get("inline_editable") or [])

    item_id = str(item.get("id", "") or "")
    item_id_attr = _html_mod.escape(item_id, quote=True)
    item_id_json = json.dumps(item_id)
    # #1327: `item_id_json` is a *double*-quoted JS literal ("<id>"). Embedded in
    # a double-quoted Alpine attribute (`:class="…"`, `x-if="…"`) its inner `"`
    # terminates the HTML attribute early → Alpine "Unexpected token". For those
    # attributes use a *single*-quoted JS literal instead (mirrors the checkbox's
    # `selected.has('…')` at the cell below). JS-escape `\`/`'` then HTML-escape
    # so non-UUID string ids stay correct. `item_id_json` is still used inside
    # the single-quoted `@dblclick='…'` attribute, where double quotes are safe.
    _item_id_js_escaped = item_id.replace("\\", "\\\\").replace("'", "\\'")
    item_id_js = "'" + _html_mod.escape(_item_id_js_escaped, quote=True) + "'"

    # Row label: first non-{ref,badge,bool,currency} column else id; ref dicts
    # resolve via `_ref_display_name`.
    row_label_key = "id"
    for col in columns:
        if col.get("type") not in ("ref", "badge", "bool", "currency"):
            row_label_key = col.get("key", "id")
            break
    raw_label = item.get(row_label_key, item.get("id", ""))
    if isinstance(raw_label, dict):
        raw_label = _ref_display_name(raw_label)
    row_label = _html_mod.escape(str(raw_label or ""), quote=False)
    row_label_attr = _html_mod.escape(str(raw_label or ""), quote=True)

    # Row state Alpine binds — emitted as a single :class attribute.
    row_state_class = (
        f"{{'is-selected': selected.has({item_id_js}), "
        f"'is-saving': editing && editing.rowId === {item_id_js} && editing.saving, "
        f"'is-error': editing && editing.rowId === {item_id_js} && editing.error}}"
    )

    detail_hx_attrs = ""
    detail_link_html = ""
    edit_link_html = ""
    if detail_url_template:
        detail_url = detail_url_template.replace("{id}", item_id)
        detail_url_attr = _html_mod.escape(detail_url, quote=True)
        detail_hx_attrs = f'hx-get="{detail_url_attr}" hx-push-url="true" hx-trigger="click" hx-target="body" hx-swap="innerHTML" '
        detail_link_html = (
            f'<a href="{detail_url_attr}" '  # nosemgrep
            f'data-dazzle-action="{entity_name_attr}.view" '
            f'aria-label="View {row_label_attr}" '
            f'class="dz-tr-action">'
            '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true" '
            'xmlns="http://www.w3.org/2000/svg">'
            '<path d="M7 2.5C4.5 2.5 2.5 5 2.5 7s2 4.5 4.5 4.5S11.5 9 11.5 7 9.5 2.5 7 2.5z" '
            'stroke="currentColor" stroke-width="1.25" stroke-linejoin="round"/>'
            '<circle cx="7" cy="7" r="1.5" stroke="currentColor" stroke-width="1.25"/>'
            "</svg></a>"
        )
        edit_link_html = (
            f'<a href="{detail_url_attr}/edit" '  # nosemgrep
            f'data-dazzle-action="{entity_name_attr}.edit" '
            f'aria-label="Edit {row_label_attr}" '
            f'class="dz-tr-action">'
            '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true" '
            'xmlns="http://www.w3.org/2000/svg">'
            '<path d="M9.5 2.5l2 2L4 12H2v-2L9.5 2.5z" stroke="currentColor" stroke-width="1.25" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
            "</svg></a>"
        )

    checkbox_cell = ""
    if bulk_actions:
        checkbox_cell = (
            '<td class="dz-tr-checkbox-cell" onclick="event.stopPropagation()">'
            f'<label class="visually-hidden" for="row-check-{item_id_attr}">'
            f"Select {row_label}</label>"
            f'<input type="checkbox" id="row-check-{item_id_attr}" '  # nosemgrep
            f'class="dz-tr-checkbox" '
            f":checked=\"selected.has('{item_id_attr}')\" "
            f"@change=\"toggleRow('{item_id_attr}')\" "
            f'aria-label="Select {row_label_attr}" /></td>'
        )

    # Data cells.
    cell_parts: list[str] = []
    for col in columns:
        if col.get("hidden"):
            continue
        col_key = str(col.get("key", ""))
        col_key_attr = _html_mod.escape(col_key, quote=True)
        col_type = str(col.get("type", "") or "")
        cell_classes = "dz-tr-cell"
        if col_type in ("currency", "percentage"):
            cell_classes += " is-numeric"
        cell_value = item.get(col_key)
        # For ref columns, prefer an explicit `<key>_display` value the
        # relation loader may have injected, else resolve via dict shape.
        if col_type == "ref":
            explicit = item.get(f"{col_key}_display")
            if explicit:
                display_html = _html_mod.escape(str(explicit), quote=False)
            else:
                display_html = _render_cell_display(col, cell_value)
        else:
            display_html = _render_cell_display(col, cell_value)

        if col_key in inline_editable:
            edit_html = _render_inline_edit(item, col, cell_value)
            # Display mode template — Alpine dblclick toggles edit mode.
            edit_val_for_dblclick = json.dumps(cell_value if cell_value is not None else "")
            title_attr = ""
            if cell_value is not None:
                title_attr = f' title="{_html_mod.escape(str(cell_value), quote=True)}"'
            display_template_html = (
                f"<template x-if=\"!isEditing({item_id_js}, '{col_key_attr}')\">"
                f'<span class="dz-tr-cell-display" '
                f"@dblclick='startEdit({item_id_json}, \"{col_key_attr}\", {edit_val_for_dblclick})'"
                f"{title_attr}>{display_html}</span></template>"
            )
            edit_template_html = (
                f"<template x-if=\"isEditing({item_id_js}, '{col_key_attr}')\">"
                f"{edit_html}</template>"
            )
            cell_inner = f"{edit_template_html}{display_template_html}"
        else:
            cell_inner = display_html

        cell_parts.append(
            f'<td data-dz-col="{col_key_attr}" '  # nosemgrep
            f"x-show=\"isColumnVisible('{col_key_attr}')\" "
            f'class="{cell_classes}" onclick="event.stopPropagation()">'
            f"{cell_inner}</td>"
        )

    # Delete action.
    delete_button = (
        f'<button type="button" '  # nosemgrep
        f'data-dazzle-action="{entity_name_attr}.delete" '
        f'aria-label="Delete {row_label_attr}" '
        f'hx-delete="{api_endpoint}/{item_id_attr}" '
        f'hx-confirm="Delete this {_html_mod.escape(entity_name_lower, quote=False)}?" '
        f'hx-target="closest tr" '
        f'hx-swap="outerHTML swap:300ms" '
        f'class="dz-tr-action is-destructive">'
        '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true" '
        'xmlns="http://www.w3.org/2000/svg">'
        '<path d="M2 3.5h10M5.5 3.5V2.5h3v1M5.5 6v4M8.5 6v4M3 3.5l.5 8h7l.5-8" '
        'stroke="currentColor" stroke-width="1.25" stroke-linecap="round" '
        'stroke-linejoin="round"/></svg></button>'
    )
    actions_cell = (
        '<td class="dz-tr-actions-cell" onclick="event.stopPropagation()">'
        f'<div class="dz-tr-actions">{detail_link_html}{edit_link_html}{delete_button}</div>'
        "</td>"
    )

    return (
        f'<tr id="row-{item_id_attr}" '  # nosemgrep
        f'data-dazzle-row="{entity_name_attr}" '
        f'data-dz-row-id="{item_id_attr}" '
        f':class="{row_state_class}" '
        f'class="dz-tr-row group" '
        f"{detail_hx_attrs}>"
        f"{checkbox_cell}"
        f"{''.join(cell_parts)}"
        f"{actions_cell}"
        "</tr>"
    )


def _render_table_empty(table: dict[str, Any], request: Any) -> str:
    """Inline mirror of `fragments/table_rows.html`'s empty-state branch
    (v0.67.67). Picks the per-kind message + affordance:

        collection → "No X yet." + link to the create surface
        filtered   → "No X match the current filters." + clear-filters link
        forbidden  → custom `empty_forbidden` copy
        loading    → "Couldn't load X. Try reloading."
    """
    import html as _html_mod

    if not table:
        entity_lower = "items"
        msg = f"No {entity_lower} found."
        return (
            "<tr>"
            f'<td colspan="1" class="dz-tr-empty-cell" data-dz-empty-kind="collection">'
            f"{msg}</td></tr>"
        )

    entity_name = str(table.get("entity_name") or "items")
    entity_lower = entity_name.lower()
    columns = table.get("columns") or []
    colspan = len(columns) + (2 if table.get("bulk_actions") else 1)
    kind = str(table.get("empty_kind") or "collection")
    kind_attr = _html_mod.escape(kind, quote=True)
    table_id = _html_mod.escape(str(table.get("table_id") or "dt-table"), quote=True)
    endpoint_attr = _html_mod.escape(str(table.get("api_endpoint", "") or ""), quote=True)

    if kind == "filtered":
        msg = str(table.get("empty_filtered") or f"No {entity_lower} match the current filters.")
        msg_html = _html_mod.escape(msg, quote=False)
        clear_link = ""
        if table.get("filter_values") and request is not None:
            url_path = _html_mod.escape(
                str(getattr(request.url, "path", "") or ""),
                quote=True,
            )
            clear_link = (
                f'<a href="{url_path}" '  # nosemgrep
                f'hx-get="{endpoint_attr}" '
                f'hx-target="#{table_id}-body" '
                f'hx-swap="innerHTML" '
                f'hx-push-url="{url_path}" '
                f'class="dz-tr-empty-link">Clear filters</a>'
            )
        inner = f"{msg_html}{clear_link}"
    elif kind == "loading":
        inner = _html_mod.escape(
            f"Couldn't load {entity_lower}. Try reloading.",
            quote=False,
        )
    elif kind == "forbidden" and table.get("empty_forbidden"):
        inner = _html_mod.escape(str(table["empty_forbidden"]), quote=False)
    else:
        msg = str(
            table.get("empty_collection")
            or table.get("empty_message")
            or f"No {entity_lower} found."
        )
        msg_html = _html_mod.escape(msg, quote=False)
        create_link = ""
        if table.get("create_url"):
            create_url_attr = _html_mod.escape(
                str(table["create_url"]),
                quote=True,
            )
            create_link = (
                f'<a href="{create_url_attr}" class="dz-tr-empty-link">Add one</a>'  # nosemgrep
            )
        inner = f"{msg_html}{create_link}"

    return (
        "<tr>"
        f'<td colspan="{colspan}" class="dz-tr-empty-cell" '
        f'data-dz-empty-kind="{kind_attr}">{inner}</td>'
        "</tr>"
    )


def _render_table_sentinel(table: dict[str, Any]) -> str:
    """Inline mirror of `fragments/table_sentinel.html` (v0.67.65).

    Emits the infinite-scroll sentinel <tr> that triggers on revealed.
    Returns empty string when there are no more pages."""
    import html as _html_mod

    if not table:
        return ""
    total = int(table.get("total", 0) or 0)
    page_size = int(table.get("page_size", 50) or 50)
    current_page = int(table.get("page", 1) or 1)
    if total <= current_page * page_size:
        return ""
    next_page = current_page + 1
    columns = table.get("columns") or []
    colspan = len(columns) + 1
    table_id = _html_mod.escape(str(table.get("table_id") or "dt-table"), quote=True)
    endpoint_attr = _html_mod.escape(str(table.get("api_endpoint", "") or ""), quote=True)
    url_q = _build_table_url_params(table, next_page, with_search=False)

    return (
        f'<tr class="dz-sentinel" '  # nosemgrep
        f'hx-get="{endpoint_attr}?{url_q}" '
        f'hx-trigger="revealed" '
        f'hx-swap="afterend" '
        f'hx-headers=\'{{"Accept": "text/html"}}\' '
        f'hx-indicator="#{table_id}-loading">'
        f'<td colspan="{colspan}" class="dz-sentinel-cell">'
        f'<span class="dz-sentinel-spinner"></span>'
        f'<span class="visually-hidden">Loading more...</span>'
        f"</td></tr>"
    )


def _with_htmx_triggers(
    request: Any, result: Any, entity_name: str, action: str, redirect_url: str | None = None
) -> Any:
    """Wrap a mutation result with HX-Trigger headers for HTMX requests.

    For non-HTMX requests, returns the result unchanged (JSON serialized by FastAPI).
    For HTMX requests, returns a JSONResponse with HX-Trigger headers so the client
    can react to entity mutations (show toasts, refresh lists, etc.).

    Args:
        request: The incoming request.
        result: The mutation result.
        entity_name: Name of the entity (e.g. "Task").
        action: Mutation action ("created", "updated", "deleted").
        redirect_url: Optional URL for HX-Redirect header (post-create navigation).
    """

    if not _is_htmx_request(request):
        return result

    # Serialize Pydantic models
    if hasattr(result, "model_dump"):
        body = result.model_dump(mode="json")
    elif isinstance(result, dict):
        # Plain dicts may contain UUID or other non-JSON-serializable values
        # from the CRUD service layer.  Pre-convert via jsonable_encoder so
        # Starlette's JSONResponse (which uses stdlib json.dumps) doesn't crash.
        body = jsonable_encoder(result)
    else:
        body = result

    headers = htmx_trigger_headers(entity_name, action)
    if redirect_url:
        headers["HX-Redirect"] = redirect_url
    return JSONResponse(content=body, headers=headers)


def _render_detail_html(request: Any, result: Any, entity_name: str) -> Any:
    """Render a detail view for HTMX or browser requests.

    - HTMX request → bare HTML fragment (for partial swap)
    - Direct browser navigation → full page with app shell (#349)
    - API client (JSON) → None (let FastAPI serialize)
    """

    if not _wants_html(request):
        return None
    try:
        import html as _html_mod

        # Convert Pydantic model to dict
        if hasattr(result, "model_dump"):
            item = result.model_dump(mode="json")
        elif isinstance(result, dict):
            item = jsonable_encoder(result)
        else:
            return None

        # Phase 4 (v0.67.64): inline-render the detail-fields fragment.
        # Replaces `fragments/detail_fields.html` + `status_badge` macro.
        rows: list[str] = []
        for key, value in item.items():
            if value is None or key == "id":
                continue
            label = _html_mod.escape(
                str(key).replace("_", " ").title(),
                quote=False,
            )
            if value is True:
                value_html = (
                    '<span class="dz-badge" data-dz-tone="success" '
                    'role="status" aria-label="Status: Yes">Yes</span>'
                )
            elif value is False:
                value_html = (
                    '<span class="dz-badge" data-dz-tone="neutral" '
                    'role="status" aria-label="Status: No">No</span>'
                )
            elif isinstance(value, str) and len(value) > 200:
                value_html = (
                    '<span class="whitespace-pre-wrap">'
                    f"{_html_mod.escape(value[:200], quote=False)}…"
                    "</span>"
                )
            else:
                value_html = _html_mod.escape(str(value), quote=False)
            rows.append(
                f'<dt class="dz-detail-fields-key">{label}</dt>'
                f'<dd class="dz-detail-fields-value">{value_html}</dd>'
            )

        entity_label = _html_mod.escape(entity_name, quote=False)
        fragment_html = (
            '<div class="dz-detail-fields-card">'
            '<div class="dz-detail-fields-body">'
            f'<h2 class="dz-detail-fields-title">{entity_label}</h2>'
            f'<dl class="dz-detail-fields-list">{"".join(rows)}</dl>'
            "</div>"
            "</div>"
        )

        if _is_htmx_request(request):
            # HTMX partial swap: return bare fragment
            return HTMLResponse(content=fragment_html)

        # Direct browser navigation: wrap fragment in a typed Page (#349).
        from dazzle.render.context import PageContext
        from dazzle.render.dispatch import dispatch_render_page

        page_ctx = PageContext(
            page_title=f"{entity_name} Detail",
            app_name="Dazzle",
            current_route=str(getattr(request.url, "path", "")),
        )
        app_state = request.app.state
        css_links = tuple(
            getattr(app_state, "fragment_chrome_css_links", None)
            or ("/static/dist/dazzle.min.css",)
        )
        js_scripts = tuple(
            getattr(app_state, "fragment_chrome_js_scripts", None)
            or ("/static/dist/dazzle.min.js",)
        )
        theme = getattr(app_state, "fragment_chrome_theme", None)
        font_preconnect = tuple(getattr(app_state, "fragment_chrome_font_preconnect", None) or ())
        favicon = getattr(
            app_state,
            "fragment_chrome_favicon",
            "/static/assets/dazzle-favicon.svg",
        )
        full_html = dispatch_render_page(
            page_ctx,
            fragment_html,
            css_links=css_links,
            js_scripts=js_scripts,
            theme=theme,
            font_preconnect=font_preconnect,
            favicon=favicon,
            chrome=False,
        )
        return HTMLResponse(content=full_html)
    except Exception:
        logger.debug("ignored exception in route_generator.py:_render_detail_html", exc_info=True)
        return None  # Fragment not found or render error
