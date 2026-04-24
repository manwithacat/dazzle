"""
Site routes for public site shell pages.

Generates FastAPI routes from SiteSpec to serve:
- Landing pages (/, /about, /pricing)
- Legal pages (/terms, /privacy)
- Auth pages (/login, /signup)
- Site configuration API (/_site/config, /_site/nav)
"""

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

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
    from fastapi import HTTPException

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
    sections = list(page.get("sections", []))

    # Resolve section-level markdown sources
    if project_root:
        for section in sections:
            source = section.get("source")
            sec_type = section.get("type")
            if source and sec_type in ("markdown", "split_content"):
                raw = _load_content_file(
                    project_root,
                    source.get("path", ""),
                )
                if raw:
                    fmt = source.get("format", "md")
                    rendered = _render_content(raw, fmt)
                    if sec_type == "split_content":
                        section["body"] = rendered
                    else:
                        section["content"] = rendered

    response: dict[str, Any] = {
        "route": page.get("route"),
        "type": page.get("type"),
        "title": page.get("title"),
        "sections": sections,
    }

    # For markdown/legal pages with page-level source
    # but no sections, process through directive parser
    page_type = page.get("type")
    source = page.get("source")
    if source and project_root and not sections:
        raw = _load_content_file(
            project_root,
            source.get("path", ""),
        )
        if raw:
            fmt = source.get("format", "md")
            directive_sections = _process_directives(raw, fmt)
            response["sections"] = directive_sections
            # Keep content key for backward compat
            response["content"] = _render_content(raw, fmt)
            response["content_format"] = "html"
    elif source and project_root and page_type in ("markdown", "legal"):
        # Page has both source and sections — still provide
        # top-level content for backward compat
        raw = _load_content_file(
            project_root,
            source.get("path", ""),
        )
        if raw:
            fmt = source.get("format", "md")
            response["content"] = _render_content(raw, fmt)
            response["content_format"] = "html"

    return response


def _format_legal_page_response(
    page_type: str,
    page_data: dict[str, Any],
    project_root: Path | None,
) -> dict[str, Any]:
    """Format legal page data for API response."""
    title = "Terms of Service" if page_type == "terms" else "Privacy Policy"
    response: dict[str, Any] = {
        "route": page_data.get("route"),
        "type": "legal",
        "title": title,
    }

    # Load content and process through directive parser
    source = page_data.get("source", {})
    if source and project_root:
        raw = _load_content_file(project_root, source.get("path", ""))
        if raw:
            fmt = source.get("format", "md")
            directive_sections = _process_directives(raw, fmt)
            response["sections"] = directive_sections
            # Keep content key for backward compat
            response["content"] = _render_content(raw, fmt)
            response["content_format"] = "html"

    return response


def _process_directives(raw: str, fmt: str) -> list[dict[str, Any]]:
    """Process markdown through the directive parser.

    Falls back to a single markdown section if the parser
    is unavailable.
    """
    try:
        from dazzle.core.directive_parser import (
            process_markdown_with_directives,
        )

        return process_markdown_with_directives(raw, fmt)
    except Exception:
        logger.debug("Directive parser unavailable, using plain markdown")
        return [
            {"type": "markdown", "content": _render_content(raw, fmt)},
        ]


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
        logger.warning("Content file not found: %s", full_path)
        return None

    try:
        return full_path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error("Error reading content file %s: %s", full_path, e)
        return None


def create_site_page_routes(
    sitespec_data: dict[str, Any],
    project_root: Path | None = None,
    get_auth_context: Callable[..., Any] | None = None,
    persona_routes: dict[str, str] | None = None,
    *,
    consent_default_jurisdiction: str = "EU",
    consent_override: str | None = None,
    privacy_page_url: str = "/privacy",
    cookie_policy_url: str | None = None,
    analytics_spec: Any | None = None,
) -> APIRouter:
    """
    Create FastAPI routes that serve HTML pages directly.

    This is for server-side rendering of site pages using Jinja2 templates.
    For SPA mode, use create_site_routes() API endpoints instead.

    When ``get_auth_context`` and ``persona_routes`` are provided, the root
    route (``/``) will redirect authenticated users to their persona's
    default workspace instead of showing the marketing landing page.

    Args:
        sitespec_data: SiteSpec as dict
        project_root: Project root for content file loading
        get_auth_context: Optional callable that takes a Request and returns
            an auth context object with ``is_authenticated`` and ``roles``.
        persona_routes: Optional dict mapping persona id to default route
            (e.g. ``{"customer": "/app/workspaces/customer_dashboard"}``).

    Returns:
        FastAPI router with HTML page routes
    """
    from dazzle_ui.runtime.css_loader import get_bundled_css
    from dazzle_ui.runtime.site_context import build_site_page_context
    from dazzle_ui.runtime.site_renderer import get_site_js
    from dazzle_ui.runtime.template_renderer import render_site_page

    router = APIRouter()

    # Check once whether the project provides a custom CSS override
    has_custom_css = bool(
        project_root and (project_root / "static" / "css" / "custom.css").is_file()
    )

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

    # Pre-resolve page data for SSR so each route can render server-side
    page_data_cache: dict[str, dict[str, Any]] = {}
    for page in pages:
        route = page.get("route", "/")
        page_data_cache[route] = _format_page_response(page, project_root)

    for ltype in ("terms", "privacy"):
        lpage = legal.get(ltype)
        if lpage:
            lroute = lpage.get("route", f"/{ltype}")
            page_data_cache[lroute] = _format_legal_page_response(ltype, lpage, project_root)

    # Create route for each page
    _auth_redirect_enabled = bool(get_auth_context and persona_routes)

    # Capture auth helpers once for closures (ruff B023).
    _auth_fn = get_auth_context
    _persona_routes: dict[str, str] = dict(persona_routes) if persona_routes else {}

    # Consent banner + per-tenant resolution (v0.61.0 Phase 2 + Phase 6)
    _app_wide_privacy_url = privacy_page_url
    _app_wide_cookie_url = cookie_policy_url
    _app_wide_jurisdiction = consent_default_jurisdiction
    _app_wide_override = consent_override
    _analytics_spec = analytics_spec

    def _resolve_consent(
        request: Request,
    ) -> tuple[dict[str, Any], str, list[dict[str, Any]], str | None, str, str | None]:
        """Return (consent, consent_json, providers, tenant_slug, privacy_url, cookie_url).

        Runs through the tenant resolver (v0.61.0 Phase 6) — per-tenant
        analytics IDs, residency, and banner link overrides are honoured.
        Falls back to app-wide config when no resolver is registered.
        """
        import json as _json

        from dazzle.compliance.analytics import (
            TenantAnalyticsConfig,
            resolve_active_providers,
            resolve_for_request,
        )
        from dazzle.compliance.analytics.consent import (
            CONSENT_COOKIE_NAME,
            ConsentDefaults,
            parse_consent_cookie,
        )
        from dazzle.core.ir import AnalyticsSpec

        # Resolve the tenant (or app-wide) config for this request.
        fallback = TenantAnalyticsConfig(
            providers=list(_analytics_spec.providers) if _analytics_spec else [],
            data_residency=_app_wide_jurisdiction,
            consent_override=_app_wide_override,
            privacy_page_url=_app_wide_privacy_url,
            cookie_policy_url=_app_wide_cookie_url,
        )
        tenant_cfg = resolve_for_request(request, fallback=fallback)

        # Build consent defaults from the resolved tenant residency.
        defaults = ConsentDefaults.for_jurisdiction(
            tenant_cfg.data_residency,
            override=tenant_cfg.consent_override
            if tenant_cfg.consent_override in ("granted", "denied")
            else None,  # type: ignore[arg-type]
        )
        raw = request.cookies.get(CONSENT_COOKIE_NAME)
        state = parse_consent_cookie(raw, defaults)
        consent = {
            "analytics": state.analytics == "granted",
            "advertising": state.advertising == "granted",
            "personalization": state.personalization == "granted",
            "functional": state.functional == "granted",
            "undecided": state.undecided,
            "decided_at": state.decided_at,
        }

        # Providers come from the tenant config (may be empty if the tenant
        # opted out entirely).
        if tenant_cfg.providers:
            tenant_spec = AnalyticsSpec(providers=tenant_cfg.providers)
            providers = resolve_active_providers(tenant_spec, state)
        else:
            providers = []

        return (
            consent,
            _json.dumps(consent),
            providers,
            tenant_cfg.tenant_slug,
            tenant_cfg.privacy_page_url,
            tenant_cfg.cookie_policy_url,
        )

    def _resolve_auth(request: Request) -> tuple[bool, str]:
        """Check auth state and resolve the dashboard URL.

        Returns (is_authenticated, dashboard_url).
        """
        if _auth_fn is None:
            return False, "/app"
        try:
            auth_ctx = _auth_fn(request)
            if auth_ctx and auth_ctx.is_authenticated:
                dashboard_url = "/app"
                if _persona_routes and auth_ctx.roles:
                    for role in auth_ctx.roles:
                        role_key = role.lower().replace("role_", "")
                        if role_key in _persona_routes:
                            dashboard_url = _persona_routes[role_key]
                            break
                return True, dashboard_url
        except Exception:
            logger.debug("Auth check failed, treating as anonymous", exc_info=True)
        return False, "/app"

    for page in pages:
        route = page.get("route", "/")

        # Capture route in closure
        page_route = route

        if route == "/" and _auth_redirect_enabled:
            # Root route: redirect authenticated users to their persona's
            # default workspace (#569), serve the landing page otherwise.

            @router.get("/", include_in_schema=False)
            async def serve_root_page(
                request: Request,
                r: str = page_route,
                sitespec: dict[str, Any] = sitespec_data,
            ) -> Response:
                """Serve landing page or redirect authenticated users."""
                is_authed, dash_url = _resolve_auth(request)
                if is_authed and dash_url != "/app":
                    # Redirect to persona workspace if a specific route was resolved.
                    # The generic /app fallback means no persona route matched,
                    # so show the landing page with auth-aware nav instead.
                    return RedirectResponse(url=dash_url, status_code=302)
                # #768 — QA mode personas for landing page panel
                qa_personas: list[dict[str, Any]] = []
                qa_persona_list = getattr(request.app.state, "qa_personas", None)
                if qa_persona_list:
                    qa_personas = [
                        {
                            "id": p.persona_id,
                            "display_name": p.display_name,
                            "email": p.email,
                            "description": p.description,
                            "stories": p.stories,
                        }
                        for p in qa_persona_list
                    ]
                (
                    consent_dict,
                    consent_json,
                    active_providers,
                    tenant_slug,
                    privacy_url,
                    cookie_url,
                ) = _resolve_consent(request)
                ctx = build_site_page_context(
                    sitespec,
                    r,
                    page_data=page_data_cache.get(r),
                    custom_css=has_custom_css,
                    is_authenticated=is_authed,
                    dashboard_url=dash_url,
                    qa_personas=qa_personas,
                    consent=consent_dict,
                    consent_state_json=consent_json,
                    active_analytics_providers=active_providers,
                    tenant_slug=tenant_slug,
                    privacy_page_url=privacy_url,
                    cookie_policy_url=cookie_url,
                )
                return HTMLResponse(content=render_site_page("site/page.html", ctx))
        else:

            @router.get(route, response_class=HTMLResponse, include_in_schema=False)
            async def serve_page(
                request: Request,
                r: str = page_route,
                sitespec: dict[str, Any] = sitespec_data,
            ) -> str:
                """Serve a site page as HTML with SSR content."""
                is_authed, dash_url = _resolve_auth(request)
                (
                    consent_dict,
                    consent_json,
                    active_providers,
                    tenant_slug,
                    privacy_url,
                    cookie_url,
                ) = _resolve_consent(request)
                ctx = build_site_page_context(
                    sitespec,
                    r,
                    page_data=page_data_cache.get(r),
                    custom_css=has_custom_css,
                    is_authenticated=is_authed,
                    dashboard_url=dash_url,
                    consent=consent_dict,
                    consent_state_json=consent_json,
                    active_analytics_providers=active_providers,
                    tenant_slug=tenant_slug,
                    privacy_page_url=privacy_url,
                    cookie_policy_url=cookie_url,
                )
                return render_site_page("site/page.html", ctx)

    # Create routes for legal pages
    if legal.get("terms"):
        terms_route = legal["terms"].get("route", "/terms")

        @router.get(terms_route, response_class=HTMLResponse, include_in_schema=False)
        async def serve_terms_page(
            request: Request,
            r: str = terms_route,
            sitespec: dict[str, Any] = sitespec_data,
        ) -> str:
            """Serve the terms of service page."""
            is_authed, dash_url = _resolve_auth(request)
            consent_dict, consent_json, active_providers, tenant_slug, privacy_url, cookie_url = (
                _resolve_consent(request)
            )
            ctx = build_site_page_context(
                sitespec,
                r,
                page_data=page_data_cache.get(r),
                custom_css=has_custom_css,
                is_authenticated=is_authed,
                dashboard_url=dash_url,
                consent=consent_dict,
                consent_state_json=consent_json,
                active_analytics_providers=active_providers,
                tenant_slug=tenant_slug,
                privacy_page_url=privacy_url,
                cookie_policy_url=cookie_url,
            )
            return render_site_page("site/page.html", ctx)

    if legal.get("privacy"):
        privacy_route = legal["privacy"].get("route", "/privacy")

        @router.get(privacy_route, response_class=HTMLResponse, include_in_schema=False)
        async def serve_privacy_page(
            request: Request,
            r: str = privacy_route,
            sitespec: dict[str, Any] = sitespec_data,
        ) -> str:
            """Serve the privacy policy page."""
            is_authed, dash_url = _resolve_auth(request)
            consent_dict, consent_json, active_providers, tenant_slug, privacy_url, cookie_url = (
                _resolve_consent(request)
            )
            ctx = build_site_page_context(
                sitespec,
                r,
                page_data=page_data_cache.get(r),
                custom_css=has_custom_css,
                is_authenticated=is_authed,
                dashboard_url=dash_url,
                consent=consent_dict,
                consent_state_json=consent_json,
                active_analytics_providers=active_providers,
                tenant_slug=tenant_slug,
                privacy_page_url=privacy_url,
                cookie_policy_url=cookie_url,
            )
            return render_site_page("site/page.html", ctx)

    return router


def create_auth_page_routes(
    sitespec_data: dict[str, Any],
    project_root: Path | None = None,
    get_auth_context: Callable[..., Any] | None = None,
) -> APIRouter:
    """
    Create FastAPI routes for authentication pages.

    Routes: /login, /signup, /forgot-password, /reset-password,
    /2fa/setup, /2fa/settings, /2fa/challenge.

    Args:
        sitespec_data: SiteSpec as dict
        project_root: Project root for detecting custom CSS
        get_auth_context: Optional callable that takes a Request and returns an
            auth context with ``is_authenticated``. When provided, /2fa/setup
            and /2fa/settings redirect unauthenticated users to /login.

    Returns:
        FastAPI router with auth page routes
    """
    from dazzle_ui.runtime.site_context import build_site_auth_context
    from dazzle_ui.runtime.template_renderer import render_site_page

    router = APIRouter()

    has_custom_css = bool(
        project_root and (project_root / "static" / "css" / "custom.css").is_file()
    )

    _auth_fn = get_auth_context

    def _require_auth(request: Request, next_path: str) -> RedirectResponse | None:
        """Return a redirect to /login when the request is unauthenticated.

        When no auth callable is wired, fall through (treat all requests as
        permitted) so the page is still reachable in dev/testing setups.
        """
        if _auth_fn is None:
            return None
        try:
            auth_ctx = _auth_fn(request)
            if auth_ctx and getattr(auth_ctx, "is_authenticated", False):
                return None
        except Exception:
            logger.debug("Auth check failed, redirecting to login", exc_info=True)
        return RedirectResponse(url=f"/login?next={next_path}", status_code=302)

    @router.get("/login", response_class=HTMLResponse, include_in_schema=False)
    async def login_page(sitespec: dict[str, Any] = sitespec_data) -> str:
        """Serve the login page."""
        ctx = build_site_auth_context(sitespec, "login", custom_css=has_custom_css)
        return render_site_page("site/auth/login.html", ctx)

    @router.get("/signup", response_class=HTMLResponse, include_in_schema=False)
    async def signup_page(sitespec: dict[str, Any] = sitespec_data) -> str:
        """Serve the signup page."""
        ctx = build_site_auth_context(sitespec, "signup", custom_css=has_custom_css)
        return render_site_page("site/auth/signup.html", ctx)

    @router.get("/forgot-password", response_class=HTMLResponse, include_in_schema=False)
    async def forgot_password_page(sitespec: dict[str, Any] = sitespec_data) -> str:
        """Serve the forgot-password page."""
        ctx = build_site_auth_context(sitespec, "forgot_password", custom_css=has_custom_css)
        return render_site_page("site/auth/forgot_password.html", ctx)

    @router.get("/reset-password", response_class=HTMLResponse, include_in_schema=False)
    async def reset_password_page(sitespec: dict[str, Any] = sitespec_data) -> str:
        """Serve the reset-password page."""
        ctx = build_site_auth_context(sitespec, "reset_password", custom_css=has_custom_css)
        return render_site_page("site/auth/reset_password.html", ctx)

    @router.get("/2fa/setup", include_in_schema=False)
    async def two_factor_setup_page(
        request: Request,
        sitespec: dict[str, Any] = sitespec_data,
    ) -> Response:
        """Serve the 2FA enrolment page (authenticated users only)."""
        redirect = _require_auth(request, "/2fa/setup")
        if redirect is not None:
            return redirect
        ctx = build_site_auth_context(sitespec, "2fa_setup", custom_css=has_custom_css)
        return HTMLResponse(content=render_site_page("site/auth/2fa_setup.html", ctx))

    @router.get("/2fa/settings", include_in_schema=False)
    async def two_factor_settings_page(
        request: Request,
        sitespec: dict[str, Any] = sitespec_data,
    ) -> Response:
        """Serve the 2FA management page (authenticated users only)."""
        redirect = _require_auth(request, "/2fa/settings")
        if redirect is not None:
            return redirect
        ctx = build_site_auth_context(sitespec, "2fa_settings", custom_css=has_custom_css)
        return HTMLResponse(content=render_site_page("site/auth/2fa_settings.html", ctx))

    @router.get("/2fa/challenge", response_class=HTMLResponse, include_in_schema=False)
    async def two_factor_challenge_page(
        session: str = "",
        method: str = "totp",
        sitespec: dict[str, Any] = sitespec_data,
    ) -> str:
        """Serve the mid-login 2FA challenge page.

        Public route — the pre-login session_token is the sole credential the
        subsequent POST /auth/2fa/verify call relies on. The token is passed in
        as ``?session=<token>`` from the login flow when the backend returns
        ``status: "2fa_required"``.
        """
        ctx = build_site_auth_context(
            sitespec,
            "2fa_challenge",
            custom_css=has_custom_css,
            session_token=session,
            default_method=method,
            methods=["totp", "email_otp"],
        )
        return render_site_page("site/auth/2fa_challenge.html", ctx)

    return router
