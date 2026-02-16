"""Context builders for site page Jinja2 templates.

Converts raw sitespec dicts into typed Pydantic context models
that are passed to Jinja2 templates for rendering.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from dazzle_ui.runtime.template_context import (
    Site404Context,
    SiteAuthContext,
    SiteCTAContext,
    SiteErrorContext,
    SiteFooterColumn,
    SiteFooterLink,
    SiteNavItem,
    SiteOGMeta,
    SitePageContext,
)


def _extract_nav_items(nav: dict[str, Any]) -> list[SiteNavItem]:
    """Extract navigation items from nav config."""
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


def _build_copyright_text(footer: dict[str, Any], brand: dict[str, Any]) -> str:
    """Build copyright/disclaimer text with template variable substitution."""
    product_name = brand.get("product_name", "My App")
    text = (
        footer.get("disclaimer")
        or footer.get("copyright")
        or f"\u00a9 {datetime.now(tz=UTC).year} {product_name}"
    )
    text = text.replace("{{year}}", str(datetime.now(tz=UTC).year))
    text = text.replace(
        "{{company_legal_name}}",
        brand.get("company_legal_name", product_name),
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
) -> SitePageContext:
    """Build a SitePageContext from sitespec data and page data.

    Args:
        sitespec_data: Site specification data.
        path: Current page route.
        page_data: Pre-resolved page data (sections, title, etc.).
        custom_css: Include project-level custom CSS.

    Returns:
        SitePageContext ready for template rendering.
    """
    brand = sitespec_data.get("brand", {})
    product_name = brand.get("product_name", "My App")
    layout = sitespec_data.get("layout", {})
    nav = layout.get("nav", {})
    auth_config = layout.get("auth") or {}
    footer = layout.get("footer", {})

    nav_items = _extract_nav_items(nav)
    nav_cta = _extract_nav_cta(nav, auth_config)
    footer_columns = _extract_footer_columns(footer)
    copyright_text = _build_copyright_text(footer, brand)

    page_title = product_name
    page_description = ""
    sections: list[dict[str, Any]] = []

    if page_data:
        page_title = page_data.get("title") or product_name
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

    og_meta = _build_og_meta(product_name, page_title, page_description)

    return SitePageContext(
        product_name=product_name,
        page_title=page_title,
        current_route=path,
        nav_items=nav_items,
        nav_cta=nav_cta,
        footer_columns=footer_columns,
        copyright_text=copyright_text,
        og_meta=og_meta,
        sections=sections,
        custom_css=custom_css,
    )


def build_site_auth_context(
    sitespec_data: dict[str, Any],
    page_type: str,
    *,
    custom_css: bool = False,
) -> SiteAuthContext:
    """Build a SiteAuthContext for auth page templates.

    Args:
        sitespec_data: Site specification data.
        page_type: One of "login", "signup", "forgot_password", "reset_password".
        custom_css: Include project-level custom CSS.

    Returns:
        SiteAuthContext ready for template rendering.
    """
    brand = sitespec_data.get("brand", {})
    product_name = brand.get("product_name", "My App")

    configs: dict[str, dict[str, Any]] = {
        "login": {
            "title": "Sign In",
            "action_url": "/auth/login",
            "button_text": "Sign In",
            "is_login": True,
            "other_page": "/signup",
            "other_link_text": "Create an account",
            "show_forgot_password": True,
            "show_name_field": False,
            "show_confirm_password": False,
            "show_success_alert": False,
            "subtitle": "",
        },
        "signup": {
            "title": "Create Account",
            "action_url": "/auth/register",
            "button_text": "Sign Up",
            "is_login": False,
            "other_page": "/login",
            "other_link_text": "Sign in instead",
            "show_forgot_password": False,
            "show_name_field": True,
            "show_confirm_password": True,
            "show_success_alert": False,
            "subtitle": "",
        },
        "forgot_password": {
            "title": "Reset Password",
            "action_url": "/auth/forgot-password",
            "button_text": "Send Reset Link",
            "is_login": False,
            "other_page": "/login",
            "other_link_text": "Back to sign in",
            "show_forgot_password": False,
            "show_name_field": False,
            "show_confirm_password": False,
            "show_success_alert": True,
            "subtitle": "Enter your email and we\u2019ll send you a link to reset your password.",
        },
        "reset_password": {
            "title": "Set New Password",
            "action_url": "/auth/reset-password",
            "button_text": "Reset Password",
            "is_login": False,
            "other_page": "/login",
            "other_link_text": "Back to sign in",
            "show_forgot_password": False,
            "show_name_field": False,
            "show_confirm_password": True,
            "show_success_alert": False,
            "subtitle": "",
        },
    }

    cfg = configs.get(page_type, configs["login"])

    return SiteAuthContext(
        product_name=product_name,
        page_type=page_type,
        custom_css=custom_css,
        **cfg,
    )


def build_site_404_context(
    sitespec_data: dict[str, Any],
    *,
    custom_css: bool = False,
) -> Site404Context:
    """Build a Site404Context for 404 error page template.

    Args:
        sitespec_data: Site specification data.
        custom_css: Include project-level custom CSS.

    Returns:
        Site404Context ready for template rendering.
    """
    brand = sitespec_data.get("brand", {})
    product_name = brand.get("product_name", "My App")
    layout = sitespec_data.get("layout", {})
    nav = layout.get("nav", {})
    auth_config = layout.get("auth") or {}
    footer = layout.get("footer", {})

    return Site404Context(
        product_name=product_name,
        nav_items=_extract_nav_items(nav),
        nav_cta=_extract_nav_cta(nav, auth_config),
        footer_columns=_extract_footer_columns(footer),
        copyright_text=_build_copyright_text(footer, brand),
        custom_css=custom_css,
    )


def build_site_error_context(
    sitespec_data: dict[str, Any],
    *,
    message: str = "",
    custom_css: bool = False,
) -> SiteErrorContext:
    """Build a SiteErrorContext for error page templates (403, 500, etc.).

    Args:
        sitespec_data: Site specification data.
        message: Error message to display.
        custom_css: Include project-level custom CSS.

    Returns:
        SiteErrorContext ready for template rendering.
    """
    brand = sitespec_data.get("brand", {})
    product_name = brand.get("product_name", "My App")
    layout = sitespec_data.get("layout", {})
    nav = layout.get("nav", {})
    auth_config = layout.get("auth") or {}
    footer = layout.get("footer", {})

    return SiteErrorContext(
        product_name=product_name,
        nav_items=_extract_nav_items(nav),
        nav_cta=_extract_nav_cta(nav, auth_config),
        footer_columns=_extract_footer_columns(footer),
        copyright_text=_build_copyright_text(footer, brand),
        custom_css=custom_css,
        message=message,
    )
