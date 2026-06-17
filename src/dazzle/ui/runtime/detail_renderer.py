"""Detail-view renderer (Phase 4, v0.67.75).

Inline Python port of `components/detail_view.html` plus its 3
related-display fragments:
  - `fragments/related_status_cards.html`
  - `fragments/related_file_list.html`
  - `fragments/related_table_group.html`

Plus the legacy `fragments/status_badge.html` include shim (which just
re-exports `macros/status_badge.html::render_status_badge`).

All Alpine bindings, HTMX attributes, and CSS class names match the
legacy templates byte-for-byte. Field type dispatch in the detail
list mirrors `detail_view.html`: badge, bool/checkbox, date,
currency/money, file, ref, enum, ref-dict, default.
"""

from __future__ import annotations

from typing import Any

from dazzle.render.html import esc as _esc


def _render_status_badge(value: Any) -> str:
    """Inline mirror of `macros/status_badge.html::render_status_badge`."""
    from dazzle.render.filters import _badge_tone_filter

    if value in (None, "", "—"):
        return '<span class="dz-badge-empty" aria-label="No status">—</span>'
    tone = _badge_tone_filter(value)
    label = str(value).replace("_", " ").title()
    return (
        f'<span class="dz-badge" data-dz-tone="{_esc(tone, quote=True)}" '  # nosemgrep
        f'role="status" aria-label="Status: {_esc(label, quote=True)}">'
        f"{_esc(label)}</span>"
    )


def _render_field_value(field: Any, value: Any, item: dict[str, Any]) -> str:
    """Render one detail-row value cell by field type."""
    from dazzle.render.filters import (
        _bool_icon_filter,
        _currency_filter,
        _date_filter,
        _ref_display_name,
    )
    from dazzle.ui.runtime.form_renderer import _basename_or_url

    if value is None:
        return "—"
    ftype = str(getattr(field, "type", "") or "")
    if ftype == "badge":
        return _render_status_badge(value)
    if ftype in ("bool", "checkbox"):
        return str(_bool_icon_filter(value))
    if ftype == "date":
        return _esc(_date_filter(value))
    if ftype in ("currency", "money"):
        extra = getattr(field, "extra", None) or {}
        currency_code = (
            extra.get("currency_code", "GBP") if isinstance(extra, dict) else "GBP"
        ) or "GBP"
        return _esc(_currency_filter(value, currency_code))
    if ftype == "file":
        if not value:
            return "—"
        href = _esc(value, quote=True)
        label = _esc(_basename_or_url(value))
        return (
            f'<a href="{href}" target="_blank" rel="noopener" '  # nosemgrep
            'class="dz-detail-file-link">'
            '<svg xmlns="http://www.w3.org/2000/svg" class="dz-detail-file-icon" '
            'fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">'
            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" '
            'd="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 '
            '01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" /></svg>'
            f"{label}</a>"
        )
    if ftype == "ref":
        name = str(getattr(field, "name", "") or "")
        rel_name = name[:-3] if name.endswith("_id") else name
        display_val = item.get(f"{rel_name}_display", "") or item.get(f"{name}_display", "")
        if display_val:
            return _esc(display_val)
        if isinstance(value, dict):
            return _esc(
                value.get("name")
                or value.get("title")
                or value.get("label")
                or value.get("email")
                or value.get("id", "—")
            )
        if value:
            return _esc(value)
        return "—"
    # default branch
    if isinstance(value, dict):
        return _esc(_ref_display_name(value))
    if ftype == "enum":
        if value in (None, ""):
            return "—"
        return _esc(str(value).replace("_", " ").title())
    if value in (None, ""):
        return "—"
    return _esc(value)


def _render_create_row(tab: Any, detail_item_id: str, extra_qs: str = "") -> str:
    create_url = str(getattr(tab, "create_url", "") or "")
    if not create_url:
        return ""
    filter_field = str(getattr(tab, "filter_field", "") or "")
    entity_name = str(getattr(tab, "entity_name", "") or "")
    label = str(getattr(tab, "label", "") or "")
    qs_sep = "&amp;" if "?" in create_url else "?"
    href = (
        f"{_esc(create_url, quote=True)}{qs_sep}"
        f"{_esc(filter_field, quote=True)}={_esc(detail_item_id, quote=True)}"
        f"{extra_qs}"
    )
    return (
        '<div class="dz-related-create-row">'
        f'<a href="{href}" '  # nosemgrep
        'class="dz-related-create-button" '
        f'data-dazzle-action="{_esc(entity_name, quote=True)}.create">'
        f"+ New {_esc(label)}</a></div>"
    )


def _render_related_status_cards(group: Any, detail_item: dict[str, Any]) -> str:
    parts: list[str] = []
    tabs = list(getattr(group, "tabs", None) or [])
    detail_item_id = str(detail_item.get("id", "") or "")
    multi_tabs = len(tabs) > 1
    for tab in tabs:
        if not bool(getattr(tab, "visible", True)):
            continue
        tab_block: list[str] = ['<div class="dz-related-group">']
        if multi_tabs:
            tab_block.append(
                f'<h4 class="dz-related-tab-label">{_esc(getattr(tab, "label", ""))}</h4>'
            )
        tab_block.append(_render_create_row(tab, detail_item_id))
        rows = list(getattr(tab, "rows", None) or [])
        if rows:
            columns = list(getattr(tab, "columns", None) or [])
            detail_url_template = str(getattr(tab, "detail_url_template", "") or "")
            cards: list[str] = []
            for item in rows:
                item_id = str(item.get("id", "") or "") if isinstance(item, dict) else ""
                hx_attrs = ""
                if detail_url_template:
                    detail_url = detail_url_template.replace("{id}", item_id)
                    hx_attrs = (
                        f'hx-get="{_esc(detail_url, quote=True)}" '
                        'hx-push-url="true" hx-trigger="click" hx-target="body" hx-swap="innerHTML" '
                    )
                text_lines: list[str] = []
                for idx, col in enumerate(columns[:3]):
                    col_key = (
                        col.get("key", "") if isinstance(col, dict) else getattr(col, "key", "")
                    )
                    val = item.get(col_key) if isinstance(item, dict) else None
                    cls = (
                        "dz-related-status-card-primary"
                        if idx == 0
                        else "dz-related-status-card-secondary"
                    )
                    text_lines.append(f'<p class="{cls}">{"—" if val is None else _esc(val)}</p>')
                badge_html = ""
                for col in columns:
                    col_type = (
                        col.get("type", "") if isinstance(col, dict) else getattr(col, "type", "")
                    )
                    col_key = (
                        col.get("key", "") if isinstance(col, dict) else getattr(col, "key", "")
                    )
                    if col_type == "badge":
                        badge_html = (
                            '<span class="dz-related-status-card-badge">'
                            f"{_render_status_badge(item.get(col_key) if isinstance(item, dict) else None)}"
                            "</span>"
                        )
                        break
                cards.append(
                    '<div class="dz-related-status-card" '  # nosemgrep
                    f"{hx_attrs}>"
                    '<div class="dz-related-status-card-row">'
                    f'<div class="dz-related-status-card-text">{"".join(text_lines)}</div>'
                    f"{badge_html}"
                    "</div></div>"
                )
            tab_block.append(f'<div class="dz-related-status-grid">{"".join(cards)}</div>')
        else:
            label = str(getattr(tab, "label", "") or "").lower()
            tab_block.append(f'<p class="dz-related-empty">No {_esc(label)} found.</p>')
        tab_block.append("</div>")
        parts.append("".join(tab_block))
    return "".join(parts)


def _render_related_file_list(group: Any, detail_item: dict[str, Any]) -> str:
    from dazzle.render.filters import _date_filter

    parts: list[str] = []
    tabs = list(getattr(group, "tabs", None) or [])
    detail_item_id = str(detail_item.get("id", "") or "")
    multi_tabs = len(tabs) > 1
    for tab in tabs:
        if not bool(getattr(tab, "visible", True)):
            continue
        tab_block: list[str] = ['<div class="dz-related-group">']
        if multi_tabs:
            tab_block.append(
                f'<h4 class="dz-related-tab-label">{_esc(getattr(tab, "label", ""))}</h4>'
            )
        tab_block.append(_render_create_row(tab, detail_item_id))
        rows = list(getattr(tab, "rows", None) or [])
        if rows:
            columns = list(getattr(tab, "columns", None) or [])
            detail_url_template = str(getattr(tab, "detail_url_template", "") or "")
            row_blocks: list[str] = []
            for item in rows:
                item_id = str(item.get("id", "") or "") if isinstance(item, dict) else ""
                hx_attrs = ""
                if detail_url_template:
                    detail_url = detail_url_template.replace("{id}", item_id)
                    hx_attrs = (
                        f'hx-get="{_esc(detail_url, quote=True)}" '
                        'hx-push-url="true" hx-trigger="click" hx-target="body" hx-swap="innerHTML" '
                    )
                text_lines: list[str] = []
                for idx, col in enumerate(columns[:2]):
                    col_key = (
                        col.get("key", "") if isinstance(col, dict) else getattr(col, "key", "")
                    )
                    val = item.get(col_key) if isinstance(item, dict) else None
                    if idx == 0:
                        text_lines.append(
                            '<p class="dz-related-file-primary">'
                            f"{'—' if val is None else _esc(val)}</p>"
                        )
                    else:
                        text_lines.append(
                            '<p class="dz-related-file-secondary">'
                            f"{'' if val is None else _esc(val)}</p>"
                        )
                date_html = ""
                for col in columns:
                    col_type = (
                        col.get("type", "") if isinstance(col, dict) else getattr(col, "type", "")
                    )
                    col_key = (
                        col.get("key", "") if isinstance(col, dict) else getattr(col, "key", "")
                    )
                    if col_type == "date":
                        date_val = item.get(col_key) if isinstance(item, dict) else None
                        date_html = (
                            '<span class="dz-related-file-date">'
                            f"{_esc(_date_filter(date_val))}</span>"
                        )
                        break
                row_blocks.append(
                    '<div class="dz-related-file-row" '  # nosemgrep
                    f"{hx_attrs}>"
                    '<svg xmlns="http://www.w3.org/2000/svg" class="dz-related-file-icon" '
                    'fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">'
                    '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" '
                    'd="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 '
                    '0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" /></svg>'
                    f'<div class="dz-related-file-text">{"".join(text_lines)}</div>'
                    f"{date_html}"
                    "</div>"
                )
            tab_block.append(f'<div class="dz-related-file-list">{"".join(row_blocks)}</div>')
        else:
            label = str(getattr(tab, "label", "") or "").lower()
            tab_block.append(f'<p class="dz-related-empty">No {_esc(label)} found.</p>')
        tab_block.append("</div>")
        parts.append("".join(tab_block))
    return "".join(parts)


def _render_related_table_cell(col: Any, item: dict[str, Any]) -> str:
    from dazzle.render.filters import (
        _bool_icon_filter,
        _currency_filter,
        _date_filter,
        _truncate_filter,
    )

    col_key = col.get("key", "") if isinstance(col, dict) else getattr(col, "key", "")
    col_type = col.get("type", "") if isinstance(col, dict) else getattr(col, "type", "")
    val = item.get(col_key) if isinstance(item, dict) else None
    if col_type == "badge":
        return _render_status_badge(val)
    if col_type == "bool":
        return str(_bool_icon_filter(val))
    if col_type == "date":
        return _esc(_date_filter(val))
    if col_type == "currency":
        currency_code = (
            col.get("currency_code", "GBP")
            if isinstance(col, dict)
            else getattr(col, "currency_code", "GBP")
        ) or "GBP"
        return _esc(_currency_filter(val, currency_code))
    return _esc(_truncate_filter(val or ""))


def _render_related_table_group(group: Any, detail_item: dict[str, Any]) -> str:
    tabs = list(getattr(group, "tabs", None) or [])
    detail_item_id = str(detail_item.get("id", "") or "")
    multi_tabs = len(tabs) > 1
    first_tab_id = str(getattr(tabs[0], "tab_id", "") or "") if tabs else ""

    parts: list[str] = [
        f"<div x-data=\"{{ activeTab: '{_esc(first_tab_id, quote=True)}' }}\">"  # nosemgrep
    ]

    # Tab buttons
    if multi_tabs:
        tab_buttons: list[str] = []
        for tab in tabs:
            if not bool(getattr(tab, "visible", True)):
                continue
            tab_id = _esc(getattr(tab, "tab_id", "") or "", quote=True)
            tab_label = _esc(getattr(tab, "label", ""))
            total = getattr(tab, "total", 0) or 0
            tab_buttons.append(
                f'<button type="button" class="dz-related-tab" '  # nosemgrep
                f":class=\"{{ 'is-active': activeTab === '{tab_id}' }}\" "
                f'role="tab" '
                f":aria-selected=\"activeTab === '{tab_id}'\" "
                f"@click=\"activeTab = '{tab_id}'\">"
                f'{tab_label}<span class="dz-related-tab-count">{int(total)}</span>'
                "</button>"
            )
        parts.append(f'<div class="dz-related-tabs" role="tablist">{"".join(tab_buttons)}</div>')

    # Tab panels
    for tab in tabs:
        if not bool(getattr(tab, "visible", True)):
            continue
        tab_id = _esc(getattr(tab, "tab_id", "") or "", quote=True)
        entity_name = _esc(getattr(tab, "entity_name", "") or "", quote=True)
        columns = list(getattr(tab, "columns", None) or [])
        rows = list(getattr(tab, "rows", None) or [])
        label_lower = str(getattr(tab, "label", "") or "").lower()
        detail_url_template = str(getattr(tab, "detail_url_template", "") or "")

        # Extra query-string for filter_type_field/value
        filter_type_field = str(getattr(tab, "filter_type_field", "") or "")
        filter_type_value = str(getattr(tab, "filter_type_value", "") or "")
        extra_qs = ""
        if filter_type_field:
            extra_qs = (
                f"&amp;{_esc(filter_type_field, quote=True)}={_esc(filter_type_value, quote=True)}"
            )

        x_show = f" x-show=\"activeTab === '{tab_id}'\"" if multi_tabs else ""

        # Header row
        header_cells = "".join(
            f'<th scope="col">{_esc(col.get("label", "") if isinstance(col, dict) else getattr(col, "label", ""))}</th>'
            for col in columns
        )

        # Body rows
        body_html: str
        if rows:
            row_blocks: list[str] = []
            for item in rows:
                item_id = str(item.get("id", "") or "") if isinstance(item, dict) else ""
                hx_attrs = ""
                if detail_url_template:
                    detail_url = detail_url_template.replace("{id}", item_id)
                    hx_attrs = (
                        f' hx-get="{_esc(detail_url, quote=True)}" '
                        'hx-push-url="true" hx-trigger="click" hx-target="body" hx-swap="innerHTML"'
                    )
                cells = "".join(
                    f"<td>{_render_related_table_cell(col, item) if isinstance(item, dict) else ''}</td>"
                    for col in columns
                )
                row_blocks.append(f"<tr{hx_attrs}>{cells}</tr>")  # nosemgrep
            body_html = "".join(row_blocks)
        else:
            body_html = (
                f'<tr><td colspan="{len(columns)}" '
                f'class="dz-related-table-empty-cell">No {_esc(label_lower)} found.'
                "</td></tr>"
            )

        parts.append(
            f'<div{x_show} role="tabpanel">'  # nosemgrep
            '<div class="dz-related-table-card">'
            f"{_render_create_row(tab, detail_item_id, extra_qs)}"
            '<div class="dz-related-table-scroll">'
            f'<table class="dz-related-table" data-entity="{entity_name}">'
            f"<thead><tr>{header_cells}</tr></thead>"
            f"<tbody>{body_html}</tbody>"
            "</table></div></div></div>"
        )

    parts.append("</div>")
    return "".join(parts)


def _render_related_group(group: Any, detail_item: dict[str, Any]) -> str:
    display = str(getattr(group, "display", "") or "")
    if display == "status_cards":
        return _render_related_status_cards(group, detail_item)
    if display == "file_list":
        return _render_related_file_list(group, detail_item)
    return _render_related_table_group(group, detail_item)


def render_detail_view(detail: Any) -> str:
    """Inline-render `components/detail_view.html` (Phase 4, v0.67.75).

    Returns empty string when `detail` is falsy (matches the legacy
    `{% if detail %}` guard).
    """
    if not detail:
        return ""

    related_groups = list(getattr(detail, "related_groups", None) or [])
    entity_name = str(getattr(detail, "entity_name", "") or "")
    entity_name_attr = _esc(entity_name, quote=True)
    entity_name_lower = entity_name.lower()
    entity_id = str(getattr(detail, "entity_id", "") or "")
    entity_id_attr_html = f' data-dz-entity-id="{_esc(entity_id, quote=True)}"' if entity_id else ""
    outer_cls = "dz-detail dz-detail-wide" if related_groups else "dz-detail"

    # --- Header ----------------------------------------------------
    back_url = _esc(getattr(detail, "back_url", "") or "", quote=True)
    title = _esc(getattr(detail, "title", ""))
    edit_url = str(getattr(detail, "edit_url", "") or "")
    delete_url = str(getattr(detail, "delete_url", "") or "")

    actions: list[str] = []
    if edit_url:
        actions.append(
            f'<a href="{_esc(edit_url, quote=True)}" '  # nosemgrep
            f'class="dz-button dz-button-outline" '
            f'data-dazzle-action="{entity_name_attr}.edit" '
            f'data-dz-action="edit" '
            f'data-dz-entity="{entity_name_attr}">Edit</a>'
        )
    if delete_url:
        actions.append(
            f'<button class="dz-button dz-button-destructive" '  # nosemgrep
            f'data-dazzle-action="{entity_name_attr}.delete" '
            f'data-dz-action="delete" '
            f'data-dz-entity="{entity_name_attr}" '
            f'hx-delete="{_esc(delete_url, quote=True)}" '
            f'hx-confirm="Delete this {_esc(entity_name_lower, quote=True)}?" '
            f'hx-trigger="click" hx-target="body" hx-swap="innerHTML">Delete</button>'
        )

    header_html = (
        '<div class="dz-detail-header">'
        '<div class="dz-detail-header-title">'
        f'<a href="{back_url}" class="dz-button dz-button-ghost" '  # nosemgrep
        f"onclick=\"var d=this.closest('#dz-detail-drawer');"
        f"if(d&&window.dzDrawer){{window.dzDrawer.close();return false}}"
        f"try{{if(document.referrer&&new URL(document.referrer).origin===location.origin)"
        f'{{history.back();return false}}}}catch(e){{}}">&larr; Back</a>'
        f'<h2 class="dz-detail-title">{title}</h2>'
        "</div>"
        f'<div class="dz-detail-actions">{"".join(actions)}</div>'
        "</div>"
    )

    # --- Transitions ----------------------------------------------
    transitions = list(getattr(detail, "transitions", None) or [])
    status_field = str(getattr(detail, "status_field", "") or "")
    transitions_html = ""
    if transitions:
        buttons: list[str] = []
        for tr in transitions:
            to_state_attr = _esc(getattr(tr, "to_state", "") or "", quote=True)
            api_url_attr = _esc(getattr(tr, "api_url", "") or "", quote=True)
            label = _esc(getattr(tr, "label", ""))
            hx_vals = f'{{"{_esc(status_field, quote=True)}": "{to_state_attr}"}}'
            buttons.append(
                f'<button class="dz-button dz-button-outline" '  # nosemgrep
                f'data-dazzle-action="{entity_name_attr}.transition.{to_state_attr}" '
                f'data-dz-action="transition.{to_state_attr}" '
                f'data-dz-entity="{entity_name_attr}" '
                f'hx-put="{api_url_attr}" '
                f"hx-vals='{hx_vals}' "
                f'hx-trigger="click" hx-target="body" hx-swap="innerHTML">{label}</button>'
            )
        transitions_html = (
            f'<div class="dz-detail-toolbar" data-dazzle-transitions="{entity_name_attr}">'
            f"{''.join(buttons)}</div>"
        )

    # --- External link actions ------------------------------------
    external_links = list(getattr(detail, "external_link_actions", None) or [])
    external_html = ""
    if external_links:
        buttons = []
        for link in external_links:
            url_attr = _esc(getattr(link, "url", "") or "", quote=True)
            name_attr = _esc(getattr(link, "name", "") or "", quote=True)
            label = _esc(getattr(link, "label", ""))
            new_tab_attrs = ""
            if getattr(link, "new_tab", False):
                new_tab_attrs = ' target="_blank" rel="noopener noreferrer"'
            buttons.append(
                f'<a href="{url_attr}"{new_tab_attrs} '  # nosemgrep
                f'class="dz-button dz-button-outline" '
                f'data-dazzle-action="{entity_name_attr}.external.{name_attr}">'
                f"{label}</a>"
            )
        external_html = (
            f'<div class="dz-detail-toolbar" data-dazzle-external-links="{entity_name_attr}">'
            f"{''.join(buttons)}</div>"
        )

    # --- Integration actions --------------------------------------
    integration_actions = list(getattr(detail, "integration_actions", None) or [])
    integration_html = ""
    if integration_actions:
        buttons = []
        for action in integration_actions:
            integration_name = _esc(getattr(action, "integration_name", "") or "", quote=True)
            mapping_name = _esc(getattr(action, "mapping_name", "") or "", quote=True)
            api_url_attr = _esc(getattr(action, "api_url", "") or "", quote=True)
            label_text = getattr(action, "label", "")
            label = _esc(label_text)
            buttons.append(
                f'<button class="dz-button dz-button-outline" '  # nosemgrep
                f'data-dazzle-action="{entity_name_attr}.integration.'
                f'{integration_name}.{mapping_name}" '
                f'hx-post="{api_url_attr}" hx-trigger="click" hx-target="body" hx-swap="innerHTML" '
                f'hx-confirm="Execute {_esc(label_text, quote=True)}?">{label}</button>'
            )
        integration_html = (
            f'<div class="dz-detail-toolbar" '
            f'data-dazzle-integration-actions="{entity_name_attr}">'
            f"{''.join(buttons)}</div>"
        )

    # --- Detail field list ---------------------------------------
    item = getattr(detail, "item", None) or {}
    if not isinstance(item, dict):
        try:
            item = dict(item)
        except Exception:
            item = {}
    fields = list(getattr(detail, "fields", None) or [])
    field_rows: list[str] = []
    for field in fields:
        if not bool(getattr(field, "visible", True)):
            continue
        name = str(getattr(field, "name", "") or "")
        value = item.get(name, "")
        label = _esc(getattr(field, "label", ""))
        value_html = _render_field_value(field, value, item)
        field_rows.append(
            '<div class="dz-detail-row">'
            f'<dt class="dz-detail-label">{label}</dt>'
            f'<dd class="dz-detail-value">{value_html}</dd>'
            "</div>"
        )
    fields_html = (
        '<div class="dz-detail-card">'
        '<div class="dz-detail-card-body">'
        f'<dl class="dz-detail-list">{"".join(field_rows)}</dl>'
        "</div></div>"
    )

    # --- Related groups ------------------------------------------
    related_html = ""
    if related_groups:
        group_blocks: list[str] = []
        for group in related_groups:
            group_id_attr = _esc(getattr(group, "group_id", "") or "", quote=True)
            is_auto = bool(getattr(group, "is_auto", False))
            label_html = ""
            if len(related_groups) > 1 or not is_auto:
                label_html = (
                    f'<h3 class="dz-detail-related-label">{_esc(getattr(group, "label", ""))}</h3>'
                )
            inner = _render_related_group(group, item)
            group_blocks.append(
                '<div class="dz-detail-related-group" '  # nosemgrep
                f'data-dazzle-related-group="{group_id_attr}">'
                f"{label_html}{inner}"
                "</div>"
            )
        related_html = "".join(group_blocks)

    # --- Audit history slot --------------------------------------
    audit_html = ""
    if getattr(detail, "show_history", False) and item.get("id"):
        item_id_attr = _esc(item["id"], quote=True)
        audit_html = (
            '<div class="dz-detail-audit-history" '  # nosemgrep
            f'hx-get="/_dazzle/audit-history/{entity_name_attr}/{item_id_attr}" '
            'hx-trigger="load" hx-swap="innerHTML">'
            '<p class="dz-audit-history__loading" aria-live="polite">'
            "Loading history…</p>"
            "</div>"
        )

    return (
        f'<div class="{outer_cls}" '  # nosemgrep
        f'data-dazzle-entity="{entity_name_attr}" '
        f'data-dz-entity="{entity_name_attr}"'
        f"{entity_id_attr_html}>"
        f"{header_html}{transitions_html}{external_html}{integration_html}"
        f"{fields_html}{related_html}{audit_html}"
        "</div>"
    )
