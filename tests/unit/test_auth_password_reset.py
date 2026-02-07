"""
Unit tests for password reset flow and SSR rendering.

Tests cover:
- Password reset token creation and validation
- Forgot-password / reset-password endpoints (via auth routes)
- Server-side rendering of sitespec pages
- OG meta tag generation
- Auth page rendering (forgot-password link, page renderers)
"""

from __future__ import annotations

import time
from datetime import timedelta
from pathlib import Path

import pytest

from dazzle_back.runtime.auth import AuthStore


@pytest.fixture
def auth_store(tmp_path: Path) -> AuthStore:
    """Create an AuthStore backed by a temporary SQLite database."""
    return AuthStore(db_path=tmp_path / "auth.db")


@pytest.fixture
def test_user(auth_store: AuthStore):
    """Create a test user and return the UserRecord."""
    return auth_store.create_user(
        email="test@example.com",
        password="securepass123",
        username="Test User",
    )


class TestPasswordResetTokens:
    """Tests for AuthStore password reset token methods."""

    def test_create_token(self, auth_store: AuthStore, test_user) -> None:
        """Test that a reset token is created successfully."""
        token = auth_store.create_password_reset_token(test_user.id)
        assert isinstance(token, str)
        assert len(token) > 20  # URL-safe base64 token

    def test_validate_valid_token(self, auth_store: AuthStore, test_user) -> None:
        """Test that a valid token returns the correct user."""
        token = auth_store.create_password_reset_token(test_user.id)
        user = auth_store.validate_password_reset_token(token)
        assert user is not None
        assert user.email == "test@example.com"

    def test_validate_expired_token(self, auth_store: AuthStore, test_user) -> None:
        """Test that an expired token returns None."""
        token = auth_store.create_password_reset_token(
            test_user.id,
            expires_in=timedelta(seconds=0),
        )
        # Token expires immediately
        time.sleep(0.1)
        user = auth_store.validate_password_reset_token(token)
        assert user is None

    def test_validate_used_token(self, auth_store: AuthStore, test_user) -> None:
        """Test that a consumed token returns None."""
        token = auth_store.create_password_reset_token(test_user.id)
        auth_store.consume_password_reset_token(token)
        user = auth_store.validate_password_reset_token(token)
        assert user is None

    def test_validate_nonexistent_token(self, auth_store: AuthStore) -> None:
        """Test that a bogus token returns None."""
        user = auth_store.validate_password_reset_token("totally-fake-token")
        assert user is None

    def test_consume_token(self, auth_store: AuthStore, test_user) -> None:
        """Test that consuming a token marks it as used."""
        token = auth_store.create_password_reset_token(test_user.id)
        result = auth_store.consume_password_reset_token(token)
        assert result is True

    def test_consume_already_used_token(self, auth_store: AuthStore, test_user) -> None:
        """Test that consuming an already-used token returns False."""
        token = auth_store.create_password_reset_token(test_user.id)
        auth_store.consume_password_reset_token(token)
        result = auth_store.consume_password_reset_token(token)
        assert result is False

    def test_new_token_invalidates_old(self, auth_store: AuthStore, test_user) -> None:
        """Test that creating a new token invalidates existing unused tokens."""
        token1 = auth_store.create_password_reset_token(test_user.id)
        token2 = auth_store.create_password_reset_token(test_user.id)

        # Old token should be invalid
        user1 = auth_store.validate_password_reset_token(token1)
        assert user1 is None

        # New token should be valid
        user2 = auth_store.validate_password_reset_token(token2)
        assert user2 is not None
        assert user2.email == "test@example.com"


class TestAuthMiddlewareExclusions:
    """Test that password reset paths are excluded from auth."""

    def test_forgot_password_excluded(self, auth_store: AuthStore) -> None:
        """Test that /auth/forgot-password is in the middleware exclude list."""
        from dazzle_back.runtime.auth import AuthMiddleware

        middleware = AuthMiddleware(auth_store)
        assert middleware.is_excluded_path("/auth/forgot-password")

    def test_reset_password_excluded(self, auth_store: AuthStore) -> None:
        """Test that /auth/reset-password is in the middleware exclude list."""
        from dazzle_back.runtime.auth import AuthMiddleware

        middleware = AuthMiddleware(auth_store)
        assert middleware.is_excluded_path("/auth/reset-password")


class TestSiteRendererSSR:
    """Test server-side rendering of sitespec pages."""

    def test_ssr_hero_section(self) -> None:
        """Test SSR rendering of a hero section."""
        from dazzle_ui.runtime.site_renderer import _ssr_hero

        section = {
            "type": "hero",
            "headline": "Welcome to MyApp",
            "subhead": "The best app ever",
            "primary_cta": {"label": "Get Started", "href": "/signup"},
        }
        html = _ssr_hero(section)
        assert "Welcome to MyApp" in html
        assert "The best app ever" in html
        assert "Get Started" in html
        assert "/signup" in html
        assert "dz-section-hero" in html

    def test_ssr_features_section(self) -> None:
        """Test SSR rendering of a features section."""
        from dazzle_ui.runtime.site_renderer import _ssr_features

        section = {
            "type": "features",
            "headline": "Features",
            "items": [
                {"title": "Fast", "description": "Lightning speed", "icon": "zap"},
                {"title": "Secure", "description": "Bank-grade security"},
            ],
        }
        html = _ssr_features(section)
        assert "Fast" in html
        assert "Lightning speed" in html
        assert 'data-lucide="zap"' in html
        assert "Secure" in html

    def test_ssr_faq_section(self) -> None:
        """Test SSR rendering of a FAQ section."""
        from dazzle_ui.runtime.site_renderer import _ssr_faq

        section = {
            "type": "faq",
            "headline": "FAQ",
            "items": [
                {"question": "How much?", "answer": "Free forever."},
            ],
        }
        html = _ssr_faq(section)
        assert "How much?" in html
        assert "Free forever." in html
        assert "collapse" in html

    def test_ssr_pricing_section(self) -> None:
        """Test SSR rendering of a pricing section."""
        from dazzle_ui.runtime.site_renderer import _ssr_pricing

        section = {
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
                },
            ],
        }
        html = _ssr_pricing(section)
        assert "Pro" in html
        assert "$29" in html
        assert "Unlimited users" in html
        assert "Buy Now" in html
        assert "border-primary" in html

    def test_render_sections_ssr(self) -> None:
        """Test full SSR rendering of multiple sections."""
        from dazzle_ui.runtime.site_renderer import _render_sections_ssr

        sections = [
            {"type": "hero", "headline": "Hello", "subhead": "World"},
            {"type": "cta", "headline": "Sign up now"},
        ]
        html = _render_sections_ssr(sections)
        assert "Hello" in html
        assert "World" in html
        assert "Sign up now" in html

    def test_render_site_page_html_with_page_data(self) -> None:
        """Test that render_site_page_html produces SSR content when page_data is provided."""
        from dazzle_ui.runtime.site_renderer import render_site_page_html

        sitespec = {
            "brand": {"product_name": "TestApp"},
            "layout": {"nav": {}, "footer": {}},
        }
        page_data = {
            "title": "Home",
            "sections": [
                {"type": "hero", "headline": "Welcome", "subhead": "Great app"},
            ],
        }
        html = render_site_page_html(sitespec, "/", page_data=page_data)

        # SSR content should be present
        assert "Welcome" in html
        assert "Great app" in html
        # OG meta should be present
        assert "og:title" in html
        assert "og:description" in html
        # Loading placeholder should NOT be present
        assert "dz-loading" not in html

    def test_render_site_page_html_without_page_data_shows_loading(self) -> None:
        """Test that render_site_page_html shows loading when no page_data."""
        from dazzle_ui.runtime.site_renderer import render_site_page_html

        sitespec = {
            "brand": {"product_name": "TestApp"},
            "layout": {"nav": {}, "footer": {}},
        }
        html = render_site_page_html(sitespec, "/")
        assert "dz-loading" in html


class TestOGMetaTags:
    """Test Open Graph meta tag generation."""

    def test_og_meta_basic(self) -> None:
        """Test basic OG meta tag generation."""
        from dazzle_ui.runtime.site_renderer import _build_og_meta

        meta = _build_og_meta("MyApp", "Home - MyApp", "The best app", "/")
        assert "og:title" in meta
        assert "og:description" in meta
        assert "The best app" in meta
        assert "Home - MyApp" in meta

    def test_og_meta_escapes_html(self) -> None:
        """Test that OG meta tags escape HTML entities."""
        from dazzle_ui.runtime.site_renderer import _build_og_meta

        meta = _build_og_meta("App", 'Title with "quotes"', "Desc <script>", "/")
        assert "&quot;" in meta
        assert "&lt;script&gt;" in meta


class TestAuthPageRenderers:
    """Test auth page renderers (forgot-password, reset-password)."""

    def test_forgot_password_page(self) -> None:
        """Test forgot-password page renders correctly."""
        from dazzle_ui.runtime.site_renderer import render_forgot_password_page_html

        sitespec = {"brand": {"product_name": "TestApp"}}
        html = render_forgot_password_page_html(sitespec)

        assert "Reset Password" in html
        assert "/auth/forgot-password" in html
        assert "TestApp" in html
        assert "Back to sign in" in html

    def test_reset_password_page(self) -> None:
        """Test reset-password page renders correctly."""
        from dazzle_ui.runtime.site_renderer import render_reset_password_page_html

        sitespec = {"brand": {"product_name": "TestApp"}}
        html = render_reset_password_page_html(sitespec)

        assert "Set New Password" in html
        assert "/auth/reset-password" in html
        assert "new_password" in html
        assert "confirm_password" in html

    def test_login_page_has_forgot_password_link(self) -> None:
        """Test that login page includes forgot-password link."""
        from dazzle_ui.runtime.site_renderer import render_auth_page_html

        sitespec = {"brand": {"product_name": "TestApp"}}
        html = render_auth_page_html(sitespec, "login")

        assert "Forgot password?" in html
        assert "/forgot-password" in html

    def test_signup_page_no_forgot_password_link(self) -> None:
        """Test that signup page does NOT show forgot-password link."""
        from dazzle_ui.runtime.site_renderer import render_auth_page_html

        sitespec = {"brand": {"product_name": "TestApp"}}
        html = render_auth_page_html(sitespec, "signup")

        assert "Forgot password?" not in html
