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
    from dazzle.render.filters import _pagination_pages

    if not table:
        return ""
    total = int(table.get("total", 0) or 0)
    page_size = int(table.get("page_size", 50) or 50)
    if total <= page_size:
        return ""
    total_pages = (total + page_size - 1) // page_size
    current_page = int(table.get("page", 1) or 1)
    rows_label = "row" if total == 1 else "rows"

    # Convergence C1.1: page buttons are the HM grid controller's seam —
    # `data-dz-grid-goto` clicks compose ONE query from the DOM (sort +
    # filters + page), so pagination can no longer lose sort/filter state
    # (the per-button hx-get URLs used to carry a server-side snapshot).
    buttons: list[str] = []
    for p in _pagination_pages(current_page, total_pages):
        if p is None:
            buttons.append('<span class="dz-pagination-ellipsis" aria-hidden="true">…</span>')
            continue
        is_current = p == current_page
        current_cls = " is-current" if is_current else ""
        current_attr = ' aria-current="page"' if is_current else ""
        buttons.append(
            f'<button type="button" class="dz-pagination-page{current_cls}"{current_attr} '
            f'data-dz-grid-goto="{p}">{p}</button>'
        )

    # Dual-lock sole-emitter (contracts/pagination.py) — roots
    # data-dz-pagination + data-dz-grid-pagination + data-dz-grid-total.
    from dazzle.render.fragment.ingest import Pagination as PaginationSeam
    from dazzle.render.fragment.ingest import render_pagination

    return render_pagination(
        PaginationSeam(
            total=total,
            pages_html="".join(buttons),
            rows_label=rows_label,
        )
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
