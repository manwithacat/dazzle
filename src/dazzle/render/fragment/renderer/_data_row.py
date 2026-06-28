"""Converged list row-core — the rich `dz-tr-row` data-table row (#1505).

The single `render/` source of truth for the rich CRUD data-table row,
ported (Phase 1, byte-for-byte) from the retired
`http/runtime/htmx_render.py::_render_table_row` family. `render_data_row`
is the substrate-native entry: it translates a `RowCapabilities` vector into
the internal table-dict the ported row renderer consumes. The dict is an
implementation detail of this module — callers pass typed
`(columns, item, RowCapabilities)`.

Pure `render/` code: no `http/` / `page/` imports (ADR-0038). Output is pinned
byte-for-byte by `tests/unit/test_data_row_characterization_1505.py`.
"""

import html as _html_mod
import json
from typing import Any

from dazzle.render.filters import (
    _bool_icon_filter,
    _currency_filter,
    _date_filter,
    _ref_display_name,
    _truncate_filter,
    badge_icon_html,
    resolve_status_tone,
)
from dazzle.render.fragment.primitives import DataTable, RowCapabilities


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

    col_type = str(col.get("type", "") or "")
    if col_type == "badge":
        if value in (None, "", "—"):
            return '<span class="dz-badge-empty" aria-label="No status">—</span>'
        # #1493 slice 2: a declared `semantic:` binding (col["semantic_map"]) wins
        # over the spelling-based name guess; None/empty → byte-identical default.

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


def render_data_row(
    columns: tuple[Any, ...],
    item: dict[str, Any],
    caps: RowCapabilities,
    *,
    entity_name: str = "Item",
    api_endpoint: str = "",
    detail_url_template: str = "",
    table_id: str = "dt-table",
) -> str:
    """Render one rich data-table `<tr>` from typed inputs (#1505).

    Byte-identical to the retired `_render_table_row` for the `data-table`
    archetype. `caps` gates the varying parts (bulk-select, inline-edit,
    drill); the always-on structure (row-state binds, per-cell column
    visibility, the actions cell) is intrinsic to this archetype.
    """
    table: dict[str, Any] = {
        "columns": list(columns),
        "entity_name": entity_name,
        "api_endpoint": api_endpoint,
        # `drill` is the authoritative gate for the whole-row hx-get + view/edit
        # links — the template only flows through when the capability is on.
        "detail_url_template": detail_url_template if caps.drill else "",
        "bulk_actions": caps.bulk_select,
        "inline_editable": list(caps.inline_editable),
        "table_id": table_id,
    }
    return _render_table_row(table, dict(item))


def render_data_table_rows(dt: DataTable) -> str:
    """Render the `<tbody>` children (the `<tr>` set) of a `DataTable` (#1505).

    The substrate-native rows-only entry. Both the (Phase-3) full-table emitter
    and the (Phase-2) http/ HTMX-refresh transport adapter call down into this,
    so first-paint and refresh can never diverge. Returns the rows alone (no
    `<tbody>` wrapper) for an `innerHTML`/`innerMorph` swap into an existing
    table body.
    """
    return "".join(
        render_data_row(
            dt.columns,
            dict(item),
            dt.capabilities,
            entity_name=dt.entity_name,
            api_endpoint=dt.api_endpoint,
            detail_url_template=dt.detail_url_template,
            table_id=dt.table_id,
        )
        for item in dt.rows
    )
