"""Fragment routes for composable HTMX fragments.

Provides search and select endpoints that proxy to configured external
API sources and return rendered HTML fragments.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)


def create_fragment_router(
    fragment_sources: dict[str, dict[str, Any]] | None = None,
) -> APIRouter:
    """Create the fragment routes router.

    Args:
        fragment_sources: Registry of external API sources keyed by name.
            Each entry should have: url, display_key, value_key, secondary_key, headers.
    """
    router = APIRouter(prefix="/api/_fragments", tags=["Fragments"])
    sources = fragment_sources or {}

    @router.get("/search", response_class=HTMLResponse)
    async def fragment_search(
        request: Request,
        source: str = Query(..., description="Source integration name"),
        q: str = Query("", description="Search query"),
        min_chars: int = Query(3, description="Minimum characters before search"),
    ) -> HTMLResponse:
        """Search an external API source and return rendered result items."""
        if len(q) < min_chars:
            return HTMLResponse(
                '<div class="p-3 text-sm text-base-content/50">'
                f"Type at least {min_chars} characters to search...</div>"
            )

        source_config = sources.get(source)
        if not source_config:
            return HTMLResponse(
                f'<div class="p-3 text-sm text-error">Unknown source: {source}</div>'
            )

        try:
            import httpx

            search_url = source_config["url"]
            headers = source_config.get("headers", {})
            params = source_config.get("query_param", "q")

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    search_url,
                    params={params: q},
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()

            # Extract items from response (support nested results)
            items_key = source_config.get("items_key", "items")
            items: list[dict[str, Any]] = (
                data if isinstance(data, list) else data.get(items_key, [])
            )

            display_key = source_config.get("display_key", "name")
            value_key = source_config.get("value_key", "id")
            secondary_key = source_config.get("secondary_key", "")
            field_name = request.query_params.get("field_name", source)

            # Render results using template
            from dazzle_dnr_ui.runtime.template_renderer import render_fragment

            html = render_fragment(
                "fragments/search_results.html",
                items=items,
                display_key=display_key,
                value_key=value_key,
                secondary_key=secondary_key,
                field_name=field_name,
                query=q,
                min_chars=min_chars,
                select_endpoint=f"/api/_fragments/select?source={source}",
            )
            return HTMLResponse(html)

        except Exception as e:
            logger.warning(f"Fragment search error for source={source}: {e}")
            return HTMLResponse(f'<div class="p-3 text-sm text-error">Search failed: {e}</div>')

    @router.get("/select", response_class=HTMLResponse)
    async def fragment_select(
        request: Request,
        source: str = Query(..., description="Source integration name"),
        id: str = Query(..., description="Selected item ID"),
    ) -> HTMLResponse:
        """Fetch a full record and return OOB swap fragments for autofill fields."""
        source_config = sources.get(source)
        if not source_config:
            return HTMLResponse(
                f'<div class="p-3 text-sm text-error">Unknown source: {source}</div>'
            )

        try:
            import httpx

            detail_url = source_config.get("detail_url", source_config["url"])
            headers = source_config.get("headers", {})

            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"{detail_url}/{id}",
                    headers=headers,
                )
                resp.raise_for_status()
                record = resp.json()

            # Build OOB swap fragments for autofill fields
            autofill = source_config.get("autofill", {})
            display_key = source_config.get("display_key", "name")
            value_key = source_config.get("value_key", "id")
            field_name = request.query_params.get("field_name", source)

            oob_parts = []

            # Update the hidden value input
            oob_parts.append(
                f'<input type="hidden" name="{field_name}" id="field-{field_name}" '
                f'data-dazzle-field="{field_name}" value="{record.get(value_key, id)}" '
                f'hx-swap-oob="true" />'
            )

            # Update the visible search input with the display value
            display_val = record.get(display_key, str(id))
            oob_parts.append(
                f'<input type="text" id="search-input-{field_name}" '
                f'class="input input-bordered w-full" value="{display_val}" '
                f'hx-swap-oob="true" />'
            )

            # Autofill mapped fields
            for result_field, form_field in autofill.items():
                val = record.get(result_field, "")
                oob_parts.append(
                    f'<input id="field-{form_field}" name="{form_field}" '
                    f'data-dazzle-field="{form_field}" value="{val}" '
                    f'hx-swap-oob="true" />'
                )

            # Close the dropdown
            html = f'<div class="p-3 text-sm text-success">Selected: {display_val}</div>'
            html += "\n".join(oob_parts)

            return HTMLResponse(html)

        except Exception as e:
            logger.warning(f"Fragment select error for source={source}, id={id}: {e}")
            return HTMLResponse(f'<div class="p-3 text-sm text-error">Selection failed: {e}</div>')

    return router
