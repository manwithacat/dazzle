"""
Site routes for public site shell pages.

Generates FastAPI routes from SiteSpec to serve:
- Landing pages (/, /about, /pricing)
- Legal pages (/terms, /privacy)
- Auth pages (/login, /signup)
- Site configuration API (/_site/config, /_site/nav)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import APIRouter

logger = logging.getLogger("dazzle.site_routes")


def create_site_routes(
    sitespec_data: dict[str, Any],
    project_root: Path | None = None,
) -> APIRouter:
    """
    Create FastAPI routes for site shell pages.

    Args:
        sitespec_data: SiteSpec as dict (from model_dump or loaded JSON)
        project_root: Project root for content file loading

    Returns:
        FastAPI router with site routes
    """
    from fastapi import APIRouter, HTTPException

    router = APIRouter(tags=["Site"])

    # Extract key data from sitespec
    brand = sitespec_data.get("brand", {})
    layout = sitespec_data.get("layout", {})
    pages = sitespec_data.get("pages", [])
    legal = sitespec_data.get("legal", {})
    integrations = sitespec_data.get("integrations", {})

    # Build navigation data
    nav_data = layout.get("nav", {})
    footer_data = layout.get("footer", {})

    # Site configuration endpoint
    @router.get("/_site/config")
    async def get_site_config() -> dict[str, Any]:
        """Get site configuration (brand, layout, integrations)."""
        return {
            "brand": brand,
            "layout": {
                "theme": layout.get("theme", "saas-default"),
                "auth": layout.get("auth", {}),
            },
            "integrations": integrations,
        }

    @router.get("/_site/nav")
    async def get_site_nav() -> dict[str, Any]:
        """Get navigation data (nav items, footer)."""
        return {
            "nav": nav_data,
            "footer": footer_data,
        }

    @router.get("/_site/pages")
    async def list_site_pages() -> dict[str, Any]:
        """List all site pages with metadata."""
        page_list = []
        for page in pages:
            page_list.append(
                {
                    "route": page.get("route"),
                    "type": page.get("type"),
                    "title": page.get("title"),
                }
            )
        # Add legal pages
        if legal.get("terms"):
            page_list.append(
                {
                    "route": legal["terms"].get("route", "/terms"),
                    "type": "legal",
                    "title": "Terms of Service",
                }
            )
        if legal.get("privacy"):
            page_list.append(
                {
                    "route": legal["privacy"].get("route", "/privacy"),
                    "type": "legal",
                    "title": "Privacy Policy",
                }
            )
        return {"pages": page_list}

    @router.get("/_site/page/{route:path}")
    async def get_page_data(route: str) -> dict[str, Any]:
        """Get page data by route."""
        route_with_slash = f"/{route}" if not route.startswith("/") else route

        # Check pages
        for page in pages:
            if page.get("route") == route_with_slash:
                return _format_page_response(page, project_root)

        # Check legal pages
        if legal.get("terms") and legal["terms"].get("route") == route_with_slash:
            return _format_legal_page_response("terms", legal["terms"], project_root)
        if legal.get("privacy") and legal["privacy"].get("route") == route_with_slash:
            return _format_legal_page_response("privacy", legal["privacy"], project_root)

        raise HTTPException(status_code=404, detail=f"Page not found: {route_with_slash}")

    return router


def _format_page_response(page: dict[str, Any], project_root: Path | None) -> dict[str, Any]:
    """Format page data for API response."""
    response: dict[str, Any] = {
        "route": page.get("route"),
        "type": page.get("type"),
        "title": page.get("title"),
        "sections": page.get("sections", []),
    }

    # Load content if this is a markdown page
    source = page.get("source")
    if source and project_root:
        raw = _load_content_file(project_root, source.get("path", ""))
        if raw:
            fmt = source.get("format", "md")
            response["content"] = _render_content(raw, fmt)
            response["content_format"] = "html"

    return response


def _format_legal_page_response(
    page_type: str, page_data: dict[str, Any], project_root: Path | None
) -> dict[str, Any]:
    """Format legal page data for API response."""
    response: dict[str, Any] = {
        "route": page_data.get("route"),
        "type": "legal",
        "title": "Terms of Service" if page_type == "terms" else "Privacy Policy",
    }

    # Load content
    source = page_data.get("source", {})
    if source and project_root:
        raw = _load_content_file(project_root, source.get("path", ""))
        if raw:
            fmt = source.get("format", "md")
            response["content"] = _render_content(raw, fmt)
            response["content_format"] = "html"

    return response


def _render_content(raw: str, fmt: str) -> str:
    """Convert raw content to HTML.

    Markdown (``md``) is converted using the ``markdown`` library.
    HTML content is returned as-is.
    """
    if fmt in ("md", "markdown"):
        try:
            import markdown  # type: ignore[import-untyped]

            return str(markdown.markdown(raw, extensions=["extra", "sane_lists"]))
        except ImportError:
            logger.warning("markdown package not available; serving raw content")
            return raw
    return raw


def _load_content_file(project_root: Path, content_path: str) -> str | None:
    """Load content from a file in site/content/."""
    if not content_path:
        return None

    full_path = project_root / "site" / "content" / content_path
    if not full_path.exists():
        logger.warning(f"Content file not found: {full_path}")
        return None

    try:
        return full_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Error reading content file {full_path}: {e}")
        return None


def create_site_page_routes(
    sitespec_data: dict[str, Any],
    project_root: Path | None = None,
) -> APIRouter:
    """
    Create FastAPI routes that serve HTML pages directly.

    This is for server-side rendering of site pages using the DaisyUI renderer.
    For SPA mode, use create_site_routes() API endpoints instead.

    Args:
        sitespec_data: SiteSpec as dict
        project_root: Project root for content file loading

    Returns:
        FastAPI router with HTML page routes
    """
    from fastapi import APIRouter
    from fastapi.responses import HTMLResponse, Response

    from dazzle_ui.runtime.css_loader import get_bundled_css
    from dazzle_ui.runtime.site_renderer import get_site_js, render_site_page_html

    router = APIRouter()

    # Serve the site JavaScript (required for page rendering)
    @router.get("/site.js", include_in_schema=False)
    async def serve_site_js() -> Response:
        """Serve the site JavaScript for marketing pages."""
        return Response(content=get_site_js(), media_type="application/javascript")

    # Serve the bundled CSS (required for styling)
    @router.get("/styles/dazzle.css", include_in_schema=False)
    async def serve_dazzle_css() -> Response:
        """Serve the bundled Dazzle CSS stylesheet."""
        return Response(content=get_bundled_css(), media_type="text/css")

    pages = sitespec_data.get("pages", [])
    legal = sitespec_data.get("legal", {})

    # Create route for each page
    for page in pages:
        route = page.get("route", "/")

        # Capture route in closure
        page_route = route

        @router.get(route, response_class=HTMLResponse, include_in_schema=False)
        async def serve_page(
            r: str = page_route,
            sitespec: dict[str, Any] = sitespec_data,
        ) -> str:
            """Serve a site page as HTML using DaisyUI renderer."""
            return render_site_page_html(sitespec, r)

    # Create routes for legal pages
    if legal.get("terms"):
        terms_route = legal["terms"].get("route", "/terms")

        @router.get(terms_route, response_class=HTMLResponse, include_in_schema=False)
        async def serve_terms_page(
            r: str = terms_route,
            sitespec: dict[str, Any] = sitespec_data,
        ) -> str:
            """Serve the terms of service page."""
            return render_site_page_html(sitespec, r)

    if legal.get("privacy"):
        privacy_route = legal["privacy"].get("route", "/privacy")

        @router.get(privacy_route, response_class=HTMLResponse, include_in_schema=False)
        async def serve_privacy_page(
            r: str = privacy_route,
            sitespec: dict[str, Any] = sitespec_data,
        ) -> str:
            """Serve the privacy policy page."""
            return render_site_page_html(sitespec, r)

    return router


def create_site_404_handler(
    sitespec_data: dict[str, Any],
) -> Any:
    """
    Create a 404 exception handler that returns a styled HTML page for site routes.

    Non-API paths (i.e. those not starting with ``/api/``, ``/_site/``, etc.)
    receive the branded 404 page from :func:`render_404_page_html`.
    API paths fall through to a standard JSON 404 response.

    Args:
        sitespec_data: SiteSpec as dict

    Returns:
        An async exception handler suitable for ``app.add_exception_handler(404, ...)``.
    """
    from fastapi.responses import HTMLResponse, JSONResponse

    from dazzle_ui.runtime.site_renderer import render_404_page_html

    async def handle_404(request: Any, exc: Any) -> HTMLResponse | JSONResponse:
        path: str = request.url.path
        # Let API, internal, and static routes return JSON 404
        if path.startswith(("/api/", "/_site/", "/static/", "/assets/", "/docs", "/openapi")):
            return JSONResponse(
                status_code=404,
                content={"detail": str(exc.detail) if hasattr(exc, "detail") else "Not Found"},
            )
        return HTMLResponse(
            content=render_404_page_html(sitespec_data, path),
            status_code=404,
        )

    return handle_404


def create_auth_page_routes(
    sitespec_data: dict[str, Any],
) -> APIRouter:
    """
    Create FastAPI routes for authentication pages (/login, /signup).

    Args:
        sitespec_data: SiteSpec as dict

    Returns:
        FastAPI router with auth page routes
    """
    from fastapi import APIRouter
    from fastapi.responses import HTMLResponse

    from dazzle_ui.runtime.site_renderer import render_auth_page_html

    router = APIRouter()

    @router.get("/login", response_class=HTMLResponse, include_in_schema=False)
    async def login_page(sitespec: dict[str, Any] = sitespec_data) -> str:
        """Serve the login page."""
        return render_auth_page_html(sitespec, "login")

    @router.get("/signup", response_class=HTMLResponse, include_in_schema=False)
    async def signup_page(sitespec: dict[str, Any] = sitespec_data) -> str:
        """Serve the signup page."""
        return render_auth_page_html(sitespec, "signup")

    return router
