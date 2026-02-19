"""
Page routes for server-rendered Dazzle pages.

Creates FastAPI routes that render full HTML pages using Jinja2 templates.
Each workspace+surface combination gets a GET route that:
1. Calls the template compiler to get a PageContext
2. Fetches data from the backend service
3. Renders the Jinja2 template
4. Returns an HTMLResponse
"""

import asyncio
import json
import logging
import os
import urllib.request
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


def _sync_fetch(url: str, cookies: dict[str, str] | None = None, timeout: int = 5) -> bytes:
    """Synchronous HTTP GET — runs in a thread to avoid blocking the event loop."""
    req = urllib.request.Request(url)
    if cookies:
        req.add_header("Cookie", "; ".join(f"{k}={v}" for k, v in cookies.items()))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data: bytes = resp.read()
        return data


async def _fetch_url(url: str, cookies: dict[str, str] | None = None) -> dict[str, Any]:
    """Async-safe HTTP GET that returns parsed JSON.

    Uses asyncio.to_thread so the blocking urllib call doesn't stall
    the event loop — critical when the backend runs in the same process.
    """
    raw = await asyncio.to_thread(_sync_fetch, url, cookies)
    result: dict[str, Any] = json.loads(raw)
    return result


def _resolve_backend_url(request: Any, fallback: str) -> str:
    """Derive the backend URL for internal API calls.

    Resolution order (first non-empty wins):

    1. ``DAZZLE_BACKEND_URL`` env var — explicit override for split-service
       deployments where the frontend can't discover the backend from its
       own request (e.g. frontend on Cloudflare, backend on AWS).
    2. ``PORT`` env var — single-dyno platforms (Heroku, Railway) where the
       port is dynamic.  Stays on localhost to avoid SSL/router overhead.
    3. ``request.base_url`` — same-origin setups where the page request
       already hit the correct host:port.
    4. ``fallback`` — hardcoded default (``http://127.0.0.1:8000``), used
       during local development.
    """
    explicit = os.environ.get("DAZZLE_BACKEND_URL", "").rstrip("/")
    if explicit:
        return explicit
    port = os.environ.get("PORT")
    if port:
        return f"http://127.0.0.1:{port}"
    try:
        base = str(request.base_url).rstrip("/")
        if base:
            return base
    except Exception:
        pass
    return fallback


async def _fetch_json(
    backend_url: str,
    api_pattern: str | None,
    path_id: Any,
    cookies: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Fetch a single entity record from the backend API.

    Args:
        backend_url: Base URL of the backend (e.g. "http://127.0.0.1:8000").
        api_pattern: URL pattern with ``{id}`` placeholder (e.g. "/contacts/{id}").
        path_id: The entity ID to substitute.
        cookies: Optional cookies to forward (e.g. session cookie for auth).

    Returns:
        Parsed JSON dict, or a fallback dict with ``error`` key on failure.
    """
    if not api_pattern or "{id}" not in api_pattern:
        return {"id": str(path_id), "error": "No API pattern"}
    url = f"{backend_url}{api_pattern.replace('{id}', str(path_id))}"
    try:
        return await _fetch_url(url, cookies)
    except Exception:
        logger.warning("Failed to fetch entity data from %s", url, exc_info=True)
        return {"id": str(path_id), "error": "Failed to load"}


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

            # Derive backend URL from request so it works on dynamic-port
            # platforms (Heroku, Railway, etc.) where the default 8000 is wrong.
            effective_backend_url = _resolve_backend_url(request, backend_url)

            # Forward session cookies so internal API calls are authenticated.
            # Without this, CRUD endpoints return 404 (auth-required routes).
            _cookies = dict(request.cookies) if request.cookies else None

            # For detail/edit pages, extract {id} from path params.
            # IMPORTANT: use per-request copies of detail/form contexts
            # because URL templates contain {id} placeholders that get
            # replaced with actual IDs.  Mutating the shared ctx would
            # corrupt templates for subsequent requests (#291).
            path_id = request.path_params.get("id")
            _ctx_overrides: dict[str, Any] = {}
            if path_id and ctx.detail:
                req_detail = ctx.detail.model_copy(deep=True)

                # Fetch item data using the *original* URL template
                req_detail.item = await _fetch_json(
                    effective_backend_url,
                    ctx.detail.delete_url or ctx.detail.back_url,
                    path_id,
                    _cookies,
                )
                if "error" in req_detail.item:
                    logger.warning(
                        "Detail page data fetch failed for %s/%s: %s",
                        ctx.detail.entity_name,
                        path_id,
                        req_detail.item.get("error"),
                    )

                # Substitute {id} in the per-request copy only
                if req_detail.edit_url:
                    req_detail.edit_url = req_detail.edit_url.replace("{id}", str(path_id))
                if req_detail.delete_url:
                    req_detail.delete_url = req_detail.delete_url.replace("{id}", str(path_id))
                for _t in req_detail.transitions:
                    if _t.api_url and "{id}" in _t.api_url:
                        _t.api_url = _t.api_url.replace("{id}", str(path_id))

                # Fetch related entity data for tabs (hub-and-spoke, #301)
                if req_detail.related_tabs and path_id:
                    import urllib.parse

                    async def _fetch_related_tab(
                        tab: Any, _id: str, _backend: str, _ck: Any
                    ) -> None:
                        params = urllib.parse.urlencode(
                            {f"filter[{tab.filter_field}]": _id, "page": "1", "page_size": "50"}
                        )
                        url = f"{_backend}{tab.api_endpoint}?{params}"
                        try:
                            data = await _fetch_url(url, _ck)
                            tab.rows = data.get("items", [])
                            tab.total = data.get("total", len(tab.rows))
                        except Exception:
                            logger.warning(
                                "Failed to fetch related %s for %s",
                                tab.entity_name,
                                _id,
                                exc_info=True,
                            )

                    await asyncio.gather(
                        *[
                            _fetch_related_tab(tab, str(path_id), effective_backend_url, _cookies)
                            for tab in req_detail.related_tabs
                        ]
                    )

                _ctx_overrides["detail"] = req_detail

            if path_id and ctx.form and ctx.form.mode == "edit":
                req_form = ctx.form.model_copy(deep=True)

                # Fetch existing data using the *original* URL template
                form_data = await _fetch_json(
                    effective_backend_url, ctx.form.action_url, path_id, _cookies
                )
                if "error" not in form_data:
                    req_form.initial_values = form_data
                else:
                    logger.warning("Failed to fetch initial form values for %s", path_id)

                req_form.action_url = req_form.action_url.replace("{id}", str(path_id))
                if req_form.cancel_url:
                    req_form.cancel_url = req_form.cancel_url.replace("{id}", str(path_id))

                _ctx_overrides["form"] = req_form

            if ctx.table:
                # Fetch list data from backend
                import urllib.parse

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
                fetch_url = f"{effective_backend_url}{ctx.table.api_endpoint}?{query_string}"

                try:
                    data = await _fetch_url(fetch_url, _cookies)
                    items = data.get("items", [])
                    if items and isinstance(items[0], dict):
                        ctx.table.rows = items
                    ctx.table.total = data.get("total", len(items))
                except Exception:
                    logger.warning("Failed to fetch list data from %s", fetch_url, exc_info=True)
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

            # Build per-request context with detail/form overrides (#291).
            # Table and nav mutations on the shared ctx are safe (fully
            # overwritten each request), but detail/form URL templates
            # degrade after substitution so they use copies.
            render_ctx = ctx.model_copy(update=_ctx_overrides) if _ctx_overrides else ctx

            # Fragment targeting: nav links target #main-content directly,
            # so return only the content template (no layout wrapper).
            if htmx.wants_fragment:
                import json

                html = render_page(render_ctx, content_only=True)
                headers = {"HX-Trigger": json.dumps({"dz:titleUpdate": render_ctx.page_title})}
                return HTMLResponse(content=html, headers=headers)

            # Any HTMX request can receive body-only HTML — the client
            # extracts <body> content anyway.  History-restore is the one
            # exception: the browser needs a full document for cache misses.
            html = render_page(render_ctx, partial=htmx.is_htmx and not htmx.is_history_restore)
            return HTMLResponse(content=html)

        return page_handler

    # Register routes — sort by specificity so FastAPI matches the most-specific
    # route first.  Rules: (1) more segments first, (2) static paths before
    # dynamic ones at the same depth (e.g. /item/create before /item/{id}).
    def _route_sort_key(kv: tuple[str, Any]) -> tuple[int, int]:
        path = kv[0]
        return (-path.count("/"), 0 if "{" not in path else 1)

    sorted_routes = sorted(page_contexts.items(), key=_route_sort_key)
    for route_path, ctx in sorted_routes:
        # Route paths include app_prefix for URL generation (nav highlighting,
        # cross-references).  Strip it for registration since the router is
        # mounted with the same prefix — otherwise routes get double-prefixed.
        reg_path = route_path
        if app_prefix and reg_path.startswith(app_prefix):
            reg_path = reg_path[len(app_prefix) :] or "/"

        handler = _make_page_handler(route_path, ctx, view_name=getattr(ctx, "view_name", None))
        router.get(reg_path, response_class=HTMLResponse)(handler)

    # Register workspace routes — workspaces use their own template, not the
    # surface page template, so they get separate handlers.
    workspaces = getattr(appspec, "workspaces", []) or []
    if workspaces:
        from dazzle_ui.runtime.workspace_renderer import build_workspace_context

        # Build nav items for workspace pages: workspace links + entity surface links.
        # Entity surfaces are derived from workspace regions' source entities.
        ws_nav_items: list[dict[str, Any]] = []
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

        # Add entity surface links from each workspace's regions
        surfaces = getattr(appspec, "surfaces", []) or []
        _list_surfaces_by_entity: dict[str, Any] = {}
        for surface in surfaces:
            if surface.mode.value == "list" and surface.entity_ref:
                _list_surfaces_by_entity.setdefault(surface.entity_ref, surface)

        # Per-workspace nav: workspace links + entity surfaces from regions
        ws_entity_nav: dict[str, list[dict[str, Any]]] = {}
        for ws in workspaces:
            entity_items: list[dict[str, Any]] = []
            seen_entities: set[str] = set()
            for region in ws.regions:
                if region.source and region.source not in seen_entities:
                    seen_entities.add(region.source)
                    list_surface = _list_surfaces_by_entity.get(region.source)
                    if list_surface:
                        entity_slug = region.source.lower().replace("_", "-")
                        entity_items.append(
                            {
                                "label": list_surface.title
                                or region.source.replace("_", " ").title(),
                                "route": f"{app_prefix}/{entity_slug}",
                                "allow_personas": [],
                            }
                        )
            ws_entity_nav[ws.name] = entity_items

        ws_app_name = appspec.title or appspec.name.replace("_", " ").title()

        for workspace in workspaces:
            ws_ctx = build_workspace_context(workspace, appspec)
            _ws_ctx = ws_ctx
            _ws_route = f"{app_prefix}/workspaces/{workspace.name}"
            _ws_allowed = (
                list(workspace.access.allow_personas) if getattr(workspace, "access", None) else []
            )
            _ws_entity_items = ws_entity_nav.get(workspace.name, [])

            def _make_workspace_handler(
                ws_context: Any = _ws_ctx,
                ws_route: str = _ws_route,
                ws_allowed_personas: list[str] = _ws_allowed,
                ws_entity_items: list[dict[str, Any]] = _ws_entity_items,
            ) -> Any:
                async def workspace_handler(request: Request) -> Response:
                    from dazzle_ui.runtime.template_renderer import render_fragment

                    # Inject auth context if available
                    visible_nav = list(ws_nav_items) + list(ws_entity_items)
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
                                    for item in ws_nav_items + ws_entity_items
                                    if not item["allow_personas"]
                                    or any(r in item["allow_personas"] for r in user_roles)
                                ]
                        except Exception:
                            logger.debug("Failed to resolve auth for workspace nav", exc_info=True)

                    # Enforce workspace persona access control (superusers bypass)
                    is_superuser = (
                        get_auth_context is not None
                        and auth_ctx is not None  # noqa: F821
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

                    ws_title = ws_context.title or ws_context.name.replace("_", " ").title()

                    # Fragment targeting: return only the workspace content
                    if htmx.wants_fragment:
                        import json

                        html = render_fragment(
                            "workspace/_content.html",
                            workspace=ws_context,
                        )
                        headers = {"HX-Trigger": json.dumps({"dz:titleUpdate": ws_title})}
                        return HTMLResponse(content=html, headers=headers)

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
