"""Context builders for marketing/site pages.

Converts raw sitespec dicts into the typed Pydantic context models
(`dazzle.render.context`) consumed by the typed-Fragment site renderer.
(Jinja2 was removed framework-wide in #1042/ADR-0023 — these are typed
contexts, not template contexts.)
"""

from datetime import UTC, datetime
from typing import Any

from dazzle.render.context import (
    QAPersonaCardContext,
    SiteCTAContext,
    SiteFooterColumn,
    SiteFooterLink,
    SiteNavItem,
    SiteOGMeta,
    SitePageContext,
)


def _extract_nav_items(
    nav: dict[str, Any],
    is_authenticated: bool = False,
) -> list[SiteNavItem]:
    """Extract navigation items from nav config.

    When *is_authenticated* is True the ``authenticated`` item list is
    preferred (if non-empty), falling back to ``public``/``items``.
    """
    if is_authenticated:
        auth_items = nav.get("authenticated")
        if auth_items:
            return [
                SiteNavItem(label=item.get("label", ""), href=item.get("href", "#"))
                for item in auth_items
            ]
    items = nav.get("public") or nav.get("items") or []
    return [SiteNavItem(label=item.get("label", ""), href=item.get("href", "#")) for item in items]


def _extract_nav_cta(
    nav: dict[str, Any],
    auth_config: dict[str, Any] | None = None,
) -> SiteCTAContext | None:
    """Extract CTA button from nav config or auth config."""
    cta = nav.get("cta")
    if cta:
        return SiteCTAContext(
            label=cta.get("label", "Get Started"),
            href=cta.get("href", "/app"),
        )
    if auth_config:
        primary_entry = auth_config.get("primary_entry", "/login")
        label = "Sign In" if "login" in primary_entry else "Get Started"
        return SiteCTAContext(label=label, href=primary_entry)
    return None


def _extract_footer_columns(footer: dict[str, Any]) -> list[SiteFooterColumn]:
    """Extract footer columns from footer config."""
    columns = []
    for col in footer.get("columns", []):
        links = [
            SiteFooterLink(label=link.get("label", ""), href=link.get("href", "#"))
            for link in col.get("links", [])
        ]
        columns.append(SiteFooterColumn(title=col.get("title", ""), links=links))
    return columns


def _brand_value(brand: dict[str, Any], key: str, default: str) -> str:
    """Null-safe brand lookup (#1423).

    `.get(key, default)` only uses the default for *absent* keys \u2014 a sitespec
    that carries the key present-but-null (`company_legal_name: null`, injected
    by normalization) returns that None, and a downstream `str.replace(..., None)`
    500s the whole root page. `or` degrades null to the default.
    """
    return brand.get(key) or default


def _build_copyright_text(footer: dict[str, Any], brand: dict[str, Any]) -> str:
    """Build copyright/disclaimer text with template variable substitution."""
    product_name = _brand_value(brand, "product_name", "My App")
    text = (
        footer.get("disclaimer")
        or footer.get("copyright")
        or f"\u00a9 {datetime.now(tz=UTC).year} {product_name}"
    )
    text = text.replace("{{year}}", str(datetime.now(tz=UTC).year))
    text = text.replace(
        "{{company_legal_name}}",
        _brand_value(brand, "company_legal_name", product_name),
    )
    return text


def _build_og_meta(
    product_name: str,
    page_title: str,
    page_description: str,
) -> SiteOGMeta:
    """Build OG meta context from page data."""
    return SiteOGMeta(
        title=page_title or product_name,
        description=page_description or product_name,
    )


def build_site_page_context(
    sitespec_data: dict[str, Any],
    path: str,
    page_data: dict[str, Any] | None = None,
    *,
    custom_css: bool = False,
    is_authenticated: bool = False,
    dashboard_url: str = "/app",
    qa_personas: list[dict[str, Any]] | None = None,
    consent: dict[str, Any] | None = None,
    consent_state_json: str = "null",
    privacy_page_url: str | None = None,
    cookie_policy_url: str | None = None,
    active_analytics_providers: list[dict[str, Any]] | None = None,
    tenant_slug: str | None = None,
) -> SitePageContext:
    """Build a SitePageContext from sitespec data and page data.

    Args:
        sitespec_data: Site specification data.
        path: Current page route.
        page_data: Pre-resolved page data (sections, title, etc.).
        custom_css: Include project-level custom CSS.
        is_authenticated: Whether the current user is authenticated.
        dashboard_url: URL to the user's dashboard/workspace.
        qa_personas: Optional list of QA persona dicts (populated in dev/QA mode).

    Returns:
        SitePageContext ready for template rendering.
    """
    brand = sitespec_data.get("brand", {})
    product_name = _brand_value(brand, "product_name", "My App")  # null-safe (#1423)
    layout = sitespec_data.get("layout", {})
    nav = layout.get("nav", {})
    auth_config = layout.get("auth") or {}
    footer = layout.get("footer", {})

    nav_items = _extract_nav_items(nav, is_authenticated=is_authenticated)
    nav_cta = _extract_nav_cta(nav, auth_config)
    footer_columns = _extract_footer_columns(footer)
    copyright_text = _build_copyright_text(footer, brand)

    page_title = product_name
    page_type = "landing"
    page_description = ""
    sections: list[dict[str, Any]] = []

    if page_data:
        page_title = page_data.get("title") or product_name
        page_type = page_data.get("type", "landing")
        sections = page_data.get("sections", [])
        # Normalize feature_grid → features for template dispatch
        for sec in sections:
            if sec.get("type") == "feature_grid":
                sec["type"] = "features"
        # Extract description from hero section subhead
        for sec in sections:
            if sec.get("type") == "hero":
                page_description = sec.get("subhead", "")
                break

    # Auto-alternate section backgrounds when configured
    section_bg_mode = layout.get("section_backgrounds", "")
    if section_bg_mode == "auto-alternate":
        for i, sec in enumerate(sections):
            if not sec.get("background"):
                sec["background"] = "alt" if i % 2 == 1 else "default"

    og_meta = _build_og_meta(product_name, page_title, page_description)

    persona_cards = [QAPersonaCardContext(**p) for p in (qa_personas or [])]

    return SitePageContext(
        product_name=product_name,
        page_title=page_title,
        page_type=page_type,
        current_route=path,
        nav_items=nav_items,
        nav_cta=nav_cta,
        footer_columns=footer_columns,
        copyright_text=copyright_text,
        og_meta=og_meta,
        sections=sections,
        custom_css=custom_css,
        is_authenticated=is_authenticated,
        dashboard_url=dashboard_url,
        qa_personas=persona_cards,
        consent=consent,
        consent_state_json=consent_state_json,
        privacy_page_url=privacy_page_url,
        cookie_policy_url=cookie_policy_url,
        active_analytics_providers=active_analytics_providers or [],
        tenant_slug=tenant_slug,
    )


# build_site_auth_context retired in Phase 1.D.2 (v0.67.37). All
# auth-page surfaces now render via typed-Fragment views in
# `dazzle.http.runtime.auth.{auth_views,two_factor_views}`. The
# `SiteAuthContext` Pydantic model in `template_context.py` is kept
# for now because the template_renderer's Union type still references
# it, but no production code path constructs it.


# build_site_404_context and build_site_error_context were retired in
# Phase 2.A (v0.67.34) — see template_context.py for the matching
# Site404Context / SiteErrorContext removal notes. Marketing-site
# errors render via `dazzle.http.runtime.error_views.build_site_*_view`.
