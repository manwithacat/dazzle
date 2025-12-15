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
        content = _load_content_file(project_root, source.get("path", ""))
        if content:
            response["content"] = content
            response["content_format"] = source.get("format", "md")

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
        content = _load_content_file(project_root, source.get("path", ""))
        if content:
            response["content"] = content
            response["content_format"] = source.get("format", "md")

    return response


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

    This is for server-side rendering of site pages.
    For SPA mode, use create_site_routes() API endpoints instead.

    Args:
        sitespec_data: SiteSpec as dict
        project_root: Project root for content file loading

    Returns:
        FastAPI router with HTML page routes
    """
    from fastapi import APIRouter
    from fastapi.responses import HTMLResponse

    router = APIRouter()

    brand = sitespec_data.get("brand", {})
    pages = sitespec_data.get("pages", [])

    # Create route for each page
    for page in pages:
        route = page.get("route", "/")
        title = page.get("title", brand.get("product_name", "Page"))

        # Capture page data in closure
        page_data = page

        @router.get(route, response_class=HTMLResponse, include_in_schema=False)
        async def serve_page(p: dict[str, Any] = page_data, t: str = title) -> str:
            """Serve a site page as HTML."""
            return _render_page_html(p, brand, t)

    return router


def _render_page_html(
    page: dict[str, Any],
    brand: dict[str, Any],
    title: str,
) -> str:
    """Render a page as simple HTML (placeholder implementation)."""
    product_name = brand.get("product_name", "My App")

    sections_html = ""
    for section in page.get("sections", []):
        section_type = section.get("type", "")
        headline = section.get("headline", "")
        subhead = section.get("subhead", "")
        body = section.get("body", "")

        sections_html += f"""
        <section class="section section-{section_type}">
            {f"<h2>{headline}</h2>" if headline else ""}
            {f'<p class="subhead">{subhead}</p>' if subhead else ""}
            {f"<p>{body}</p>" if body else ""}
        </section>
        """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - {product_name}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: #1a1a1a;
            background: #fff;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 0 20px; }}
        header {{
            padding: 20px 0;
            border-bottom: 1px solid #eee;
        }}
        .logo {{ font-size: 1.5rem; font-weight: 700; color: #333; text-decoration: none; }}
        .section {{ padding: 80px 20px; text-align: center; }}
        .section-hero {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; }}
        .section h2 {{ font-size: 2.5rem; margin-bottom: 20px; }}
        .section .subhead {{ font-size: 1.25rem; opacity: 0.9; margin-bottom: 20px; }}
        footer {{
            padding: 40px 20px;
            background: #f8f9fa;
            text-align: center;
            font-size: 0.875rem;
            color: #666;
        }}
    </style>
</head>
<body>
    <header>
        <div class="container">
            <a href="/" class="logo">{product_name}</a>
        </div>
    </header>
    <main>
        {sections_html}
    </main>
    <footer>
        <div class="container">
            <p>&copy; 2025 {product_name}. All rights reserved.</p>
        </div>
    </footer>
</body>
</html>"""
