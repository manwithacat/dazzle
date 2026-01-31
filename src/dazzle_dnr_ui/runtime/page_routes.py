"""
Page routes for server-rendered DNR pages.

Creates FastAPI routes that render full HTML pages using Jinja2 templates.
Each workspace+surface combination gets a GET route that:
1. Calls the template compiler to get a PageContext
2. Fetches data from the backend service
3. Renders the Jinja2 template
4. Returns an HTMLResponse
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from dazzle.core import ir

try:
    from fastapi import APIRouter, Request
    from fastapi.responses import HTMLResponse

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


def create_page_routes(
    appspec: ir.AppSpec,
    backend_url: str = "http://127.0.0.1:8000",
    theme_css: str = "",
) -> APIRouter:
    """
    Create FastAPI page routes from an AppSpec.

    Each surface becomes a page route that renders server-side HTML.

    Args:
        appspec: Complete application specification.
        backend_url: URL of the backend API for data fetching.
        theme_css: Pre-compiled theme CSS to inject.

    Returns:
        FastAPI router with page routes.
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is not installed")

    from dazzle_dnr_ui.converters.template_compiler import compile_appspec_to_templates
    from dazzle_dnr_ui.runtime.template_renderer import render_page

    router = APIRouter()

    # Compile all surfaces to template contexts
    page_contexts = compile_appspec_to_templates(appspec)

    # Inject theme CSS into all contexts
    for ctx in page_contexts.values():
        ctx.theme_css = theme_css

    def _make_page_handler(route_path: str, ctx: Any) -> Any:
        """Create a closure-based handler for a specific page route."""

        async def page_handler(request: Request) -> HTMLResponse:
            # Set current route for nav highlighting
            ctx.current_route = route_path

            # For detail/edit pages, extract {id} from path params
            path_id = request.path_params.get("id")
            if path_id and ctx.detail:
                # Fetch item data from backend API
                import json
                import urllib.request

                entity_api = ctx.detail.delete_url or ctx.detail.back_url
                if entity_api and "{id}" in entity_api:
                    fetch_url = f"{backend_url}{entity_api.replace('{id}', str(path_id))}"
                else:
                    fetch_url = None

                if fetch_url:
                    try:
                        req = urllib.request.Request(fetch_url)
                        with urllib.request.urlopen(req, timeout=5) as resp:
                            ctx.detail.item = json.loads(resp.read())
                    except Exception:
                        ctx.detail.item = {"id": path_id, "error": "Failed to load"}

                # Fix URLs with actual ID
                if ctx.detail.edit_url:
                    ctx.detail.edit_url = ctx.detail.edit_url.replace("{id}", str(path_id))
                if ctx.detail.delete_url:
                    ctx.detail.delete_url = ctx.detail.delete_url.replace("{id}", str(path_id))

            if path_id and ctx.form and ctx.form.mode == "edit":
                # Fetch existing data for edit form
                import json
                import urllib.request

                fetch_url = f"{backend_url}{ctx.form.action_url.replace('{id}', str(path_id))}"
                try:
                    req = urllib.request.Request(fetch_url)
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        ctx.form.initial_values = json.loads(resp.read())
                except Exception:
                    pass

                ctx.form.action_url = ctx.form.action_url.replace("{id}", str(path_id))
                if ctx.form.cancel_url:
                    ctx.form.cancel_url = ctx.form.cancel_url.replace("{id}", str(path_id))

            if ctx.table:
                # Fetch list data from backend
                import json
                import urllib.request

                fetch_url = f"{backend_url}{ctx.table.api_endpoint}"
                search = request.query_params.get("search", "")
                page_num = request.query_params.get("page", "1")
                if search:
                    fetch_url += f"?search={search}&page={page_num}"
                elif page_num != "1":
                    fetch_url += f"?page={page_num}"

                try:
                    req = urllib.request.Request(fetch_url)
                    with urllib.request.urlopen(req, timeout=5) as resp:
                        data = json.loads(resp.read())
                        items = data.get("items", [])
                        # Convert Pydantic-serialized items to plain dicts
                        if items and isinstance(items[0], dict):
                            ctx.table.rows = items
                        ctx.table.total = data.get("total", len(items))
                except Exception:
                    ctx.table.rows = []
                    ctx.table.total = 0

            html = render_page(ctx)
            return HTMLResponse(content=html)

        return page_handler

    # Register routes
    for route_path, ctx in page_contexts.items():
        # Convert {id} to FastAPI's :id format
        fastapi_path = route_path.replace("{id}", "{id:path}")

        handler = _make_page_handler(route_path, ctx)
        router.get(fastapi_path, response_class=HTMLResponse)(handler)

    return router
