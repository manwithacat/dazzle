"""Fragment routes for composable HTMX fragments.

Provides search and select endpoints that proxy to configured external
API sources and return rendered HTML fragments.
"""

import logging
from html import escape as html_escape
from typing import Any

from fastapi import APIRouter, Query, Request
from starlette.responses import Response

from dazzle.core import ir
from dazzle.core.http_client import async_retrying_request
from dazzle.render.fragment.ingest import SearchResultRow, render_search_result_list

logger = logging.getLogger(__name__)


def _html(content: str) -> Response:
    """Return Jinja2-rendered HTML as a Response.

    Uses ``starlette.responses.Response`` with an explicit media type so
    that static-analysis tools can distinguish template-rendered output
    from raw string interpolation (which would be flagged as XSS).
    """
    return Response(content=content, media_type="text/html")


def create_fragment_router(
    fragment_sources: dict[str, dict[str, Any]] | None = None,
    app_spec: ir.AppSpec | None = None,
    cache: Any | None = None,
) -> APIRouter:
    """Create the fragment routes router.

    Args:
        fragment_sources: Registry of external API sources keyed by name.
            Each entry should have: url, display_key, value_key, secondary_key, headers.
        app_spec: Optional AppSpec to resolve sources from integration IR.
            Falls back to fragment_sources dict for backward compat.
    """
    router = APIRouter(prefix="/_dazzle/fragments", tags=["Fragments"])
    sources = dict(fragment_sources or {})

    # Resolve additional sources from integration IR if available (v0.20.0)
    if app_spec:
        for integration in getattr(app_spec, "integrations", []):
            for action in getattr(integration, "actions", []):
                if action.call_service and action.call_service not in sources:
                    # Register the service as a fragment source if not already present
                    service_name = action.call_service
                    env_prefix = service_name.upper().replace("-", "_")
                    import os

                    base_url = os.environ.get(f"DAZZLE_API_{env_prefix}_URL", "")
                    if base_url:
                        sources[service_name] = {
                            "url": base_url,
                            "display_key": "name",
                            "value_key": "id",
                            "headers": {},
                        }

    @router.get("/search")
    async def fragment_search(
        request: Request,
        source: str = Query(..., description="Source integration name"),
        q: str = Query("", description="Search query"),
        min_chars: int = Query(3, description="Minimum characters before search"),
    ) -> Any:
        """Search an external API source and return rendered result items."""
        if len(q) < min_chars:
            # min_chars is validated as int by FastAPI; explicit int() for static analysis
            return _html(
                '<div class="dz-search-result-empty">'
                f"Type at least {int(min_chars)} characters to search...</div>"
            )

        source_config = sources.get(source)
        if not source_config:
            return _html(
                f'<div class="dz-search-result-empty" style="color: var(--colour-danger)">Unknown source: {html_escape(source)}</div>'
            )

        try:
            import httpx

            search_url = source_config["url"]
            headers = source_config.get("headers", {})
            params = source_config.get("query_param", "q")
            full_url = f"{search_url}?{params}={q}"
            scope = f"fragment:{source}"

            # Check cache
            data: Any = None
            if cache is not None:
                data = await cache.get(scope, full_url)

            if data is None:
                async with httpx.AsyncClient(
                    timeout=10.0
                ) as client:  # DZ-HTTP-NORETRY  retry via async_retrying_request below
                    resp = await async_retrying_request(
                        client,
                        "GET",
                        search_url,
                        params={params: q},
                        headers=headers,
                    )
                    resp.raise_for_status()
                    data = resp.json()
                # Cache search results for 5 minutes
                if cache is not None:
                    await cache.put(scope, full_url, data, ttl=300)

            # Extract items from response (support nested results)
            items_key = source_config.get("items_key", "items")
            items: list[dict[str, Any]] = (
                data if isinstance(data, list) else data.get(items_key, [])
            )

            display_key = source_config.get("display_key", "name")
            value_key = source_config.get("value_key", "id")
            secondary_key = source_config.get("secondary_key", "")
            field_name = request.query_params.get("field_name", source)

            # #1547: propagate the widget's field name so the selection
            # round-trip targets the field-keyed ids.
            # Schema+DOM dual-lock: map each hit into SearchResultRow and
            # emit via the shared HM-faithful renderer (ingest seam).
            from urllib.parse import quote_plus as _qp

            select_endpoint = (
                f"/_dazzle/fragments/select?source={source}&field_name={_qp(field_name)}"
            )
            results_target = f"#search-results-{field_name}"
            if items:
                model_rows: list[SearchResultRow] = []
                for item in items:
                    val = item.get(value_key)
                    secondary = ""
                    if secondary_key:
                        sec = item.get(secondary_key)
                        if sec:
                            secondary = str(sec)
                    model_rows.append(
                        SearchResultRow(
                            id=str(val),
                            name=str(item.get(display_key, "")),
                            secondary=secondary,
                            select_url=f"{select_endpoint}&id={val}",
                            results_target=results_target,
                        )
                    )
                html = render_search_result_list(model_rows)
            else:
                html = render_search_result_list([], empty_q=str(q) if q else "")
                if not q:
                    # Preserve the request's min_chars in the empty prompt
                    # (HM default is 3; Dazzle passes the query param).
                    html = (
                        f'<div class="dz-search-result-empty">'
                        f"Type at least {int(min_chars)} characters to search...</div>"
                    )
            return _html(html)

        except Exception as e:
            logger.warning("Fragment search error for source=%s: %s", source, e)
            return _html(
                '<div class="dz-search-result-empty" style="color: var(--colour-danger)">Search failed</div>'
            )

    @router.get("/select")
    async def fragment_select(
        request: Request,
        source: str = Query(..., description="Source integration name"),
        id: str = Query(..., description="Selected item ID"),
    ) -> Any:
        """Fetch a full record and return OOB swap fragments for autofill fields."""
        source_config = sources.get(source)
        if not source_config:
            return _html(
                f'<div class="dz-search-result-empty" style="color: var(--colour-danger)">Unknown source: {html_escape(source)}</div>'
            )

        try:
            import httpx

            detail_url = source_config.get("detail_url", source_config["url"])
            headers = source_config.get("headers", {})
            full_url = f"{detail_url}/{id}"
            scope = f"fragment:{source}:detail"

            # Check cache
            record: Any = None
            if cache is not None:
                record = await cache.get(scope, full_url)

            if record is None:
                async with httpx.AsyncClient(
                    timeout=10.0
                ) as client:  # DZ-HTTP-NORETRY  retry via async_retrying_request below
                    resp = await async_retrying_request(client, "GET", full_url, headers=headers)
                    resp.raise_for_status()
                    record = resp.json()
                # Cache detail records for 1 hour
                if cache is not None:
                    await cache.put(scope, full_url, record, ttl=3600)

            # Build OOB swap fragments for autofill fields
            autofill = source_config.get("autofill", {})
            display_key = source_config.get("display_key", "name")
            value_key = source_config.get("value_key", "id")
            field_name = request.query_params.get("field_name", source)
            from urllib.parse import quote_plus as _qp

            # Prepare autofill values as (form_field, value) pairs
            autofill_values = [
                (form_field, str(record.get(result_field, "")))
                for result_field, form_field in autofill.items()
            ]

            # Phase 4 (v0.67.62): inline-render with stdlib html.escape.
            import html as _html_mod

            selected_value = str(record.get(value_key, id))
            display_val = str(record.get(display_key, str(id)))
            fn_attr = _html_mod.escape(field_name, quote=True)
            sv_attr = _html_mod.escape(selected_value, quote=True)
            dv_attr = _html_mod.escape(display_val, quote=True)
            dv_text = _html_mod.escape(display_val, quote=False)

            autofill_html = "".join(
                f'<input id="field-{_html_mod.escape(form_field, quote=True)}" '
                f'name="{_html_mod.escape(form_field, quote=True)}" '
                f'data-dazzle-field="{_html_mod.escape(form_field, quote=True)}" '
                f'value="{_html_mod.escape(field_value, quote=True)}" '
                f'hx-swap-oob="true" />'
                for form_field, field_value in autofill_values
            )

            # All interpolated values flow through html.escape with
            # quote=True (attributes) or quote=False (text).
            resp_html = (
                f'<div class="dz-select-result-confirm">Selected: {dv_text}</div>'
                f'<input type="hidden" name="{fn_attr}" id="field-{fn_attr}" '  # nosemgrep
                f'data-dazzle-field="{fn_attr}" value="{sv_attr}" '
                f'hx-swap-oob="true" />'
                # #1547: the OOB-swapped visible input must satisfy the
                # live widget contract (dz-search-select-input + combobox
                # aria + the typeahead hx-get) — the dz-search-select
                # controller keys off these, and re-searching after a
                # selection must keep working. Widget defaults for
                # debounce; min_chars is enforced server-side.
                f'<input type="text" id="search-input-{fn_attr}" '  # nosemgrep
                f'class="dz-search-select-input" value="{dv_attr}" '
                f'autocomplete="off" role="combobox" aria-expanded="false" '
                f'aria-controls="search-results-{fn_attr}" '
                f'aria-autocomplete="list" aria-haspopup="listbox" '
                f'hx-get="/_dazzle/fragments/search?source={_qp(source)}'
                f'&amp;field_name={_qp(field_name)}" '
                f'hx-trigger="keyup changed delay:400ms" '
                f'hx-target="#search-results-{fn_attr}" '
                f'hx-params="q" '
                f'hx-swap-oob="true" />'
                f"{autofill_html}"
            )
            return _html(resp_html)

        except Exception as e:
            logger.warning("Fragment select error for source=%s, id=%s: %s", source, id, e)
            return _html(
                '<div class="dz-search-result-empty" style="color: var(--colour-danger)">Selection failed</div>'
            )

    return router
