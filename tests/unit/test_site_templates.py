"""Tests for Jinja2 site page rendering.

Tests cover:
- Section template rendering (hero, features, cta, faq, etc.)
- Auth page rendering (login, signup, forgot/reset password)
- 404 page rendering
- Context builder functions
- Backward-compatible shims in site_renderer.py
"""

from typing import Any

import pytest


def _render(template: str, context_model: Any) -> str:
    """Helper to render a site template with a context model."""
    from dazzle.ui.runtime.template_renderer import render_site_page

    return render_site_page(template, context_model)


# =========================================================================
# Context Builder Tests
# =========================================================================


class TestBuildSitePageContext:
    """Tests for build_site_page_context()."""

    def test_basic_context(self) -> None:
        from dazzle.ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {
            "brand": {"product_name": "TestApp"},
            "layout": {"nav": {}, "footer": {}},
        }
        ctx = build_site_page_context(sitespec, "/")
        assert ctx.product_name == "TestApp"
        assert ctx.current_route == "/"
        assert ctx.sections == []

    def test_null_brand_fields_do_not_crash_root_page(self) -> None:
        """A sitespec with `company_legal_name: null` (present-but-None) must not 500.

        Regression for #1423: sitespec normalization injects brand keys with null
        values; `brand.get("company_legal_name", product_name)` then returns that
        None (not the default), and `str.replace(..., None)` raised TypeError on the
        root page — uvicorn bound, but `GET /` 500'd, which the managed-server health
        poll (`<500`) read as "never bound" → the llm_ticket_classifier GUIDE_WALK CI
        timeout. `or`-fallbacks make null fields degrade to the product name.
        """
        from dazzle.ui.runtime.site_context import (
            _build_copyright_text,
            build_site_page_context,
        )

        # present-but-null on BOTH brand fields — the exact runtime shape.
        text = _build_copyright_text(
            {"copyright": "{{company_legal_name}} {{year}}"},
            {"product_name": "AI Ticket Classifier", "company_legal_name": None},
        )
        assert "{{company_legal_name}}" not in text
        assert "AI Ticket Classifier" in text  # null legal name → product name

        # product_name itself null → falls back to "My App", no crash.
        text2 = _build_copyright_text(
            {"copyright": "© {{company_legal_name}}"},
            {"product_name": None, "company_legal_name": None},
        )
        assert "My App" in text2

        # full builder path with the null field present — must not raise.
        sitespec_null: dict[str, Any] = {
            "brand": {"product_name": "AI Ticket Classifier", "company_legal_name": None},
            "layout": {"nav": {}, "footer": {"copyright": "© {{company_legal_name}}"}},
        }
        ctx = build_site_page_context(sitespec_null, "/")
        assert ctx.product_name == "AI Ticket Classifier"

    def test_nav_items_extracted(self) -> None:
        from dazzle.ui.runtime.site_context import build_site_page_context

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
        from dazzle.ui.runtime.site_context import build_site_page_context

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
        from dazzle.ui.runtime.site_context import build_site_page_context

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
        from dazzle.ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {}, "layout": {}}
        page_data = {
            "title": "Home",
            "sections": [{"type": "feature_grid", "items": []}],
        }
        ctx = build_site_page_context(sitespec, "/", page_data=page_data)
        assert ctx.sections[0]["type"] == "features"

    def test_og_meta_from_hero(self) -> None:
        from dazzle.ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {"product_name": "App"}, "layout": {}}
        page_data = {
            "title": "Home",
            "sections": [{"type": "hero", "headline": "Hello", "subhead": "World"}],
        }
        ctx = build_site_page_context(sitespec, "/", page_data=page_data)
        assert ctx.og_meta is not None
        assert ctx.og_meta.description == "World"

    def test_custom_css_flag(self) -> None:
        from dazzle.ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {}, "layout": {}}
        ctx = build_site_page_context(sitespec, "/", custom_css=True)
        assert ctx.custom_css is True

    def test_auto_alternate_backgrounds(self) -> None:
        from dazzle.ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {
            "brand": {},
            "layout": {"section_backgrounds": "auto-alternate"},
        }
        page_data = {
            "title": "Home",
            "sections": [
                {"type": "hero", "headline": "Hello"},
                {"type": "features", "items": []},
                {"type": "cta", "headline": "Go"},
            ],
        }
        ctx = build_site_page_context(sitespec, "/", page_data=page_data)
        assert ctx.sections[0]["background"] == "default"
        assert ctx.sections[1]["background"] == "alt"
        assert ctx.sections[2]["background"] == "default"

    def test_explicit_background_preserved(self) -> None:
        from dazzle.ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {
            "brand": {},
            "layout": {"section_backgrounds": "auto-alternate"},
        }
        page_data = {
            "title": "Home",
            "sections": [
                {"type": "hero", "headline": "Hello"},
                {"type": "features", "background": "primary", "items": []},
                {"type": "cta", "headline": "Go"},
            ],
        }
        ctx = build_site_page_context(sitespec, "/", page_data=page_data)
        # Explicit background should be preserved, not overwritten
        assert ctx.sections[1]["background"] == "primary"

    @pytest.mark.skip(
        reason="v0.67.69 retired site/inner_only.html — background-class "
        "rendering is now tested via the typed `_render_site_inner_html` "
        "in tests/unit/test_site_routes_no_duplicate_registration.py + "
        "the typed-section-builder tests."
    )
    def test_background_class_in_rendered_html(self) -> None: ...


# TestBuildSiteAuthContext class retired in Phase 1.D.2 (v0.67.37).
# `build_site_auth_context` is gone; auth-page coverage now lives in
# the typed-view test suites under `tests/unit/test_auth_views_*.py`
# and `tests/unit/test_two_factor_views.py`.


# TestBuildSite404Context removed in Phase 2.A (v0.67.34) —
# `build_site_404_context` is gone. Marketing-site 404 coverage now
# lives in `tests/unit/test_error_views.py`.


# =========================================================================
# Template Rendering Tests
# =========================================================================


@pytest.mark.skip(
    reason="v0.67.69 retired site/sections/*.html, site/inner_only.html, and "
    "site/includes/* Jinja templates — the marketing-page render now goes "
    "through `_render_site_inner_html` (site_routes.py) using stdlib "
    "html.escape. Section-by-section parity tests are obsolete."
)
class TestSitePageTemplate:
    """Tests for site/page.html template rendering."""

    def test_renders_hero_section(self) -> None:
        from dazzle.ui.runtime.site_context import build_site_page_context

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
        html = _render("site/inner_only.html", ctx)

        assert "Welcome to TestApp" in html
        assert "The best app ever" in html
        assert "Get Started" in html
        assert "/signup" in html
        assert "dz-section-hero" in html

    def test_renders_features_section(self) -> None:
        from dazzle.ui.runtime.site_context import build_site_page_context

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
        html = _render("site/inner_only.html", ctx)

        assert "Fast" in html
        assert "Lightning speed" in html
        assert 'data-lucide="zap"' in html
        assert "Secure" in html

    def test_renders_faq_section(self) -> None:
        from dazzle.ui.runtime.site_context import build_site_page_context

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
        html = _render("site/inner_only.html", ctx)

        assert "How much?" in html
        assert "Free forever." in html
        # Cycle 250 — FAQ migrated from DaisyUI collapse to design tokens
        assert "dz-faq-list" in html

    def test_renders_pricing_section(self) -> None:
        from dazzle.ui.runtime.site_context import build_site_page_context

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
        html = _render("site/inner_only.html", ctx)

        assert "Pro" in html
        assert "$29" in html
        assert "Unlimited users" in html
        assert "Buy Now" in html
        assert "dz-pricing-highlighted" in html
        # Cycle 250 — btn btn-secondary migrated to design tokens
        assert "bg-[hsl(var(--background))]" in html or "Buy Now" in html

    def test_renders_card_grid_section(self) -> None:
        from dazzle.ui.runtime.site_context import build_site_page_context

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
        html = _render("site/inner_only.html", ctx)

        assert "dz-section-card-grid" in html
        assert "Consulting" in html
        assert 'data-lucide="briefcase"' in html
        assert "Learn More" in html

    def test_renders_split_content_reversed(self) -> None:
        from dazzle.ui.runtime.site_context import build_site_page_context

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
        html = _render("site/inner_only.html", ctx)

        assert "dz-split--reversed" in html
        assert "Our Story" in html
        assert "/img/team.webp" in html

    def test_renders_misc_sections(self) -> None:
        """Combined: trust_bar, value_highlight, comparison, logo_cloud each render
        the canonical class + content."""
        from dazzle.ui.runtime.site_context import build_site_page_context

        cases: list[tuple[dict[str, Any], list[str]]] = [
            # trust_bar
            (
                {
                    "type": "trust_bar",
                    "items": [
                        {"text": "ICAEW Certified", "icon": "shield-check"},
                        {"text": "GDPR Compliant", "icon": "lock"},
                    ],
                },
                ["dz-section-trust-bar", "ICAEW Certified", 'data-lucide="shield-check"'],
            ),
            # value_highlight
            (
                {
                    "type": "value_highlight",
                    "headline": "Our Commitment",
                    "subhead": "Quality first",
                    "body": "We deliver excellence",
                    "primary_cta": {"label": "Get Started", "href": "/start"},
                },
                ["dz-section-value-highlight", "Our Commitment", "Quality first"],
            ),
            # comparison
            (
                {
                    "type": "comparison",
                    "headline": "Plans",
                    "columns": [
                        {"label": "Free", "highlighted": False},
                        {"label": "Pro", "highlighted": True},
                    ],
                    "items": [{"feature": "Users", "cells": ["5", "Unlimited"]}],
                },
                ["dz-section-comparison", "dz-comparison-highlighted", "Free", "Unlimited"],
            ),
            # logo_cloud
            (
                {
                    "type": "logo_cloud",
                    "headline": "Trusted By",
                    "items": [
                        {"name": "Acme", "src": "/logos/acme.png", "href": "https://acme.com"},
                    ],
                },
                ["dz-section-logo-cloud", "Acme"],
            ),
        ]
        sitespec: dict[str, Any] = {"brand": {}, "layout": {}}
        for section, expected in cases:
            page_data = {"title": "X", "sections": [section]}
            ctx = build_site_page_context(sitespec, "/", page_data=page_data)
            html = _render("site/inner_only.html", ctx)
            for needle in expected:
                assert needle in html, f"missing {needle!r} in section type={section['type']}"

    def test_renders_multiple_sections(self) -> None:
        from dazzle.ui.runtime.site_context import build_site_page_context

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
        html = _render("site/inner_only.html", ctx)

        assert "Hello" in html
        assert "Sign up now" in html
        assert "99%" in html

    def test_empty_sections_shows_loading(self) -> None:
        from dazzle.ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {}, "layout": {}}
        ctx = build_site_page_context(sitespec, "/")
        html = _render("site/inner_only.html", ctx)

        assert "dz-loading" in html

    def test_generic_fallback_for_unknown_type(self) -> None:
        from dazzle.ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {}, "layout": {}}
        page_data = {
            "title": "Home",
            "sections": [
                {"type": "unknown_type", "headline": "Mystery Section"},
            ],
        }
        ctx = build_site_page_context(sitespec, "/", page_data=page_data)
        html = _render("site/inner_only.html", ctx)

        assert "dz-section-unknown-type" in html
        assert "Mystery Section" in html

    def test_nav_and_footer_present(self) -> None:
        from dazzle.ui.runtime.site_context import build_site_page_context

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
        html = _render("site/inner_only.html", ctx)

        assert "NavTest" in html
        assert "About" in html
        assert "dz-site-footer" in html
        assert "Links" in html

    # test_og_meta_present and test_custom_css_included were retired
    # in Phase 4 chrome-flag flip (v0.67.43). Both pinned `<head>`
    # content emitted by the legacy `site/page.html` chrome, which no
    # longer exists — the typed Page wrapper now provides the head.
    # OG meta coverage moved to:
    #   - tests/unit/test_page_og_meta.py (Page primitive level)
    #   - tests/integration/test_sitespec_chrome_gate_flip.py
    #     (chrome=on OG tag emission end-to-end)
    # Custom-CSS override is exercised via build_site_page_context's
    # `custom_css` flag and `app.state.fragment_chrome_css_links` —
    # both covered by other integration tests.

    def test_custom_css_excluded_by_default(self) -> None:
        from dazzle.ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {}, "layout": {}}
        ctx = build_site_page_context(sitespec, "/")
        html = _render("site/inner_only.html", ctx)

        assert "/static/css/custom.css" not in html

    def test_renders_team_section(self) -> None:
        from dazzle.ui.runtime.site_context import build_site_page_context

        sitespec: dict[str, Any] = {"brand": {"product_name": "App"}, "layout": {}}
        page_data = {
            "title": "About",
            "sections": [
                {
                    "type": "team",
                    "headline": "The Team",
                    "items": [
                        {
                            "name": "Jane Doe",
                            "role": "CEO",
                            "bio": "Leads the company.",
                            "links": [{"type": "linkedin", "href": "https://linkedin.com/in/jane"}],
                        },
                        {"name": "Bob Smith", "role": "CTO"},
                    ],
                }
            ],
        }
        ctx = build_site_page_context(sitespec, "/about", page_data=page_data)
        html = _render("site/inner_only.html", ctx)

        assert "dz-section-team" in html
        assert "The Team" in html
        assert "Jane Doe" in html
        assert "CEO" in html
        assert "Leads the company." in html
        assert "linkedin.com/in/jane" in html
        assert "Bob Smith" in html
        # Initials fallback for members without images
        assert "JD" in html  # Jane Doe initials
        assert "BS" in html  # Bob Smith initials


# Site 404 template retired in Phase 2.A (v0.67.34) — coverage moved
# to `tests/unit/test_error_views.py`.


# =========================================================================
# Auth Template Tests
# =========================================================================


# Auth page templates deleted in Phase 1.E (v0.67.33) — login, signup,
# forgot_password, and reset_password are now typed-Fragment views.
# Coverage moved to tests/unit/test_auth_views_*.py and
# tests/integration/test_auth_*_chrome_gate.py.
