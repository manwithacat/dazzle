"""Filterable-table renderer (Phase 4, v0.67.76).

Inline Python port of `components/filterable_table.html` plus the 3
toolbar fragments:
  - `fragments/search_input.html`
  - `fragments/filter_bar.html`
  - `fragments/bulk_actions.html`

The table rows + pagination + sentinel are already ported in
`dazzle.http.runtime.route_generator` (v0.67.65 + v0.67.67-v0.67.68);
this module imports those helpers rather than duplicating them.

All Alpine bindings (`dzTable` controller: loading, colMenuOpen,
isColumnVisible, toggleColumn, toggleSort, ariaSortDir, sortIcon,
toggleSelectAll, bulkCount, startColumnResize, bulkDelete,
clearSelection, dzFilterRefSelect) and HTMX wiring preserved
verbatim. CSS classes match the legacy template byte-for-byte
(dz-table-*, dz-filter-*, dz-search-*, dz-bulk-*).
"""

from __future__ import annotations

import json
from typing import Any

from dazzle.render.html import esc as _esc


def _render_search_input(table: Any, endpoint: str, target: str) -> str:
    """Port of `fragments/search_input.html`."""
    entity_name = str(getattr(table, "entity_name", "") or "")
    entity_label = entity_name.replace("_", " ").lower()
    placeholder = f"Search {entity_label}..."
    placeholder_attr = _esc(placeholder, quote=True)
    table_id = str(getattr(table, "table_id", "") or "dt-table")
    table_id_attr = _esc(table_id, quote=True)
    search_id = f"dz-search-{table_id}"
    search_id_attr = _esc(search_id, quote=True)
    title = _esc(getattr(table, "title", ""))
    endpoint_attr = _esc(endpoint, quote=True)
    target_attr = _esc(target, quote=True)

    return (
        '<div x-data="{ query: \'\' }" class="dz-search-input-wrap">'  # nosemgrep
        f'<label for="{search_id_attr}" class="visually-hidden">Search {title}</label>'
        '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" '
        'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round" class="dz-search-input-icon" '
        'aria-hidden="true">'
        '<circle cx="11" cy="11" r="8"></circle>'
        '<line x1="21" y1="21" x2="16.65" y2="16.65"></line>'
        "</svg>"
        f'<input type="search" id="{search_id_attr}" name="search" '
        'x-model="query" '
        f'placeholder="{placeholder_attr}" '
        f'aria-label="Search {title}" '
        'class="dz-search-input" '
        f'hx-get="{endpoint_attr}" '
        f'hx-target="{target_attr}" '
        'hx-trigger="keyup changed delay:300ms" '
        'hx-swap="innerHTML" '
        'hx-include="closest [data-dazzle-table]" '
        'hx-headers=\'{"Accept": "text/html"}\' '
        f'hx-indicator="#{table_id_attr}-loading-sr" />'
        '<button x-show="query.length > 0" x-cloak '
        "@click=\"query = ''; $el.previousElementSibling.value = ''; "
        "htmx.trigger($el.previousElementSibling, 'keyup')\" "
        'type="button" aria-label="Clear search" class="dz-search-clear">'
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" '
        'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<line x1="18" y1="6" x2="6" y2="18"></line>'
        '<line x1="6" y1="6" x2="18" y2="18"></line>'
        "</svg></button></div>"
    )


def _render_filter_bar(table: Any) -> str:
    """Port of `fragments/filter_bar.html`."""
    table_id = str(getattr(table, "table_id", "") or "dt-table")
    table_id_attr = _esc(table_id, quote=True)
    tbody_target = f"#{table_id_attr}-body"
    api_endpoint = _esc(getattr(table, "api_endpoint", "") or "", quote=True)
    filter_values = getattr(table, "filter_values", None) or {}
    columns = list(getattr(table, "columns", None) or [])

    parts: list[str] = ['<div class="dz-filter-bar">']
    for col in columns:
        filterable = (
            col.get("filterable") if isinstance(col, dict) else getattr(col, "filterable", False)
        )
        if not filterable:
            continue
        col_key = col.get("key", "") if isinstance(col, dict) else getattr(col, "key", "")
        col_label = col.get("label", "") if isinstance(col, dict) else getattr(col, "label", "")
        col_key_attr = _esc(col_key, quote=True)
        col_label_text = _esc(col_label)
        filter_type = (
            col.get("filter_type", "") if isinstance(col, dict) else getattr(col, "filter_type", "")
        )
        filter_ref_entity = (
            col.get("filter_ref_entity", "")
            if isinstance(col, dict)
            else getattr(col, "filter_ref_entity", "")
        )
        filter_ref_api = (
            col.get("filter_ref_api", "")
            if isinstance(col, dict)
            else getattr(col, "filter_ref_api", "")
        )
        selected_value = filter_values.get(col_key, "") if filter_values else ""

        if filter_type == "select" and filter_ref_entity:
            control = (
                f'<select name="filter[{col_key_attr}]" '  # nosemgrep
                f'class="dz-filter-select" '
                f'data-ref-api="{_esc(filter_ref_api, quote=True)}" '
                f'data-selected-value="{_esc(selected_value, quote=True)}" '
                f'hx-get="{api_endpoint}" hx-target="{tbody_target}" '
                f'hx-swap="innerHTML" hx-trigger="change" '
                f'hx-include="closest [data-dazzle-table]" '
                f'hx-headers=\'{{"Accept": "text/html"}}\' '
                f'hx-indicator="#{table_id_attr}-loading-sr" '
                f'x-init="dzFilterRefSelect($el)">'
                '<option value="">All</option></select>'
            )
        elif filter_type == "select":
            options = list(
                col.get("filter_options", [])
                if isinstance(col, dict)
                else getattr(col, "filter_options", None) or []
            )
            opts_html_parts: list[str] = ['<option value="">All</option>']
            for opt in options:
                opt_val = (
                    opt.get("value", "") if isinstance(opt, dict) else getattr(opt, "value", "")
                )
                opt_label = (
                    opt.get("label", "") if isinstance(opt, dict) else getattr(opt, "label", "")
                )
                sel = " selected" if filter_values and filter_values.get(col_key) == opt_val else ""
                opts_html_parts.append(
                    f'<option value="{_esc(opt_val, quote=True)}"{sel}>{_esc(opt_label)}</option>'
                )
            control = (
                f'<select name="filter[{col_key_attr}]" '  # nosemgrep
                f'class="dz-filter-select" '
                f'hx-get="{api_endpoint}" hx-target="{tbody_target}" '
                f'hx-swap="innerHTML" hx-trigger="change" '
                f'hx-include="closest [data-dazzle-table]" '
                f'hx-headers=\'{{"Accept": "text/html"}}\' '
                f'hx-indicator="#{table_id_attr}-loading-sr">'
                f"{''.join(opts_html_parts)}</select>"
            )
        else:
            placeholder = f"Filter {col_label.lower()}…"
            control = (
                f'<input type="text" name="filter[{col_key_attr}]" '  # nosemgrep
                f'placeholder="{_esc(placeholder, quote=True)}" '
                f'value="{_esc(selected_value, quote=True)}" '
                f'class="dz-filter-input" '
                f'hx-get="{api_endpoint}" hx-target="{tbody_target}" '
                f'hx-swap="innerHTML" hx-trigger="keyup changed delay:300ms" '
                f'hx-include="closest [data-dazzle-table]" '
                f'hx-headers=\'{{"Accept": "text/html"}}\' '
                f'hx-indicator="#{table_id_attr}-loading-sr" />'
            )
        parts.append(
            '<div class="dz-filter-cell">'
            f'<label class="dz-filter-label">{col_label_text}</label>'
            f"{control}</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def _render_bulk_actions() -> str:
    """Port of `fragments/bulk_actions.html` — delete + clear-selection."""
    return (
        '<div class="dz-bulk-actions">'  # nosemgrep
        '<button @click="bulkDelete()" type="button" class="dz-bulk-delete">'
        '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" '
        'viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        '<polyline points="3 6 5 6 21 6"></polyline>'
        '<path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"></path>'
        '<path d="M10 11v6"></path>'
        '<path d="M14 11v6"></path>'
        '<path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"></path>'
        "</svg>"
        "<span>Delete <span data-dz-bulk-count-target>0</span> "
        'item<span class="dz-bulk-plural">s</span></span>'
        "</button>"
        '<button @click="clearSelection()" type="button" class="dz-bulk-clear">'
        "Clear selection</button>"
        "</div>"
    )


def render_filterable_table(table: Any, *, page_title: str = "") -> str:
    """Port of `components/filterable_table.html` (v0.67.76).

    Returns the full table chrome — Alpine dzTable wrapper, header,
    toolbar (search + filters + bulk actions), thead with column-visibility
    menu + sortable headers, tbody (loaded by HTMX from the api_endpoint),
    empty state, screen-reader loading region, and pagination footer.

    The row body is fetched by HTMX from `table.api_endpoint` and
    rendered by `htmx_render._render_table_row` server-side; this
    function does NOT inline the row markup itself.
    """
    if not table:
        return ""

    table_id = str(getattr(table, "table_id", "") or "dt-table")
    table_id_attr = _esc(table_id, quote=True)
    entity_name = str(getattr(table, "entity_name", "") or "")
    entity_name_attr = _esc(entity_name, quote=True)
    # #1487: prefer the entity's declared display title for the "New <Entity>"
    # CTA + empty-state copy; fall back to humanising the raw identifier.
    entity_label_text = str(getattr(table, "entity_title", "") or "") or entity_name.replace(
        "_", " "
    )
    entity_label_lower = entity_label_text.lower()
    title = _esc(getattr(table, "title", ""))
    title_attr = _esc(getattr(table, "title", ""), quote=True)
    api_endpoint = str(getattr(table, "api_endpoint", "") or "")
    api_endpoint_attr = _esc(api_endpoint, quote=True)
    columns = list(getattr(table, "columns", None) or [])
    bulk_actions = bool(getattr(table, "bulk_actions", False))
    search_enabled = bool(getattr(table, "search_enabled", False))
    create_url = str(getattr(table, "create_url", "") or "")
    page_size = int(getattr(table, "page_size", 10) or 10)
    pagination_mode = str(getattr(table, "pagination_mode", "") or "")
    search_first = bool(getattr(table, "search_first", False))

    # dzTable config JSON
    config = {
        "sortField": getattr(table, "default_sort_field", ""),
        "sortDir": getattr(table, "default_sort_dir", ""),
        "inlineEditable": list(getattr(table, "inline_editable", None) or []),
        "bulkActions": bulk_actions,
        "entityName": entity_name,
    }
    config_json = json.dumps(config)

    # Page title (visually-hidden h1)
    page_title_html = ""
    if page_title:
        page_title_html = f'<h1 class="dz-page-title visually-hidden">{_esc(page_title)}</h1>'

    # Column visibility menu
    col_menu_html = ""
    if len(columns) > 3:
        items: list[str] = []
        for col in columns:
            hidden = col.get("hidden") if isinstance(col, dict) else getattr(col, "hidden", False)
            if hidden:
                continue
            col_key = col.get("key", "") if isinstance(col, dict) else getattr(col, "key", "")
            col_label = col.get("label", "") if isinstance(col, dict) else getattr(col, "label", "")
            ck = _esc(col_key, quote=True)
            cl = _esc(col_label, quote=True)
            items.append(
                '<label role="menuitemcheckbox" class="dz-table-col-menu-item">'  # nosemgrep
                '<input type="checkbox" class="dz-table-col-menu-checkbox" '
                f":checked=\"isColumnVisible('{ck}')\" "
                f"@change=\"toggleColumn('{ck}')\" "
                f'aria-label="Show {cl} column" />'
                f"<span>{_esc(col_label)}</span></label>"
            )
        col_menu_html = (
            '<div class="dz-table-col-menu" '  # nosemgrep
            '@click.outside="colMenuOpen = false">'
            '<button type="button" @click="colMenuOpen = !colMenuOpen" '
            ':aria-expanded="colMenuOpen" '
            'aria-label="Toggle column visibility" '
            'aria-haspopup="menu" '
            'class="dz-table-col-menu-trigger">'
            '<svg width="14" height="14" viewBox="0 0 14 14" fill="none" '
            'aria-hidden="true" xmlns="http://www.w3.org/2000/svg">'
            '<rect x="1" y="1" width="3" height="12" rx="0.5" stroke="currentColor" '
            'stroke-width="1.5"/>'
            '<rect x="5.5" y="1" width="3" height="12" rx="0.5" stroke="currentColor" '
            'stroke-width="1.5"/>'
            '<rect x="10" y="1" width="3" height="12" rx="0.5" stroke="currentColor" '
            'stroke-width="1.5"/>'
            "</svg>Columns</button>"
            '<div x-show="colMenuOpen" x-transition.opacity.duration.80ms '
            'role="menu" class="dz-table-col-menu-panel">'
            f"{''.join(items)}</div></div>"
        )

    # Create button
    create_html = ""
    if create_url:
        create_url_attr = _esc(create_url, quote=True)
        create_html = (
            f'<a href="{create_url_attr}" '  # nosemgrep
            f'data-dazzle-action="{entity_name_attr}.create" '
            'class="dz-button-primary">'
            '<svg width="12" height="12" viewBox="0 0 12 12" fill="none" '
            'aria-hidden="true" xmlns="http://www.w3.org/2000/svg">'
            '<path d="M6 1v10M1 6h10" stroke="currentColor" stroke-width="1.5" '
            'stroke-linecap="round"/></svg>'
            f"New {_esc(entity_label_text)}</a>"
        )

    header_html = (
        '<div class="dz-table-header">'
        f'<h2 class="dz-table-title">{title}</h2>'
        '<div class="dz-table-header-actions">'
        f"{col_menu_html}{create_html}"
        "</div></div>"
    )

    # Toolbar
    toolbar_parts: list[str] = []
    if search_enabled:
        toolbar_parts.append(_render_search_input(table, api_endpoint, f"#{table_id_attr}-body"))
    has_filters = any(
        (c.get("filterable") if isinstance(c, dict) else getattr(c, "filterable", False))
        for c in columns
    )
    if has_filters:
        toolbar_parts.append(
            f'<div class="dz-table-toolbar-filters">{_render_filter_bar(table)}</div>'
        )
    if bulk_actions:
        toolbar_parts.append(_render_bulk_actions())
    toolbar_html = (
        f'<div class="dz-table-toolbar">{"".join(toolbar_parts)}</div>'
        if toolbar_parts
        else '<div class="dz-table-toolbar"></div>'
    )

    # colgroup
    colgroup_parts: list[str] = []
    if bulk_actions:
        colgroup_parts.append('<col data-col="__select" style="width: 40px">')
    for col in columns:
        hidden = col.get("hidden") if isinstance(col, dict) else getattr(col, "hidden", False)
        if hidden:
            continue
        col_key = col.get("key", "") if isinstance(col, dict) else getattr(col, "key", "")
        ck = _esc(col_key, quote=True)
        colgroup_parts.append(
            f'<col data-col="{ck}" '  # nosemgrep
            f":style=\"columnWidths['{ck}'] ? 'width: ' + columnWidths['{ck}'] + 'px' : ''\">"
        )
    colgroup_parts.append('<col data-col="__actions" style="width: 64px">')
    colgroup_html = f"<colgroup>{''.join(colgroup_parts)}</colgroup>"

    # thead
    header_cells: list[str] = []
    if bulk_actions:
        header_cells.append(
            '<th scope="col" class="dz-table-th dz-table-th-select">'
            '<input type="checkbox" class="dz-table-col-menu-checkbox" '
            '@change="toggleSelectAll($event.target.checked)" '
            ':checked="bulkCount > 0 && bulkCount === '
            "$el.closest('table').querySelectorAll('tbody tr[data-dz-row-id]').length\" "
            ':indeterminate="bulkCount > 0 && bulkCount < '
            "$el.closest('table').querySelectorAll('tbody tr[data-dz-row-id]').length\" "
            'aria-label="Select all rows" /></th>'
        )
    for col in columns:
        hidden = col.get("hidden") if isinstance(col, dict) else getattr(col, "hidden", False)
        if hidden:
            continue
        col_key = col.get("key", "") if isinstance(col, dict) else getattr(col, "key", "")
        col_label = col.get("label", "") if isinstance(col, dict) else getattr(col, "label", "")
        sortable = col.get("sortable") if isinstance(col, dict) else getattr(col, "sortable", False)
        ck = _esc(col_key, quote=True)
        cl = _esc(col_label)
        cl_attr = _esc(col_label, quote=True)
        sort_attr = f" :aria-sort=\"ariaSortDir('{ck}')\"" if sortable else ""
        if sortable:
            label_body = (
                '<button type="button" '
                f"@click=\"toggleSort('{ck}')\" "
                f'aria-label="Sort by {cl_attr}" class="dz-table-sort-button">'
                f"{cl}"
                '<svg width="12" height="12" viewBox="0 0 12 12" fill="none" '
                'aria-hidden="true" xmlns="http://www.w3.org/2000/svg" '
                f":class=\"sortIcon('{ck}')\" "
                'class="dz-table-sort-icon">'
                '<path d="M2 4.5l4 4 4-4" stroke="currentColor" stroke-width="1.5" '
                'stroke-linecap="round" stroke-linejoin="round"/></svg>'
                "</button>"
            )
        else:
            label_body = cl
        resize_handle = (
            '<div role="separator" aria-orientation="vertical" '
            f'aria-label="Resize {cl_attr} column" '
            f"@pointerdown=\"startColumnResize('{ck}', $event)\" "
            'class="dz-table-resize-handle"></div>'
        )
        header_cells.append(
            f'<th scope="col" data-dz-col="{ck}" '  # nosemgrep
            f"x-show=\"isColumnVisible('{ck}')\"{sort_attr} "
            f'class="dz-table-th">{label_body}{resize_handle}</th>'
        )
    header_cells.append(
        '<th scope="col" class="dz-table-th dz-table-th-actions">'
        '<span class="visually-hidden">Actions</span></th>'
    )
    thead_html = f'<thead class="dz-table-head"><tr>{"".join(header_cells)}</tr></thead>'

    # tbody (HTMX-loaded)
    sort_field = getattr(table, "default_sort_field", "") or ""
    sort_dir = getattr(table, "default_sort_dir", "") or ""
    sort_qs = ""
    if sort_field:
        sort_qs = f"?sort={_esc(sort_field, quote=True)}&dir={_esc(sort_dir, quote=True)}"
    # #1399 slice 3: live-refresh — append `every Ns` to the tbody trigger so
    # the existing list data endpoint re-fetches on a poll. Parser floors at 5s.
    refresh_interval = getattr(table, "refresh_interval", None)
    _triggers: list[str] = []
    if not search_first:
        _triggers.append("load")
    if refresh_interval:
        _triggers.append(f"every {int(refresh_interval)}s")
    trigger_attr = f' hx-trigger="{", ".join(_triggers)}"' if _triggers else ""
    tbody_html = (
        f'<tbody id="{table_id_attr}-body" '  # nosemgrep
        f'hx-get="{api_endpoint_attr}{sort_qs}"'
        f"{trigger_attr} "
        'hx-swap="innerMorph" '
        'hx-headers=\'{"Accept": "text/html"}\' '
        f'hx-indicator="#{table_id_attr}-loading-sr" '
        '@htmx:before-request="loading = true" '
        '@htmx:after-settle="loading = false" '
        'class="dz-table-body">'
        "</tbody>"
    )

    # Empty state
    empty_button = ""
    if create_url:
        empty_button = (
            f'<a href="{_esc(create_url, quote=True)}" class="dz-button-primary">'  # nosemgrep
            '<svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">'
            '<path d="M6 1v10M1 6h10" stroke="currentColor" stroke-width="1.5" '
            'stroke-linecap="round"/></svg>'
            f"New {_esc(entity_label_text)}</a>"
        )
    empty_html = (
        f'<div id="{table_id_attr}-empty" role="status" class="dz-table-empty">'  # nosemgrep
        '<svg width="40" height="40" viewBox="0 0 40 40" fill="none" '
        'aria-hidden="true" xmlns="http://www.w3.org/2000/svg" '
        'class="dz-table-empty-icon">'
        '<rect x="4" y="4" width="32" height="32" rx="4" stroke="currentColor" '
        'stroke-width="2"/>'
        '<path d="M12 16h16M12 20h10M12 24h8" stroke="currentColor" stroke-width="1.5" '
        'stroke-linecap="round"/></svg>'
        f'<p class="dz-table-empty-title">No {_esc(entity_label_lower)}s found</p>'
        '<p class="dz-table-empty-hint">Try adjusting your search or filter criteria.</p>'
        f"{empty_button}</div>"
    )

    # Pagination
    pagination_html = ""
    if pagination_mode != "infinite":
        pagination_html = f'<div id="{table_id_attr}-pagination" class="dz-table-footer"></div>'

    # Loading indicator
    loading_sr_html = (
        f'<div id="{table_id_attr}-loading-sr" '
        'class="htmx-indicator visually-hidden" '
        'role="status" aria-label="Loading data">Loading…</div>'
    )

    # Live region
    live_region_html = (
        '<div id="dz-live-region" aria-live="polite" aria-atomic="true" '
        'class="visually-hidden"></div>'
    )

    return (
        f"{page_title_html}"
        f'<div id="{table_id_attr}" '  # nosemgrep
        f'data-dazzle-table="{entity_name_attr}" '
        f'x-data=\'dzTable("{table_id_attr}", "{api_endpoint_attr}", {config_json})\' '
        ':aria-busy="loading" '
        'data-dz-bulk-count="0" '
        'class="dz-table">'
        f"{header_html}{toolbar_html}"
        f'<div class="dz-table-scroll" style="--dz-list-rows: {page_size}">'
        '<div aria-hidden="true" class="dz-table-loading">'
        '<svg class="dz-table-loading-spinner" viewBox="0 0 24 24" fill="none" '
        'xmlns="http://www.w3.org/2000/svg">'
        '<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" '
        'stroke-width="2"/>'
        '<path class="opacity-75" fill="currentColor" '
        'd="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>'
        '<span class="visually-hidden">Loading…</span></div>'
        f'<div class="dz-table-scroll-x" role="region" '
        f'aria-label="{title_attr} table" tabindex="0">'
        f'<table class="dz-table-grid" data-entity="{entity_name_attr}" '
        f'aria-label="{title_attr}">'
        f'<caption class="visually-hidden">{title}</caption>'
        f"{colgroup_html}{thead_html}{tbody_html}</table>"
        f"{empty_html}"
        "</div></div>"
        f"{loading_sr_html}"
        f"{pagination_html}"
        f"{live_region_html}"
        "</div>"
    )
