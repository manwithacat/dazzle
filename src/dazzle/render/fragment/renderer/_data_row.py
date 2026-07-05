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
from dataclasses import dataclass
from typing import Any

from dazzle.render.filters import (
    _basename_or_url_filter,
    _bool_icon_filter,
    _currency_filter,
    _date_filter,
    _metric_number_filter,
    _ref_display_name,
    _truncate_filter,
    badge_icon_html,
    resolve_status_tone,
)
from dazzle.render.fragment.icon_html import lucide_svg_html
from dazzle.render.fragment.primitives import DataTable, RowCapabilities


@dataclass(frozen=True, slots=True)
class _RowArchetype:
    """A named list-row archetype (#1511): a capability *preset* over the one
    shared row-core. The three archetypes converge their `<tr>` assembly here
    while staying semantically distinct — `base_class` keeps each variant's
    existing CSS hook, and `list_kind` stamps the `data-dz-list-kind` marker so
    both CSS and an inspecting agent retain the category (design §3.3).
    """

    base_class: str
    list_kind: str


# The three archetypes (design §3.3). `data-table` is the rich CRUD row (Alpine
# `dzTable` controller mounted); `embedded` is the plain Fragment `Table` row;
# `region` is the workspace `kind: list` row. All three flow through
# `assemble_list_row` — only HTML production converges; RBAC/scope/sort and the
# per-archetype cell content stay in the callers.
ARCHETYPE_DATA_TABLE = _RowArchetype("dz-tr-row group", "data-table")
ARCHETYPE_EMBEDDED = _RowArchetype("dz-table__row", "embedded")
ARCHETYPE_LIST_REGION = _RowArchetype("dz-list-row", "region")


def drill_row_attrs(url_attr: str) -> str:
    """The shared clickable-row block (#1511, design §3.2): the row owns a
    bare-click `hx-get` to the detail surface (full-page swap). `url_attr` is the
    already-escaped detail URL — empty means the row is not clickable.

    This is the single load-bearing composition rule: the *row* owns the bare
    click; every interactive sub-element (checkbox, edit cell, action button,
    peek chevron) must `event.stopPropagation()` so the capabilities coexist on
    one row without entanglement.
    """
    if not url_attr:
        return ""
    # 2b preload-drill (#1491): `hx-preload="mouseover"` warms the detail GET on
    # hover (the vendored htmx-4 `preload` extension), so the click serves the
    # cached prefetch — perceived-instant drill. The extension dedups per row
    # (one prefetch / 5s), so a mouse-sweep doesn't storm the server.
    return (
        f'hx-get="{url_attr}" hx-push-url="true" hx-trigger="click" '
        f'hx-preload="mouseover" hx-target="body" hx-swap="innerHTML" tabindex="0"'
    )


def slideover_panel_id(table_id: str) -> str:
    """Container id for a list's `peek: slide_over` shared panel (#1494).

    The single id convention shared by the `SlideOver` container emitter
    (`_emit_slide_over`) and the per-row chevron (`render_data_row`) so a row's
    reveal/target resolves to the one panel emitted for its list."""
    return f"slideover-{table_id}"


def slideover_content_id(table_id: str) -> str:
    """Body id a row's slide_over chevron `hx-get`s the detail body into (#1494)."""
    return f"slideover-content-{table_id}"


def assemble_list_row(
    *,
    archetype: _RowArchetype,
    cells_html: str,
    row_id_attr: str = "",
    dom_id: str = "",
    data_dazzle_row: str = "",
    state_bind: str = "",
    drill_attrs: str = "",
    class_extra: str = "",
    checkbox_cell: str = "",
    actions_cell: str = "",
    peek_panel_row: str = "",
) -> str:
    """Assemble one list-row `<tr>` from per-archetype pieces (#1511).

    The single `<tr>`-skeleton owner for all three list archetypes. It fixes the
    canonical attribute order, stamps the `data-dz-list-kind` archetype marker,
    composes the base class, and orders the cells (`checkbox · cells · actions`)
    — then appends any peek panel row. The *content* of each slot (cell wrappers,
    checkbox flavour, action flavour, row-state binds) is produced by the caller,
    because those genuinely diverge by archetype (design §3.3); only the skeleton
    converges here.

    All `*_attr` / `dom_id` / `data_dazzle_row` inputs are already HTML-escaped by
    the caller (which owns its escaping context) — this seam does pure string
    assembly. `state_bind` is a full Alpine `:class="…"` attribute (data-table
    row-state). `drill_attrs` is the output of `drill_row_attrs`.
    """
    head = "<tr"
    if dom_id:
        head += f' id="{dom_id}"'
    elif row_id_attr:
        # HM grid contract (convergence C0a): a row with an identity carries a
        # stable `id` — the idiomorph MORPH KEY — so a live selection follows
        # its ROW (not its DOM position) across a re-sort/paginate. The id
        # encodes `data-dz-row-id` (the payload anchor) so the two agree. An
        # explicit `dom_id` (drawer/detail anchor) wins: any id is a morph key.
        head += f' id="dz-grid-row-{row_id_attr}"'
    if data_dazzle_row:
        head += f' data-dazzle-row="{data_dazzle_row}"'
    if row_id_attr:
        head += f' data-dz-row-id="{row_id_attr}"'
    head += f' data-dz-list-kind="{archetype.list_kind}"'
    if state_bind:
        head += f" {state_bind}"
    head += f' class="{archetype.base_class}{class_extra}"'
    if drill_attrs:
        head += f" {drill_attrs}"
    head += ">"
    return f"{head}{checkbox_cell}{cells_html}{actions_cell}</tr>{peek_panel_row}"


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


def _json_summary(value: Any, *, max_pairs: int = 4, length: int = 80) -> str:
    """Humanise a JSON value (#1491 1d) — a compact `key: val · key: val`
    summary for a dict, `a, b, c` for a list — instead of a raw blob or (worse)
    `_ref_display_name` mangling a dict down to a single arbitrary value."""
    if isinstance(value, dict):
        parts = [f"{k}: {v}" for k, v in list(value.items())[:max_pairs]]
        text = " · ".join(parts)
        if len(value) > max_pairs:
            text += " · …"
    elif isinstance(value, (list, tuple)):
        parts = [str(x) for x in list(value)[:max_pairs]]
        text = ", ".join(parts)
        if len(value) > max_pairs:
            text += ", …"
    else:
        text = str(value)
    return text[:length] + "…" if len(text) > length else text


def _render_cell_display(col: dict[str, Any], value: Any) -> str:
    """Render the display-mode value for one table cell.

    Mirrors the type-dispatch in `table_rows.html` (badge / bool /
    date / datetime / number / json / currency / sensitive / ref /
    percentage / text default). #1491 1d: datetime/number/json are
    humanised at the core so detail views (which feed the cell core
    form-typed values) stop leaking raw ISO / `True` / full-precision
    floats / mangled JSON.
    """

    col_type = str(col.get("type", "") or "")
    # #1491 1d: an empty value renders the em-dash placeholder for the humanised
    # types — a null `number` must NOT fabricate "0" and a null `json` must NOT
    # leak "None" (the detail seam guards upstream; list rows reach here directly).
    if col_type in ("datetime", "number", "json") and value in (None, "", "—"):
        return "—"
    if col_type == "datetime":
        return _html_mod.escape(_date_filter(value, "%d %b %Y %H:%M"), quote=False)
    if col_type == "number":
        return _html_mod.escape(_metric_number_filter(value), quote=False)
    if col_type == "json":
        return _html_mod.escape(_json_summary(value), quote=False)
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
    if col_type in ("currency", "money"):
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
    if col_type == "file":
        # ADR-0049 Phase 2: file fields render a download link (detail-view
        # parity). Files aren't typical list columns, so this is additive.
        if value in (None, "", "—"):
            return "—"
        href = _html_mod.escape(str(value), quote=True)
        label = _html_mod.escape(str(_basename_or_url_filter(value)), quote=False)
        return (
            f'<a href="{href}" target="_blank" rel="noopener" class="dz-detail-file-link">'
            f"{label}</a>"
        )
    # Default text cell — truncated. #1491 1d: a dict/list value (an unmapped
    # `json` field, e.g. a `text`-typed column over JSON data) is summarised
    # rather than routed through `_truncate_filter` → `_ref_display_name`, which
    # mangles a dict down to one arbitrary value. A float is rounded rather than
    # leaking full binary precision.
    if isinstance(value, (dict, list, tuple)):
        inner = _json_summary(value)
    elif isinstance(value, float):
        inner = _metric_number_filter(value)
    else:
        inner = _truncate_filter(value or "")
    return f'<span class="dz-tr-cell-truncate">{_html_mod.escape(inner, quote=False)}</span>'


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
    # Convergence C1.1: `is-selected` is owned by the HM grid controller
    # (dz-grid.js toggles the class directly from the checkbox state) — it must
    # NOT ride the Alpine :class bind, or any Alpine re-evaluation would strip
    # the controller-applied class. is-saving/is-error stay Alpine until the
    # inline-edit extension moves in C2.
    row_state_class = (
        f"{{'is-saving': editing && editing.rowId === {item_id_js} && editing.saving, "
        f"'is-error': editing && editing.rowId === {item_id_js} && editing.error}}"
    )

    # #1494 (2c): the row-peek chevron. `peek: expand` toggles a hidden *sibling
    # panel row* in place; `peek: slide_over` loads the same detail body into the
    # one shared right-side `SlideOver` panel for this list and reveals it. Only
    # `off`/unset rows stay byte-identical to pre-#1494 (no chevron emitted).
    peek_mode = str(table.get("peek_mode") or "").strip()
    peek_expand = peek_mode == "expand"
    peek_slide = peek_mode == "slide_over"
    peek_toggle_html = ""

    drill_attrs = ""
    detail_link_html = ""
    edit_link_html = ""
    if detail_url_template:
        detail_url = detail_url_template.replace("{id}", item_id)
        detail_url_attr = _html_mod.escape(detail_url, quote=True)
        if peek_expand:
            peek_url_attr = _html_mod.escape(f"{detail_url}?peek=1", quote=True)
            panel_id = f"peek-{item_id_attr}"
            content_id = f"peek-content-{item_id_attr}"
            peek_toggle_html = (
                f'<button type="button" '  # nosemgrep
                f'class="dz-tr-action dz-tr-peek-toggle" '
                f'data-dazzle-action="{entity_name_attr}.peek" '
                f'aria-label="Toggle detail for {row_label_attr}" '
                f'aria-expanded="false" '
                f'hx-get="{peek_url_attr}" '
                f'hx-target="#{content_id}" '
                f'hx-swap="innerHTML" '
                f"hx-on:click=\"const p=document.getElementById('{panel_id}'); "
                f"const willOpen=p.hasAttribute('hidden'); "
                f"if(willOpen){{p.removeAttribute('hidden')}}else{{p.setAttribute('hidden','')}}; "
                f"this.setAttribute('aria-expanded', String(willOpen));\">"
                '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true" '
                'xmlns="http://www.w3.org/2000/svg">'
                '<path d="M3.5 5.5L7 9l3.5-3.5" stroke="currentColor" stroke-width="1.25" '
                'stroke-linecap="round" stroke-linejoin="round"/></svg></button>'
            )
        elif peek_slide:
            # The chevron loads the detail body into this list's one shared
            # SlideOver panel (`#slideover-content-{table_id}`) and reveals the
            # container (`#slideover-{table_id}`). JS-free reveal via inline
            # hx-on; the backdrop/close button (on the SlideOver) re-hide it.
            table_id = str(table.get("table_id") or "")
            slide_url_attr = _html_mod.escape(f"{detail_url}?peek=1", quote=True)
            content_target = _html_mod.escape(slideover_content_id(table_id), quote=True)
            # panel id crosses into a JS-string context inside hx-on — json.dumps
            # for the JS layer, then HTML-escape for the attribute layer (the
            # #1494 Slice-2 hardening; table_id is a parser-validated identifier,
            # so this is defense-in-depth).
            panel_js = _html_mod.escape(json.dumps(slideover_panel_id(table_id)), quote=True)
            reveal_js = f"document.getElementById({panel_js}).removeAttribute('hidden')"
            peek_toggle_html = (
                f'<button type="button" '  # nosemgrep
                f'class="dz-tr-action dz-tr-peek-toggle" '
                f'data-dazzle-action="{entity_name_attr}.peek" '
                f'aria-label="Open detail for {row_label_attr}" '
                f'hx-get="{slide_url_attr}" '
                f'hx-target="#{content_target}" '
                f'hx-swap="innerHTML" '
                f'hx-on:click="{reveal_js}">'
                '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true" '
                'xmlns="http://www.w3.org/2000/svg">'
                '<path d="M5.5 3.5L9 7l-3.5 3.5" stroke="currentColor" stroke-width="1.25" '
                'stroke-linecap="round" stroke-linejoin="round"/></svg></button>'
            )
        drill_attrs = drill_row_attrs(detail_url_attr)
        detail_link_html = (
            f'<a href="{detail_url_attr}" '  # nosemgrep
            f'data-dazzle-action="{entity_name_attr}.view" '
            f'aria-label="View {row_label_attr}" '
            f'class="dz-tr-action">'
            f"{lucide_svg_html('eye', cls='dz-tr-action-icon')}</a>"
        )
        edit_link_html = (
            f'<a href="{detail_url_attr}/edit" '  # nosemgrep
            f'data-dazzle-action="{entity_name_attr}.edit" '
            f'aria-label="Edit {row_label_attr}" '
            f'class="dz-tr-action">'
            f"{lucide_svg_html('pencil', cls='dz-tr-action-icon')}</a>"
        )

    checkbox_cell = ""
    if bulk_actions:
        # Convergence C1.1: the row box is the HM grid controller's selection
        # seam — `data-dz-grid-select` (delegated change handler) +
        # `data-dz-grid-row-id` (the bulk payload anchor; the row's stable
        # `id` encodes the same value = the idiomorph morph key). The
        # checkbox's own `.checked` IS the state — no Alpine bindings.
        checkbox_cell = (
            '<td class="dz-tr-checkbox-cell" onclick="event.stopPropagation()">'
            f'<label class="visually-hidden" for="row-check-{item_id_attr}">'
            f"Select {row_label}</label>"
            f'<input type="checkbox" id="row-check-{item_id_attr}" '  # nosemgrep
            f'class="dz-tr-checkbox" '
            f'data-dz-grid-select data-dz-grid-row-id="{item_id_attr}" '
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

        # C2.1: no per-cell visibility binding — dz-grid-cols.js projects the
        # hidden set onto [data-dz-col] cells after every swap.
        cell_parts.append(
            f'<td data-dz-col="{col_key_attr}" '  # nosemgrep
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
        f"{lucide_svg_html('trash-2', cls='dz-tr-action-icon')}</button>"
    )
    actions_cell = (
        '<td class="dz-tr-actions-cell" onclick="event.stopPropagation()">'
        f'<div class="dz-tr-actions">{peek_toggle_html}{detail_link_html}{edit_link_html}'
        f"{delete_button}</div>"
        "</td>"
    )

    # #1494: the hidden sibling panel the `expand` chevron reveals; spans the full
    # row. `slide_over` uses the one shared SlideOver container instead, so it
    # emits no per-row panel.
    peek_panel_row = ""
    if peek_expand:
        colspan = len(cell_parts) + (1 if bulk_actions else 0) + 1
        peek_panel_row = (
            f'<tr id="peek-{item_id_attr}" '  # nosemgrep
            f'class="dz-tr-peek-panel" hidden>'
            f'<td colspan="{colspan}" class="dz-tr-peek-cell" '
            f'id="peek-content-{item_id_attr}"></td>'
            "</tr>"
        )

    # #1511: the `<tr>` skeleton is assembled by the shared `assemble_list_row`
    # seam (the one row-core for all three archetypes). The data-table archetype
    # contributes its rich pieces — the whole-row drill (`detail_url`), the Alpine
    # row-state bind, the bulk-select checkbox, the per-column cells, and the
    # hover-icon actions cell + peek panel — but the row identity/marker/class
    # ordering lives in the seam. `drill_attrs` is built above (reusing the
    # escaped detail URL) inside the `detail_url_template` block.
    return assemble_list_row(
        archetype=ARCHETYPE_DATA_TABLE,
        cells_html="".join(cell_parts),
        row_id_attr=item_id_attr,
        dom_id=f"row-{item_id_attr}",
        data_dazzle_row=entity_name_attr,
        state_bind=f':class="{row_state_class}"',
        drill_attrs=drill_attrs,
        checkbox_cell=checkbox_cell,
        actions_cell=actions_cell,
        peek_panel_row=peek_panel_row,
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
        # #1494: `peek: expand` chevron + inline detail panel. Requires a detail
        # surface (the chevron lives inside the `drill` block), so peek with no
        # detail URL is inert.
        "peek_mode": caps.peek,
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
