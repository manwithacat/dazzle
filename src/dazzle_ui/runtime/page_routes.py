"""
Page routes for server-rendered Dazzle pages.

Creates FastAPI routes that render full HTML pages using Jinja2 templates.
Each workspace+surface combination gets a GET route that:
1. Calls the template compiler to get a PageContext
2. Fetches data from the backend service
3. Renders the Jinja2 template
4. Returns an HTMLResponse
"""

import logging
from collections.abc import Callable
from typing import Any

from dazzle.core import ir

logger = logging.getLogger(__name__)

try:
    from fastapi import APIRouter, HTTPException, Request
    from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False


def create_page_routes(
    appspec: ir.AppSpec,
    backend_url: str = "http://127.0.0.1:8000",
    theme_css: str = "",
    get_auth_context: Callable[..., Any] | None = None,
    app_prefix: str = "",
) -> APIRouter:
    """
    Create FastAPI page routes from an AppSpec.

    Each surface becomes a page route that renders server-side HTML.

    Args:
        appspec: Complete application specification.
        backend_url: URL of the backend API for data fetching.
        theme_css: Pre-compiled theme CSS to inject.
        get_auth_context: Optional callable(request) -> AuthContext for user info.
        app_prefix: URL prefix for page routes (e.g. "/app").

    Returns:
        FastAPI router with page routes.
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is not installed")

    from dazzle_back.runtime.surface_access import (
        SurfaceAccessConfig,
        SurfaceAccessDenied,
        check_surface_access,
    )
    from dazzle_ui.converters.template_compiler import compile_appspec_to_templates
    from dazzle_ui.runtime.template_renderer import render_page

    router = APIRouter()

    # Compile all surfaces to template contexts
    page_contexts = compile_appspec_to_templates(appspec, app_prefix=app_prefix)

    # Build route -> access config mapping from surface specs
    access_configs: dict[str, SurfaceAccessConfig] = {}
    for surface in appspec.surfaces:
        if surface.access is not None:
            access_configs[surface.name] = SurfaceAccessConfig.from_spec(surface.access)

    # Inject theme CSS into all contexts
    for ctx in page_contexts.values():
        ctx.theme_css = theme_css

    def _make_page_handler(route_path: str, ctx: Any, view_name: str | None = None) -> Any:
        """Create a closure-based handler for a specific page route."""

        async def page_handler(request: Request) -> Response:
            # Set current route for nav highlighting
            ctx.current_route = route_path

            # Inject auth context if available
            auth_ctx = None
            if get_auth_context is not None:
                try:
                    auth_ctx = get_auth_context(request)
                    ctx.is_authenticated = bool(auth_ctx and auth_ctx.is_authenticated)
                    if auth_ctx and auth_ctx.user:
                        ctx.user_email = auth_ctx.user.email or ""
                        ctx.user_name = auth_ctx.user.username or ""
                        # Persona-aware nav filtering: match user roles against
                        # per-persona nav variants compiled from workspace access.
                        roles = getattr(auth_ctx.user, "roles", None) or []
                        ctx.user_roles = list(roles)
                        if ctx.nav_by_persona and roles:
                            for role in roles:
                                persona_nav = ctx.nav_by_persona.get(role)
                                if persona_nav is not None:
                                    ctx.nav_items = persona_nav
                                    break
                except Exception:
                    logger.debug("Failed to resolve auth context for page", exc_info=True)

            # Enforce surface access control
            surface_name = view_name or getattr(ctx, "view_name", None)
            if surface_name and surface_name in access_configs:
                ac = access_configs[surface_name]
                user = None
                if auth_ctx and auth_ctx.is_authenticated and auth_ctx.user:
                    user = {"id": getattr(auth_ctx.user, "id", None)}
                try:
                    check_surface_access(ac, user, is_api_request=False)
                except SurfaceAccessDenied as e:
                    if e.is_auth_required and e.redirect_url:
                        return RedirectResponse(url=e.redirect_url, status_code=302)
                    return JSONResponse(
                        status_code=403,
                        content={"detail": e.reason},
                    )

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
                    logger.warning("Failed to fetch initial form values", exc_info=True)

                ctx.form.action_url = ctx.form.action_url.replace("{id}", str(path_id))
                if ctx.form.cancel_url:
                    ctx.form.cancel_url = ctx.form.cancel_url.replace("{id}", str(path_id))

            if ctx.table:
                # Fetch list data from backend
                import json
                import urllib.parse
                import urllib.request

                # Forward all DataTable query params to backend API
                api_params: dict[str, str] = {}
                for key in ("page", "page_size", "sort", "dir", "search"):
                    val = request.query_params.get(key)
                    if val:
                        api_params[key] = val
                for key, val in request.query_params.items():
                    if key.startswith("filter[") and val:
                        api_params[key] = val
                api_params.setdefault("page", "1")

                query_string = urllib.parse.urlencode(api_params)
                fetch_url = f"{backend_url}{ctx.table.api_endpoint}?{query_string}"

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

                # Update table context with current sort/filter state from request
                ctx.table.sort_field = request.query_params.get(
                    "sort", ctx.table.default_sort_field
                )
                ctx.table.sort_dir = request.query_params.get("dir", ctx.table.default_sort_dir)
                ctx.table.filter_values = {
                    k[7:-1]: v
                    for k, v in request.query_params.items()
                    if k.startswith("filter[") and k.endswith("]") and v
                }

            from dazzle_back.runtime.htmx_response import HtmxDetails

            htmx = HtmxDetails.from_request(request)

            # Boosted navigations: update nav highlighting from the actual URL
            if htmx.current_url:
                from urllib.parse import urlparse

                ctx.current_route = urlparse(htmx.current_url).path

            # Any HTMX request can receive body-only HTML — the client
            # extracts <body> content anyway.  History-restore is the one
            # exception: the browser needs a full document for cache misses.
            html = render_page(ctx, partial=htmx.is_htmx and not htmx.is_history_restore)
            return HTMLResponse(content=html)

        return page_handler

    # Register routes
    for route_path, ctx in page_contexts.items():
        # Convert {id} to FastAPI's :id format
        fastapi_path = route_path.replace("{id}", "{id:path}")

        handler = _make_page_handler(route_path, ctx, view_name=getattr(ctx, "view_name", None))
        router.get(fastapi_path, response_class=HTMLResponse)(handler)

    # Register workspace routes — workspaces use their own template, not the
    # surface page template, so they get separate handlers.
    workspaces = getattr(appspec, "workspaces", []) or []
    if workspaces:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        # Build nav items for workspace pages (same logic as template_compiler)
        ws_nav_items = []
        for ws in workspaces:
            ws_nav_items.append(
                {
                    "label": ws.title or ws.name.replace("_", " ").title(),
                    "route": f"{app_prefix}/workspaces/{ws.name}",
                    "allow_personas": list(ws.access.allow_personas)
                    if getattr(ws, "access", None)
                    else [],
                }
            )
        ws_app_name = appspec.title or appspec.name.replace("_", " ").title()

        for workspace in workspaces:
            ws_ctx = build_workspace_context(workspace, appspec)
            _ws_ctx = ws_ctx
            _ws_route = f"{app_prefix}/workspaces/{workspace.name}"
            _ws_allowed = (
                list(workspace.access.allow_personas) if getattr(workspace, "access", None) else []
            )

            def _make_workspace_handler(
                ws_context: Any = _ws_ctx,
                ws_route: str = _ws_route,
                ws_allowed_personas: list[str] = _ws_allowed,
            ) -> Any:
                async def workspace_handler(request: Request) -> Response:
                    from dazzle_ui.runtime.template_renderer import render_fragment

                    # Inject auth context if available
                    visible_nav = list(ws_nav_items)
                    is_authenticated = False
                    user_email = ""
                    user_name = ""
                    user_roles: list[str] = []

                    if get_auth_context is not None:
                        try:
                            auth_ctx = get_auth_context(request)
                            if auth_ctx and auth_ctx.is_authenticated:
                                is_authenticated = True
                                user_email = auth_ctx.user.email if auth_ctx.user else ""
                                user_name = auth_ctx.user.username if auth_ctx.user else ""
                                user_roles = list(getattr(auth_ctx.user, "roles", None) or [])
                                # Filter nav by persona access
                                visible_nav = [
                                    {"label": item["label"], "route": item["route"]}
                                    for item in ws_nav_items
                                    if not item["allow_personas"]
                                    or any(r in item["allow_personas"] for r in user_roles)
                                ]
                        except Exception:
                            logger.debug("Failed to resolve auth for workspace nav", exc_info=True)

                    # Enforce workspace persona access control (superusers bypass)
                    is_superuser = (
                        get_auth_context is not None
                        and auth_ctx is not None  # type: ignore[possibly-undefined]
                        and auth_ctx.user is not None
                        and auth_ctx.user.is_superuser
                    )
                    if ws_allowed_personas and not is_superuser:
                        if not user_roles or not any(r in ws_allowed_personas for r in user_roles):
                            raise HTTPException(
                                status_code=403,
                                detail="You don't have permission to access this workspace.",
                            )

                    from dazzle_back.runtime.htmx_response import HtmxDetails

                    htmx = HtmxDetails.from_request(request)

                    effective_route = ws_route
                    if htmx.current_url:
                        from urllib.parse import urlparse

                        effective_route = urlparse(htmx.current_url).path

                    html = render_fragment(
                        "workspace/workspace.html",
                        workspace=ws_context,
                        nav_items=visible_nav,
                        app_name=ws_app_name,
                        current_route=effective_route,
                        is_authenticated=is_authenticated,
                        user_email=user_email,
                        user_name=user_name,
                        _htmx_partial=htmx.is_htmx and not htmx.is_history_restore,
                    )
                    return HTMLResponse(content=html)

                return workspace_handler

            handler = _make_workspace_handler(_ws_ctx, _ws_route)
            router.get(f"/workspaces/{workspace.name}", response_class=HTMLResponse)(handler)

        # When workspaces exist and "/" is not already registered as a page,
        # add a redirect so users landing at the app root reach a real page.
        # Uses persona default_workspace to pick the right workspace per user.
        if "/" not in page_contexts:
            # Build persona → workspace route mapping
            _persona_ws_routes: dict[str, str] = {}
            for persona in appspec.personas:
                if persona.default_workspace:
                    _persona_ws_routes[persona.id] = (
                        f"{app_prefix}/workspaces/{persona.default_workspace}"
                    )
            _fallback_ws_route = f"{app_prefix}/workspaces/{workspaces[0].name}"

            async def root_redirect(request: Request) -> Response:
                # Try to resolve the user's persona and redirect to their workspace
                if get_auth_context is not None:
                    try:
                        auth_ctx = get_auth_context(request)
                        if auth_ctx and auth_ctx.is_authenticated and auth_ctx.roles:
                            for role in auth_ctx.roles:
                                route = _persona_ws_routes.get(role)
                                if route:
                                    return RedirectResponse(url=route, status_code=302)
                    except Exception:
                        pass
                return RedirectResponse(url=_fallback_ws_route, status_code=302)

            router.get("/", response_class=HTMLResponse)(root_redirect)

    return router
