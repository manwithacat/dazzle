"""Tests for Jinja2 site page rendering.

Tests cover:
- Section template rendering (hero, features, cta, faq, etc.)
- Auth page rendering (login, signup, forgot/reset password)
- 404 page rendering
- Context builder functions
- Backward-compatible shims in site_renderer.py
"""

from __future__ import annotations

from typing import Any


def _render(template: str, context_model: Any) -> str:
    """Helper to render a site template with a context model."""
    from dazzle_ui.runtime.template_renderer import render_site_page

    return render_site_page(template, context_model)


# =========================================================================
# Context Builder Tests
# =========================================================================


class TestBuildSitePageContext:
    """Tests for build_site_page_context()."""

    def test_basic_context(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {
            "brand": {"product_name": "TestApp"},
            "layout": {"nav": {}, "footer": {}},
        }
        ctx = build_site_page_context(sitespec, "/")
        assert ctx.product_name == "TestApp"
        assert ctx.current_route == "/"
        assert ctx.sections == []

    def test_nav_items_extracted(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {
            "brand": {"product_name": "App"},
            "layout": {
                "nav": {
                    "public": [
                        {"label": "Home", "href": "/"},
                        {"label": "About", "href": "/about"},
                    ],
                    "cta": {"label": "Sign Up", "href": "/signup"},
                },
                "footer": {},
            },
        }
        ctx = build_site_page_context(sitespec, "/")
        assert len(ctx.nav_items) == 2
        assert ctx.nav_items[0].label == "Home"
        assert ctx.nav_cta is not None
        assert ctx.nav_cta.label == "Sign Up"

    def test_footer_columns_extracted(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {
            "brand": {"product_name": "App"},
            "layout": {
                "nav": {},
                "footer": {
                    "columns": [
                        {
                            "title": "Company",
                            "links": [{"label": "About", "href": "/about"}],
                        }
                    ]
                },
            },
        }
        ctx = build_site_page_context(sitespec, "/")
        assert len(ctx.footer_columns) == 1
        assert ctx.footer_columns[0].title == "Company"
        assert len(ctx.footer_columns[0].links) == 1

    def test_sections_from_page_data(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {
            "brand": {"product_name": "App"},
            "layout": {},
        }
        page_data = {
            "title": "Home",
            "sections": [
                {"type": "hero", "headline": "Hello"},
                {"type": "cta", "headline": "Sign Up"},
            ],
        }
        ctx = build_site_page_context(sitespec, "/", page_data=page_data)
        assert len(ctx.sections) == 2
        assert ctx.page_title == "Home"

    def test_feature_grid_normalized_to_features(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {}, "layout": {}}
        page_data = {
            "title": "Home",
            "sections": [{"type": "feature_grid", "items": []}],
        }
        ctx = build_site_page_context(sitespec, "/", page_data=page_data)
        assert ctx.sections[0]["type"] == "features"

    def test_og_meta_from_hero(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {"product_name": "App"}, "layout": {}}
        page_data = {
            "title": "Home",
            "sections": [{"type": "hero", "headline": "Hello", "subhead": "World"}],
        }
        ctx = build_site_page_context(sitespec, "/", page_data=page_data)
        assert ctx.og_meta is not None
        assert ctx.og_meta.description == "World"

    def test_custom_css_flag(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {}, "layout": {}}
        ctx = build_site_page_context(sitespec, "/", custom_css=True)
        assert ctx.custom_css is True


class TestBuildSiteAuthContext:
    """Tests for build_site_auth_context()."""

    def test_login_context(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_auth_context

        ctx = build_site_auth_context({"brand": {"product_name": "App"}}, "login")
        assert ctx.title == "Sign In"
        assert ctx.action_url == "/auth/login"
        assert ctx.is_login is True
        assert ctx.show_forgot_password is True

    def test_signup_context(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_auth_context

        ctx = build_site_auth_context({"brand": {"product_name": "App"}}, "signup")
        assert ctx.title == "Create Account"
        assert ctx.show_name_field is True
        assert ctx.show_confirm_password is True

    def test_forgot_password_context(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_auth_context

        ctx = build_site_auth_context({"brand": {}}, "forgot_password")
        assert ctx.title == "Reset Password"
        assert ctx.show_success_alert is True

    def test_reset_password_context(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_auth_context

        ctx = build_site_auth_context({"brand": {}}, "reset_password")
        assert ctx.title == "Set New Password"
        assert ctx.show_confirm_password is True


class TestBuildSite404Context:
    """Tests for build_site_404_context()."""

    def test_basic_404(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_404_context

        ctx = build_site_404_context({"brand": {"product_name": "App"}, "layout": {}})
        assert ctx.product_name == "App"


# =========================================================================
# Template Rendering Tests
# =========================================================================


class TestSitePageTemplate:
    """Tests for site/page.html template rendering."""

    def test_renders_hero_section(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {"product_name": "TestApp"}, "layout": {}}
        page_data = {
            "title": "Home",
            "sections": [
                {
                    "type": "hero",
                    "headline": "Welcome to TestApp",
                    "subhead": "The best app ever",
                    "primary_cta": {"label": "Get Started", "href": "/signup"},
                }
            ],
        }
        ctx = build_site_page_context(sitespec, "/", page_data=page_data)
        html = _render("site/page.html", ctx)

        assert "Welcome to TestApp" in html
        assert "The best app ever" in html
        assert "Get Started" in html
        assert "/signup" in html
        assert "dz-section-hero" in html

    def test_renders_features_section(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {"product_name": "App"}, "layout": {}}
        page_data = {
            "title": "Home",
            "sections": [
                {
                    "type": "features",
                    "headline": "Features",
                    "items": [
                        {"title": "Fast", "body": "Lightning speed", "icon": "zap"},
                        {"title": "Secure", "body": "Bank-grade security"},
                    ],
                }
            ],
        }
        ctx = build_site_page_context(sitespec, "/", page_data=page_data)
        html = _render("site/page.html", ctx)

        assert "Fast" in html
        assert "Lightning speed" in html
        assert 'data-lucide="zap"' in html
        assert "Secure" in html

    def test_renders_faq_section(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {}, "layout": {}}
        page_data = {
            "title": "FAQ",
            "sections": [
                {
                    "type": "faq",
                    "headline": "FAQ",
                    "items": [{"question": "How much?", "answer": "Free forever."}],
                }
            ],
        }
        ctx = build_site_page_context(sitespec, "/faq", page_data=page_data)
        html = _render("site/page.html", ctx)

        assert "How much?" in html
        assert "Free forever." in html
        assert "collapse" in html

    def test_renders_pricing_section(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {}, "layout": {}}
        page_data = {
            "title": "Pricing",
            "sections": [
                {
                    "type": "pricing",
                    "headline": "Pricing",
                    "tiers": [
                        {
                            "name": "Pro",
                            "price": "$29",
                            "period": "/mo",
                            "features": ["Unlimited users", "Priority support"],
                            "highlighted": True,
                            "cta": {"label": "Buy Now", "href": "/buy"},
                        }
                    ],
                }
            ],
        }
        ctx = build_site_page_context(sitespec, "/pricing", page_data=page_data)
        html = _render("site/page.html", ctx)

        assert "Pro" in html
        assert "$29" in html
        assert "Unlimited users" in html
        assert "Buy Now" in html
        assert "dz-pricing-highlighted" in html
        assert "btn btn-secondary" in html

    def test_renders_card_grid_section(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {}, "layout": {}}
        page_data = {
            "title": "Services",
            "sections": [
                {
                    "type": "card_grid",
                    "headline": "Services",
                    "items": [
                        {
                            "title": "Consulting",
                            "body": "Expert guidance",
                            "icon": "briefcase",
                            "cta": {"label": "Learn More", "href": "/consulting"},
                        }
                    ],
                }
            ],
        }
        ctx = build_site_page_context(sitespec, "/", page_data=page_data)
        html = _render("site/page.html", ctx)

        assert "dz-section-card-grid" in html
        assert "Consulting" in html
        assert 'data-lucide="briefcase"' in html
        assert "Learn More" in html

    def test_renders_split_content_reversed(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {}, "layout": {}}
        page_data = {
            "title": "About",
            "sections": [
                {
                    "type": "split_content",
                    "headline": "Our Story",
                    "body": "Founded in 2020",
                    "alignment": "right",
                    "media": {"kind": "image", "src": "/img/team.webp", "alt": "Team photo"},
                }
            ],
        }
        ctx = build_site_page_context(sitespec, "/about", page_data=page_data)
        html = _render("site/page.html", ctx)

        assert "dz-split--reversed" in html
        assert "Our Story" in html
        assert "/img/team.webp" in html

    def test_renders_trust_bar(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {}, "layout": {}}
        page_data = {
            "title": "Home",
            "sections": [
                {
                    "type": "trust_bar",
                    "items": [
                        {"text": "ICAEW Certified", "icon": "shield-check"},
                        {"text": "GDPR Compliant", "icon": "lock"},
                    ],
                }
            ],
        }
        ctx = build_site_page_context(sitespec, "/", page_data=page_data)
        html = _render("site/page.html", ctx)

        assert "dz-section-trust-bar" in html
        assert "ICAEW Certified" in html
        assert 'data-lucide="shield-check"' in html

    def test_renders_value_highlight(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {}, "layout": {}}
        page_data = {
            "title": "Home",
            "sections": [
                {
                    "type": "value_highlight",
                    "headline": "Our Commitment",
                    "subhead": "Quality first",
                    "body": "We deliver excellence",
                    "primary_cta": {"label": "Get Started", "href": "/start"},
                }
            ],
        }
        ctx = build_site_page_context(sitespec, "/", page_data=page_data)
        html = _render("site/page.html", ctx)

        assert "dz-section-value-highlight" in html
        assert "Our Commitment" in html
        assert "Quality first" in html

    def test_renders_comparison(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {}, "layout": {}}
        page_data = {
            "title": "Plans",
            "sections": [
                {
                    "type": "comparison",
                    "headline": "Plans",
                    "columns": [
                        {"label": "Free", "highlighted": False},
                        {"label": "Pro", "highlighted": True},
                    ],
                    "items": [
                        {"feature": "Users", "cells": ["5", "Unlimited"]},
                    ],
                }
            ],
        }
        ctx = build_site_page_context(sitespec, "/", page_data=page_data)
        html = _render("site/page.html", ctx)

        assert "dz-section-comparison" in html
        assert "dz-comparison-highlighted" in html
        assert "Free" in html
        assert "Unlimited" in html

    def test_renders_logo_cloud(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {}, "layout": {}}
        page_data = {
            "title": "Home",
            "sections": [
                {
                    "type": "logo_cloud",
                    "headline": "Trusted By",
                    "items": [
                        {"name": "Acme", "src": "/logos/acme.png", "href": "https://acme.com"},
                    ],
                }
            ],
        }
        ctx = build_site_page_context(sitespec, "/", page_data=page_data)
        html = _render("site/page.html", ctx)

        assert "dz-section-logo-cloud" in html
        assert "Acme" in html

    def test_renders_multiple_sections(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {}, "layout": {}}
        page_data = {
            "title": "Home",
            "sections": [
                {"type": "hero", "headline": "Hello"},
                {"type": "cta", "headline": "Sign up now"},
                {"type": "stats", "items": [{"value": "99%", "label": "Uptime"}]},
            ],
        }
        ctx = build_site_page_context(sitespec, "/", page_data=page_data)
        html = _render("site/page.html", ctx)

        assert "Hello" in html
        assert "Sign up now" in html
        assert "99%" in html

    def test_empty_sections_shows_loading(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {}, "layout": {}}
        ctx = build_site_page_context(sitespec, "/")
        html = _render("site/page.html", ctx)

        assert "dz-loading" in html

    def test_generic_fallback_for_unknown_type(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {}, "layout": {}}
        page_data = {
            "title": "Home",
            "sections": [
                {"type": "unknown_type", "headline": "Mystery Section"},
            ],
        }
        ctx = build_site_page_context(sitespec, "/", page_data=page_data)
        html = _render("site/page.html", ctx)

        assert "dz-section-unknown-type" in html
        assert "Mystery Section" in html

    def test_nav_and_footer_present(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {
            "brand": {"product_name": "NavTest"},
            "layout": {
                "nav": {"public": [{"label": "About", "href": "/about"}]},
                "footer": {
                    "columns": [{"title": "Links", "links": [{"label": "Home", "href": "/"}]}]
                },
            },
        }
        ctx = build_site_page_context(sitespec, "/")
        html = _render("site/page.html", ctx)

        assert "NavTest" in html
        assert "About" in html
        assert "dz-site-footer" in html
        assert "Links" in html

    def test_og_meta_present(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {"product_name": "App"}, "layout": {}}
        page_data = {
            "title": "Home",
            "sections": [{"type": "hero", "headline": "H", "subhead": "S"}],
        }
        ctx = build_site_page_context(sitespec, "/", page_data=page_data)
        html = _render("site/page.html", ctx)

        assert "og:title" in html
        assert "og:description" in html

    def test_custom_css_included(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {}, "layout": {}}
        ctx = build_site_page_context(sitespec, "/", custom_css=True)
        html = _render("site/page.html", ctx)

        assert "/static/css/custom.css" in html

    def test_custom_css_excluded_by_default(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {}, "layout": {}}
        ctx = build_site_page_context(sitespec, "/")
        html = _render("site/page.html", ctx)

        assert "/static/css/custom.css" not in html


# =========================================================================
# 404 Template Tests
# =========================================================================


class TestSite404Template:
    """Tests for site/404.html template."""

    def test_404_renders(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_404_context

        ctx = build_site_404_context({"brand": {"product_name": "TestApp"}, "layout": {}})
        html = _render("site/404.html", ctx)

        assert "404" in html
        assert "TestApp" in html
        assert "Go Home" in html
        assert "dz-404-headline" in html


# =========================================================================
# Auth Template Tests
# =========================================================================


class TestAuthTemplates:
    """Tests for auth page templates."""

    def test_login_page(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_auth_context

        ctx = build_site_auth_context({"brand": {"product_name": "TestApp"}}, "login")
        html = _render("site/auth/login.html", ctx)

        assert "Sign In" in html
        assert "TestApp" in html
        assert "/auth/login" in html
        assert "Forgot password?" in html
        assert "Create an account" in html

    def test_signup_page(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_auth_context

        ctx = build_site_auth_context({"brand": {"product_name": "TestApp"}}, "signup")
        html = _render("site/auth/signup.html", ctx)

        assert "Create Account" in html
        assert "Full Name" in html
        assert "Confirm Password" in html
        assert "Sign in instead" in html
        assert "Forgot password?" not in html

    def test_forgot_password_page(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_auth_context

        ctx = build_site_auth_context({"brand": {"product_name": "TestApp"}}, "forgot_password")
        html = _render("site/auth/forgot_password.html", ctx)

        assert "Reset Password" in html
        assert "/auth/forgot-password" in html
        assert "Back to sign in" in html

    def test_reset_password_page(self) -> None:
        from dazzle_ui.runtime.site_context import build_site_auth_context

        ctx = build_site_auth_context({"brand": {"product_name": "TestApp"}}, "reset_password")
        html = _render("site/auth/reset_password.html", ctx)

        assert "Set New Password" in html
        assert "/auth/reset-password" in html
        assert "new_password" in html
        assert "confirm_password" in html
