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

from dazzle.core.ir import AnalyticsSpec
from dazzle.http.runtime.auth.auth_views import (
    build_forgot_password_sent_view,
    build_forgot_password_view,
    build_login_sent_view,
    build_reset_password_done_view,
    build_reset_password_view,
)
from dazzle.http.runtime.auth.two_factor_views import (
    build_2fa_challenge_view,
    build_2fa_settings_view,
    build_2fa_setup_view,
)
from dazzle.page.runtime.css_loader import get_bundled_css
from dazzle.page.runtime.site_context import build_site_page_context
from dazzle.page.runtime.site_renderer import get_site_js
from dazzle.render.context import PageContext
from dazzle.render.dispatch import build_page
from dazzle.render.fragment.renderer import FragmentRenderer

logger = logging.getLogger(__name__)


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
            import markdown  # type: ignore[import-untyped,unused-ignore]

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


def _render_site_footer_column(col: Any) -> str:
    """Render one footer column from the legacy `footer_columns` list."""
    import html as _html_mod

    title = _html_mod.escape(str(getattr(col, "title", "") or ""), quote=False)
    links = getattr(col, "links", None) or []
    links_html = "".join(
        f'<li><a href="{_html_mod.escape(str(getattr(lk, "href", "") or ""), quote=True)}">'  # nosemgrep
        f"{_html_mod.escape(str(getattr(lk, 'label', '') or ''), quote=False)}"
        f"</a></li>"
        for lk in links
    )
    return f'<div class="dz-footer-col"><h4>{title}</h4><ul>{links_html}</ul></div>'


def _render_qa_personas_html(qa_personas: list[Any]) -> str:
    """Dev-only persona impersonation panel (#1553, HM-native).

    Composes existing HM primitives — card / badge / button /
    auto-grid / stack / cluster — with zero bespoke CSS (the 19
    ``dz-qa-*`` classes are retired). The magic-link wiring lives in
    the delegated ``static/js/dz-qa.js`` controller (no inline script,
    CSP-friendly); the ``data-qa-login-persona`` attribute and the
    ``POST /qa/magic-link`` contract are unchanged.
    """
    import html as _html_mod

    cards: list[str] = []
    for persona in qa_personas:
        pid = _html_mod.escape(str(getattr(persona, "id", "") or ""), quote=True)
        pid_text = _html_mod.escape(str(getattr(persona, "id", "") or ""), quote=False)
        display_name = _html_mod.escape(
            str(getattr(persona, "display_name", "") or ""), quote=False
        )
        email = _html_mod.escape(str(getattr(persona, "email", "") or ""), quote=False)
        description = _html_mod.escape(str(getattr(persona, "description", "") or ""), quote=False)
        stories = getattr(persona, "stories", None) or []
        stories_html = ""
        if stories:
            story_items = "".join(
                f"<li>{_html_mod.escape(str(s), quote=False)}</li>" for s in stories
            )
            stories_html = f'<ul class="dz-card-label">{story_items}</ul>'

        cards.append(
            '<article class="dz-card dz-card-body">'
            '<div class="dz-stack" data-dz-gap="sm">'
            '<div class="dz-cluster" data-dz-align="baseline">'
            f"<h3>{display_name}</h3>"
            f'<span class="dz-badge">{pid_text}</span>'
            "</div>"
            f'<div class="dz-card-label">{email}</div>'
            f"<p>{description}</p>"
            f"{stories_html}"
            f'<button type="button" data-qa-login-persona="{pid}" '  # nosemgrep
            f'class="dz-button" data-dz-variant="primary">'
            f"Log in as {display_name}"
            f"</button>"
            "</div>"
            "</article>"
        )

    header_html = (
        '<div class="dz-stack" data-dz-gap="sm">'
        '<span class="dz-badge" data-dz-tone="warning">'
        "Local Dev Mode — not visible in production</span>"
        "<h2>Try the app as different personas</h2>"
        "<p>This is local QA mode. Pick a persona to explore the app "
        "with their permissions and data.</p>"
        "</div>"
    )
    return (
        '<section class="dz-stack" data-dz-gap="lg" data-qa-personas>'
        f"{header_html}"
        f'<div class="dz-auto-grid">{"".join(cards)}</div>'
        "</section>"
    )


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
    dark_mode_toggle: bool = True,
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
    from dazzle.http.runtime.renderers.site_section_override_loader import (
        discover_section_overrides,
    )

    # Discover project-local section overrides once at build time
    # (#1110 Part A). Empty registry when the project doesn't have a
    # `site_sections/` directory — falls through to framework defaults.
    _section_overrides = (
        discover_section_overrides(project_root) if project_root is not None else None
    )

    def _render_site_inner_html(request: Request, ctx: Any) -> str:
        """Inline-render the marketing-page body (Phase 4, v0.67.69).

        Replaces the legacy `site/inner_only.html` Jinja path. Composes:
          - `site/includes/nav.html`  (header with logo + nav items + theme toggle)
          - per-section dispatch (typed sections only — see below)
          - `site/includes/footer.html` (column links + copyright)
          - optional `site/sections/qa_personas.html` (dev-only persona cards)

        Sections are dispatched to the typed `render_typed_section` builder
        when their `type` is in `TYPED_SECTION_TYPES`; the upstream caller
        pre-renders them and replaces the section dict with a `_typed`
        marker carrying the rendered HTML. Unknown section types are
        skipped per the v0.67.69 breaking-change directive — projects
        with custom section types should register a typed builder.

        Theme toggle and dark-mode-toggle controls are visibility-gated
        by `dark_mode_toggle_enabled()`.
        """
        import html as _html_mod

        from dazzle.http.runtime.renderers.site_section_builder import (
            TYPED_SECTION_TYPES,
            render_typed_section,
        )

        product_name = _html_mod.escape(
            str(getattr(ctx, "product_name", "") or ""),
            quote=False,
        )
        nav_items = getattr(ctx, "nav_items", None) or []
        is_authenticated = bool(getattr(ctx, "is_authenticated", False))
        dashboard_url_raw = str(getattr(ctx, "dashboard_url", "") or "")
        nav_cta = getattr(ctx, "nav_cta", None)
        footer_columns = getattr(ctx, "footer_columns", None) or []
        copyright_text = _html_mod.escape(
            str(getattr(ctx, "copyright_text", "") or ""),
            quote=False,
        )
        page_type = str(getattr(ctx, "page_type", "") or "")
        current_route = _html_mod.escape(
            str(getattr(ctx, "current_route", "") or ""),
            quote=True,
        )
        sections = getattr(ctx, "sections", None) or []
        qa_personas = getattr(ctx, "qa_personas", None) or []

        # --- Nav (site/includes/nav.html) ----------------------------
        nav_links_html = "".join(
            f'<a href="{_html_mod.escape(str(getattr(item, "href", "") or ""), quote=True)}" '  # nosemgrep
            f'class="dz-nav-link">'
            f"{_html_mod.escape(str(getattr(item, 'label', '') or ''), quote=False)}"
            f"</a>"
            for item in nav_items
        )
        if is_authenticated:
            dashboard_attr = _html_mod.escape(dashboard_url_raw, quote=True)
            cta_html = (
                f'<a href="{dashboard_attr}" '  # nosemgrep
                f'class="dz-button" data-dz-variant="primary">Dashboard</a>'
            )
        elif nav_cta is not None:
            cta_href = _html_mod.escape(str(getattr(nav_cta, "href", "") or ""), quote=True)
            cta_label = _html_mod.escape(str(getattr(nav_cta, "label", "") or ""), quote=False)
            cta_html = f'<a href="{cta_href}" class="dz-button" data-dz-variant="primary">{cta_label}</a>'  # nosemgrep
        else:
            cta_html = ""
        theme_toggle_html = ""
        if bool(getattr(ctx, "dark_mode_toggle", True)):
            theme_toggle_html = (
                '<button class="dz-theme-toggle" id="dz-theme-toggle" '
                'aria-label="Toggle dark mode" title="Toggle dark mode">'
                '<svg class="dz-theme-toggle__icon dz-theme-toggle__sun" width="20" height="20" '
                'xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" '
                'stroke="currentColor" stroke-width="2">'
                '<path stroke-linecap="round" stroke-linejoin="round" '
                'd="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707'
                'm12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />'
                "</svg>"
                '<svg class="dz-theme-toggle__icon dz-theme-toggle__moon" width="20" height="20" '
                'xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" '
                'stroke="currentColor" stroke-width="2">'
                '<path stroke-linecap="round" stroke-linejoin="round" '
                'd="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354'
                '-5.646z" /></svg>'
                "</button>"
            )
        nav_html = (
            '<header class="dz-site-header"><nav class="dz-site-nav">'
            f'<a href="/" class="dz-site-logo">{product_name}</a>'
            '<div class="dz-nav-items">'
            f"{nav_links_html}{cta_html}{theme_toggle_html}"
            "</div></nav></header>"
        )

        # --- Page <h1> (#1108) ---------------------------------------
        # Pages without a `type: hero` section had no <h1> at all, since
        # all other section types use _section_header() which emits <h2>.
        # Auto-inject one from page.title when no hero is present so every
        # page satisfies the single-<h1> WCAG rule.
        # #1261: when `_render_site_page_chromed` has already transformed
        # typed sections into `{"type": "_typed", ...}` markers, the raw
        # `"hero"` type is gone. The marker dict preserves the pre-transform
        # type as `_original_type` so we can still detect a hero here.
        def _is_hero(s: Any) -> bool:
            if not isinstance(s, dict):
                return False
            stype = str(s.get("type", "") or "")
            if stype == "hero":
                return True
            return stype == "_typed" and str(s.get("_original_type", "") or "") == "hero"

        has_hero = any(_is_hero(s) for s in sections)
        page_h1_html = ""
        if not has_hero:
            page_title_text = _html_mod.escape(
                str(getattr(ctx, "page_title", "") or ""),
                quote=False,
            )
            if page_title_text:
                page_h1_html = f'<h1 class="dz-page-title">{page_title_text}</h1>'

        # --- Section dispatch (only typed sections survive) ---------
        section_parts: list[str] = []
        for section in sections:
            if not isinstance(section, dict):
                continue
            stype = str(section.get("type", "") or "")
            if stype == "_typed":
                section_html = str(section.get("_typed_html", "") or "")
            elif stype in TYPED_SECTION_TYPES or (
                _section_overrides is not None and _section_overrides.get(stype) is not None
            ):
                section_html = render_typed_section(section, overrides=_section_overrides)
            else:
                # Unknown / non-typed section: skip per v0.67.69 directive.
                continue
            bg = str(section.get("background", "") or "")
            if bg and bg != "default":
                bg_attr = _html_mod.escape(bg, quote=True)
                section_parts.append(f'<div class="dz-bg-{bg_attr}">{section_html}</div>')
            else:
                section_parts.append(section_html)
        sections_html = (
            "".join(section_parts)
            if section_parts
            else ('<div class="dz-loading">Loading...</div>')
        )

        # --- QA Personas (dev-only) ---------------------------------
        qa_html = _render_qa_personas_html(qa_personas) if qa_personas else ""

        # --- Main body ----------------------------------------------
        main_class = ' class="dz-page-legal"' if page_type == "legal" else ""
        main_html = (
            f'<main id="dz-site-main"{main_class} data-route="{current_route}">'
            f"{page_h1_html}{sections_html}{qa_html}"
            "</main>"
        )

        # --- Footer (site/includes/footer.html) ---------------------
        footer_cols_html = "".join(_render_site_footer_column(col) for col in footer_columns)
        footer_html = (
            '<footer class="dz-site-footer">'
            f'<div class="dz-footer-content">{footer_cols_html}</div>'
            f'<div class="dz-footer-bottom"><p>{copyright_text}</p></div>'
            "</footer>"
        )

        return f"{nav_html}{main_html}{footer_html}"

    def _render_site_page_chromed(request: Request, ctx: Any) -> str:
        """Render a sitespec page via the typed-Fragment chrome path.

        Phase 4 (v0.67.43): the `app.state.fragment_chrome` flag is no
        longer consulted on the marketing-page path. The typed
        substrate is the only render path; `site/page.html` was
        deleted alongside this flag flip. Per-deployment overrides
        for CSS / JS / theme still live on
        `app.state.fragment_chrome_css_links` etc. — those state
        attributes are retained because they're *asset overrides*,
        not a "use Jinja vs. typed" toggle.

        Body composition:
          1. Walk `ctx.sections`; for each section whose `type` is in
             `TYPED_SECTION_TYPES`, render via `site_section_builder`
             into HTML and replace the section dict with a marker
             (`{"type": "_typed", "_typed_html": "..."}`) so
             `inner_only.html` emits the pre-rendered HTML directly.
          2. Sections with unmigrated types stay as-is — Jinja
             partials still drive their render.
          3. The resulting inner HTML wraps in a typed `Page`
             primitive (with OG / Twitter meta from `ctx.og_meta`,
             per Phase 4 first slice v0.67.42).
        """
        from dazzle.http.runtime.renderers.site_section_builder import (
            TYPED_SECTION_TYPES,
            render_typed_section,
        )

        sections = list(getattr(ctx, "sections", None) or [])
        if sections:
            replaced: list[Any] = []
            for section in sections:
                if not isinstance(section, dict):
                    replaced.append(section)
                    continue
                section_type = str(section.get("type", "") or "")
                has_override = (
                    _section_overrides is not None
                    and _section_overrides.get(section_type) is not None
                )
                if section_type in TYPED_SECTION_TYPES or has_override:
                    replaced.append(
                        {
                            "type": "_typed",
                            "_original_type": section_type,
                            "_typed_html": render_typed_section(
                                section, overrides=_section_overrides
                            ),
                        }
                    )
                else:
                    replaced.append(section)
            ctx = (
                ctx.model_copy(update={"sections": replaced}) if hasattr(ctx, "model_copy") else ctx
            )

        inner_html = _render_site_inner_html(request, ctx)
        page_ctx = PageContext(
            page_title=getattr(ctx, "page_title", "") or "",
            app_name=(
                getattr(ctx, "product_name", None) or getattr(ctx, "app_name", None) or "Dazzle"
            ),
            current_route=getattr(ctx, "current_route", "") or "/",
        )
        app_state = request.app.state
        css_links_list = list(
            getattr(app_state, "fragment_chrome_css_links", None)
            or ("/static/dist/dazzle.min.css",)
        )
        # Phase 4 chrome-flag flip (v0.67.43): honour the project's
        # custom.css override here too. The legacy `site/page.html` →
        # `site_base.html` chain emitted `<link href="/static/css/custom.css">`
        # in `<head>` when `ctx.custom_css=True`; the typed path now
        # appends the same link to `css_links` so the override survives
        # the migration.
        if getattr(ctx, "custom_css", False) and "/static/css/custom.css" not in css_links_list:
            css_links_list.append("/static/css/custom.css")
        css_links = tuple(css_links_list)
        js_scripts = tuple(
            getattr(app_state, "fragment_chrome_js_scripts", None)
            or ("/static/dist/dazzle.min.js",)
        )
        if "data-qa-personas" in inner_html:
            # #1553: the QA panel's delegated magic-link controller —
            # loaded only when the dev-only panel actually renders
            # (the renderer marks its section with data-qa-personas).
            js_scripts = tuple(list(js_scripts) + ["/static/js/dz-qa.js"])
        theme = getattr(app_state, "fragment_chrome_theme", None)

        # Phase 4 (v0.67.42): thread Open Graph + Twitter card meta
        # tags from `ctx.og_meta` so the typed path matches the legacy
        # Jinja path's `site/includes/og_meta.html` output.
        extra_meta, og_meta = _og_meta_pairs(getattr(ctx, "og_meta", None))

        page = build_page(
            page_ctx,
            inner_html,
            css_links=css_links,
            js_scripts=js_scripts,
            theme=theme,
            extra_meta=extra_meta,
            og_meta=og_meta,
        )
        return FragmentRenderer().render(page)

    def _og_meta_pairs(
        og: Any,
    ) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
        """Split SitePageContext.og_meta into `name=` and `property=` tuples.

        Mirrors `site/includes/og_meta.html`:
          - `<meta name="description">`, `<meta name="twitter:*">` → `extra_meta`
          - `<meta property="og:*">` → `og_meta`

        Returns `((), ())` when ``og`` is None / falsy.
        """
        if not og:
            return ((), ())
        title = getattr(og, "title", "") or ""
        description = getattr(og, "description", "") or ""
        og_type = getattr(og, "og_type", "") or ""

        name_pairs: list[tuple[str, str]] = []
        property_pairs: list[tuple[str, str]] = []
        if description:
            name_pairs.append(("description", description))
        if title:
            property_pairs.append(("og:title", title))
        if description:
            property_pairs.append(("og:description", description))
        if og_type:
            property_pairs.append(("og:type", og_type))
        if title or description:
            name_pairs.append(("twitter:card", "summary"))
        if title:
            name_pairs.append(("twitter:title", title))
        if description:
            name_pairs.append(("twitter:description", description))
        return tuple(name_pairs), tuple(property_pairs)

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
                    dark_mode_toggle=dark_mode_toggle,
                    qa_personas=qa_personas,
                    consent=consent_dict,
                    consent_state_json=consent_json,
                    active_analytics_providers=active_providers,
                    tenant_slug=tenant_slug,
                    privacy_page_url=privacy_url,
                    cookie_policy_url=cookie_url,
                )
                return HTMLResponse(content=_render_site_page_chromed(request, ctx))
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
                    dark_mode_toggle=dark_mode_toggle,
                    consent=consent_dict,
                    consent_state_json=consent_json,
                    active_analytics_providers=active_providers,
                    tenant_slug=tenant_slug,
                    privacy_page_url=privacy_url,
                    cookie_policy_url=cookie_url,
                )
                return _render_site_page_chromed(request, ctx)

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
                dark_mode_toggle=dark_mode_toggle,
                consent=consent_dict,
                consent_state_json=consent_json,
                active_analytics_providers=active_providers,
                tenant_slug=tenant_slug,
                privacy_page_url=privacy_url,
                cookie_policy_url=cookie_url,
            )
            return _render_site_page_chromed(request, ctx)

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
                dark_mode_toggle=dark_mode_toggle,
                consent=consent_dict,
                consent_state_json=consent_json,
                active_analytics_providers=active_providers,
                tenant_slug=tenant_slug,
                privacy_page_url=privacy_url,
                cookie_policy_url=cookie_url,
            )
            return _render_site_page_chromed(request, ctx)

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

    router = APIRouter()

    # Phase 1.D.2 (v0.67.37): all auth/2FA routes use typed-Fragment
    # views that pull per-deployment CSS overrides from
    # `app.state.fragment_chrome_css_links` rather than the legacy
    # project-root probe. `project_root` is kept on the signature for
    # backward call-site compatibility but is no longer consulted.
    _ = project_root

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

    def _typed_chrome_assets(app_state: object) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Resolve the CSS+JS asset tuples for typed-Fragment auth pages.

        Phase 1.E (v0.67.33): the auth GET handlers always render typed
        views (the chrome=off Jinja fallback is gone). This helper
        centralises the per-deployment override lookup that all seven
        handlers share."""
        css = tuple(
            getattr(app_state, "fragment_chrome_css_links", None)
            or ("/static/dist/dazzle.min.css",)
        )
        js = tuple(
            getattr(app_state, "fragment_chrome_js_scripts", None)
            or ("/static/dist/dazzle.min.js",)
        )
        return css, js

    @router.get("/login", response_class=HTMLResponse, include_in_schema=False)
    async def login_page(
        request: Request,
        sitespec: dict[str, Any] = sitespec_data,
        next: str = "/",
        error: str = "",
    ) -> str:
        """Serve the login page.

        Phase 1.E (v0.67.33): typed-Fragment is the only path —
        `site/auth/login.html` was deleted alongside the chrome=off
        branch. `app.state.auth_password_mode_enabled` still selects
        between magic-link and password views.
        """
        from dazzle.http.runtime.auth.auth_views import (
            build_login_magic_link_view,
            build_login_password_view,
        )

        app_state = request.app.state
        css_links, js_scripts = _typed_chrome_assets(app_state)
        product_name = sitespec.get("brand", {}).get("product_name", "Dazzle")
        password_mode = bool(getattr(app_state, "auth_password_mode_enabled", False))
        sso_providers = tuple(getattr(app_state, "sso_providers", ()) or ())
        error_message = ""
        if error == "invalid_magic_link":
            error_message = "That sign-in link is invalid or expired. Request a new one below."
        elif error == "invalid_credentials":
            error_message = "That email and password didn't match. Try again."
        elif error == "sso_failed":
            error_message = "We couldn't complete the sign-in. Please try again."
        elif error == "sso_no_email":
            error_message = (
                "That SSO provider didn't share an email address with us — "
                "try a different sign-in method."
            )
        elif error == "sso_email_unverified":
            error_message = (
                "Your SSO email address isn't verified with the provider yet. "
                "Verify it and try again."
            )
        elif error == "sso_provider_unknown":
            error_message = "That SSO provider isn't configured on this deployment."
        builder = build_login_password_view if password_mode else build_login_magic_link_view
        page = builder(
            page_title="Sign in",
            product_name=product_name,
            next_url=next,
            error_message=error_message,
            sso_providers=sso_providers,
            css_links=css_links,
            js_scripts=js_scripts,
        )
        return FragmentRenderer().render(page)

    @router.get("/login/sent", response_class=HTMLResponse, include_in_schema=False)
    async def login_sent_page(
        request: Request,
        sitespec: dict[str, Any] = sitespec_data,
        email: str = "",
    ) -> str:
        """Post-magic-link confirmation page (Phase 1.E: typed-only)."""

        app_state = request.app.state
        css_links, js_scripts = _typed_chrome_assets(app_state)
        product_name = sitespec.get("brand", {}).get("product_name", "Dazzle")
        page = build_login_sent_view(
            product_name=product_name,
            # email NOT echoed back — defensive against account-
            # enumeration via reflected input.
            email="",
            css_links=css_links,
            js_scripts=js_scripts,
        )
        return FragmentRenderer().render(page)

    @router.get("/signup", response_class=HTMLResponse, include_in_schema=False)
    async def signup_page(
        request: Request,
        sitespec: dict[str, Any] = sitespec_data,
        next: str = "/",
        error: str = "",
    ) -> str:
        """Serve the signup page.

        Phase 1.E (v0.67.33): typed-Fragment is the only path —
        `site/auth/signup.html` was deleted. `auth_password_mode_enabled`
        still selects between magic-link and password views.
        """
        from dazzle.http.runtime.auth.auth_views import (
            build_signup_magic_link_view,
            build_signup_password_view,
        )

        app_state = request.app.state
        css_links, js_scripts = _typed_chrome_assets(app_state)
        product_name = sitespec.get("brand", {}).get("product_name", "Dazzle")
        password_mode = bool(getattr(app_state, "auth_password_mode_enabled", False))
        error_message = ""
        if error == "mismatch":
            error_message = "The two password fields didn't match. Try again."
        elif error == "already_registered":
            error_message = "An account with that email already exists. Try signing in instead."
        elif error == "create_failed":
            error_message = "We couldn't create that account. Please try again."
        elif error == "invalid_email":
            error_message = "That email address doesn't look right."
        builder = build_signup_password_view if password_mode else build_signup_magic_link_view
        page = builder(
            page_title="Create your account",
            product_name=product_name,
            next_url=next,
            error_message=error_message,
            css_links=css_links,
            js_scripts=js_scripts,
        )
        return FragmentRenderer().render(page)

    @router.get("/forgot-password", response_class=HTMLResponse, include_in_schema=False)
    async def forgot_password_page(
        request: Request,
        sitespec: dict[str, Any] = sitespec_data,
    ) -> str:
        """Serve the forgot-password page (Phase 1.E: typed-only)."""

        app_state = request.app.state
        css_links, js_scripts = _typed_chrome_assets(app_state)
        page = build_forgot_password_view(
            product_name=sitespec.get("brand", {}).get("product_name", "Dazzle"),
            css_links=css_links,
            js_scripts=js_scripts,
        )
        return FragmentRenderer().render(page)

    @router.get("/forgot-password/sent", response_class=HTMLResponse, include_in_schema=False)
    async def forgot_password_sent_page(
        request: Request,
        sitespec: dict[str, Any] = sitespec_data,
    ) -> str:
        """Post-forgot-password confirmation page (Phase 1.E: typed-only)."""

        app_state = request.app.state
        css_links, js_scripts = _typed_chrome_assets(app_state)
        product_name = sitespec.get("brand", {}).get("product_name", "Dazzle")
        page = build_forgot_password_sent_view(
            product_name=product_name,
            css_links=css_links,
            js_scripts=js_scripts,
        )
        return FragmentRenderer().render(page)

    @router.get("/reset-password", response_class=HTMLResponse, include_in_schema=False)
    async def reset_password_page(
        request: Request,
        sitespec: dict[str, Any] = sitespec_data,
        token: str = "",
        error: str = "",
    ) -> str:
        """Serve the reset-password page (Phase 1.E: typed-only)."""

        app_state = request.app.state
        css_links, js_scripts = _typed_chrome_assets(app_state)
        error_message = ""
        if error == "mismatch":
            error_message = "The two password fields didn't match. Try again."
        elif error == "invalid":
            error_message = "That reset link is invalid or expired. Request a new one."
        page = build_reset_password_view(
            product_name=sitespec.get("brand", {}).get("product_name", "Dazzle"),
            token=token,
            error_message=error_message,
            css_links=css_links,
            js_scripts=js_scripts,
        )
        return FragmentRenderer().render(page)

    @router.get("/reset-password/done", response_class=HTMLResponse, include_in_schema=False)
    async def reset_password_done_page(
        request: Request,
        sitespec: dict[str, Any] = sitespec_data,
    ) -> str:
        """Post-reset confirmation page (Phase 1.E: typed-only)."""

        app_state = request.app.state
        css_links, js_scripts = _typed_chrome_assets(app_state)
        product_name = sitespec.get("brand", {}).get("product_name", "Dazzle")
        page = build_reset_password_done_view(
            product_name=product_name,
            css_links=css_links,
            js_scripts=js_scripts,
        )
        return FragmentRenderer().render(page)

    @router.get("/2fa/setup", include_in_schema=False)
    async def two_factor_setup_page(
        request: Request,
        sitespec: dict[str, Any] = sitespec_data,
    ) -> Response:
        """Serve the 2FA enrolment page (authenticated users only).

        Phase 1.D.2 (v0.67.37): typed-Fragment is the only path —
        `site/auth/2fa_setup.html` was deleted. DOM scaffold is
        emitted via RawHTML inside the typed Page; client behavior
        lives in `/static/js/dz-2fa-setup.js` (referenced via
        `Page.js_scripts`).
        """
        redirect = _require_auth(request, "/2fa/setup")
        if redirect is not None:
            return redirect

        app_state = request.app.state
        css_links, js_scripts = _typed_chrome_assets(app_state)
        # The 2FA setup page also needs the dz-2fa-setup.js client.
        js_scripts = tuple(list(js_scripts) + ["/static/js/dz-2fa-setup.js"])
        page = build_2fa_setup_view(
            product_name=sitespec.get("brand", {}).get("product_name", "Dazzle"),
            css_links=css_links,
            js_scripts=js_scripts,
        )
        return HTMLResponse(content=FragmentRenderer().render(page))

    @router.get("/2fa/settings", include_in_schema=False)
    async def two_factor_settings_page(
        request: Request,
        sitespec: dict[str, Any] = sitespec_data,
    ) -> Response:
        """Serve the 2FA management page (Phase 1.D.2: typed-only)."""
        redirect = _require_auth(request, "/2fa/settings")
        if redirect is not None:
            return redirect

        app_state = request.app.state
        css_links, js_scripts = _typed_chrome_assets(app_state)
        js_scripts = tuple(list(js_scripts) + ["/static/js/dz-2fa-settings.js"])
        page = build_2fa_settings_view(
            product_name=sitespec.get("brand", {}).get("product_name", "Dazzle"),
            css_links=css_links,
            js_scripts=js_scripts,
        )
        return HTMLResponse(content=FragmentRenderer().render(page))

    @router.get("/2fa/challenge", response_class=HTMLResponse, include_in_schema=False)
    async def two_factor_challenge_page(
        request: Request,
        session: str = "",
        method: str = "",
        mode: str = "",
        sent: str = "",
        error: str = "",
        sitespec: dict[str, Any] = sitespec_data,
    ) -> str:
        """Serve the mid-login 2FA challenge page.

        Phase 1.D.1 (v0.67.35): typed-Fragment is the only path —
        `site/auth/2fa_challenge.html` was deleted. The view posts to
        the form-encoded `/auth/2fa/verify/submit` endpoint and does
        mode switching via plain links rather than JS.

        Public route — the pre-login session_token is the sole
        credential the verify endpoint relies on. The token threads
        through as ``?session=<token>`` from the login flow.
        """

        app_state = request.app.state
        css_links, js_scripts = _typed_chrome_assets(app_state)
        product_name = sitespec.get("brand", {}).get("product_name", "Dazzle")
        # `mode` is the canonical query name; accept legacy `method=`
        # too so links from older bookmarks still work.
        chosen_mode = mode or method or "totp"
        if chosen_mode not in ("totp", "email_otp", "recovery"):
            chosen_mode = "totp"
        error_message = ""
        if error == "invalid_code":
            error_message = "That code didn't match. Try again."
        page = build_2fa_challenge_view(
            product_name=product_name,
            session_token=session,
            mode=chosen_mode,  # type: ignore[arg-type]
            email_otp_enabled=True,
            code_sent=bool(sent),
            error_message=error_message,
            css_links=css_links,
            js_scripts=js_scripts,
        )
        return FragmentRenderer().render(page)

    return router
