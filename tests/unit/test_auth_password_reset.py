"""
Unit tests for password reset flow and SSR rendering.

Tests cover:
- Password reset token creation and validation (e2e — requires PostgreSQL)
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
def auth_store() -> AuthStore:
    """Create an AuthStore backed by a PostgreSQL test database."""
    return AuthStore(database_url="postgresql://mock/test")


@pytest.fixture
def test_user(auth_store: AuthStore):
    """Create a test user and return the UserRecord."""
    return auth_store.create_user(
        email="test@example.com",
        password="securepass123",
        username="Test User",
    )


@pytest.mark.e2e
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


@pytest.mark.e2e
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
    """Test server-side rendering of sitespec pages via Jinja2 templates."""

    def test_render_site_page_html_with_page_data(self) -> None:
        """Test that site page SSR produces content when page_data is provided."""
        from dazzle_ui.runtime.site_context import build_site_page_context
        from dazzle_ui.runtime.template_renderer import render_site_page

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
        ctx = build_site_page_context(sitespec, "/", page_data=page_data)
        html = render_site_page("site/page.html", ctx)

        # SSR content should be present
        assert "Welcome" in html
        assert "Great app" in html
        # OG meta should be present
        assert "og:title" in html

    def test_render_site_page_html_without_page_data(self) -> None:
        """Test that site page SSR renders even without page_data."""
        from dazzle_ui.runtime.site_context import build_site_page_context
        from dazzle_ui.runtime.template_renderer import render_site_page

        sitespec = {
            "brand": {"product_name": "TestApp"},
            "layout": {"nav": {}, "footer": {}},
        }
        ctx = build_site_page_context(sitespec, "/")
        html = render_site_page("site/page.html", ctx)
        # Should render a valid page (no loading state — always SSR now)
        assert "TestApp" in html
        assert "<!DOCTYPE html>" in html.lower() or "<html" in html.lower()


class TestOGMetaTags:
    """Test Open Graph meta tag generation via Jinja2 templates."""

    def test_og_meta_in_rendered_page(self) -> None:
        """Test OG meta tags appear in rendered page HTML."""
        from dazzle_ui.runtime.site_context import build_site_page_context
        from dazzle_ui.runtime.template_renderer import render_site_page

        sitespec = {
            "brand": {"product_name": "MyApp"},
            "layout": {"nav": {}, "footer": {}},
        }
        page_data = {
            "title": "Home",
            "sections": [
                {"type": "hero", "headline": "Welcome", "subhead": "The best app"},
            ],
        }
        ctx = build_site_page_context(sitespec, "/", page_data=page_data)
        html = render_site_page("site/page.html", ctx)
        assert "og:title" in html
        assert "og:type" in html


class TestAuthPageRenderers:
    """Test auth page renderers (forgot-password, reset-password)."""

    def test_forgot_password_page(self) -> None:
        """Test forgot-password page renders correctly."""
        from dazzle_ui.runtime.site_context import build_site_auth_context
        from dazzle_ui.runtime.template_renderer import render_site_page

        sitespec = {"brand": {"product_name": "TestApp"}}
        ctx = build_site_auth_context(sitespec, "forgot_password")
        html = render_site_page("site/auth/forgot_password.html", ctx)

        assert "Reset Password" in html
        assert "/auth/forgot-password" in html
        assert "TestApp" in html
        assert "Back to sign in" in html

    def test_reset_password_page(self) -> None:
        """Test reset-password page renders correctly."""
        from dazzle_ui.runtime.site_context import build_site_auth_context
        from dazzle_ui.runtime.template_renderer import render_site_page

        sitespec = {"brand": {"product_name": "TestApp"}}
        ctx = build_site_auth_context(sitespec, "reset_password")
        html = render_site_page("site/auth/reset_password.html", ctx)

        assert "Set New Password" in html
        assert "/auth/reset-password" in html
        assert "new_password" in html
        assert "confirm_password" in html

    def test_login_page_has_forgot_password_link(self) -> None:
        """Test that login page includes forgot-password link."""
        from dazzle_ui.runtime.site_context import build_site_auth_context
        from dazzle_ui.runtime.template_renderer import render_site_page

        sitespec = {"brand": {"product_name": "TestApp"}}
        ctx = build_site_auth_context(sitespec, "login")
        html = render_site_page("site/auth/login.html", ctx)

        assert "Forgot password?" in html
        assert "/forgot-password" in html

    def test_signup_page_no_forgot_password_link(self) -> None:
        """Test that signup page does NOT show forgot-password link."""
        from dazzle_ui.runtime.site_context import build_site_auth_context
        from dazzle_ui.runtime.template_renderer import render_site_page

        sitespec = {"brand": {"product_name": "TestApp"}}
        ctx = build_site_auth_context(sitespec, "signup")
        html = render_site_page("site/auth/signup.html", ctx)

        assert "Forgot password?" not in html


class TestCustomCssOverride:
    """Tests for project-level custom CSS override (#187)."""

    def test_get_shared_head_html_includes_custom_css_when_enabled(self) -> None:
        """custom_css=True adds a link to /static/css/custom.css."""
        from dazzle_ui.runtime.site_renderer import get_shared_head_html

        html = get_shared_head_html("Test Page", custom_css=True)
        assert "/static/css/custom.css" in html
        # Must appear after dazzle.css
        dazzle_pos = html.index("/styles/dazzle.css")
        custom_pos = html.index("/static/css/custom.css")
        assert custom_pos > dazzle_pos

    def test_get_shared_head_html_no_custom_css_by_default(self) -> None:
        """custom_css defaults to False — no custom.css link."""
        from dazzle_ui.runtime.site_renderer import get_shared_head_html

        html = get_shared_head_html("Test Page")
        assert "/static/css/custom.css" not in html

    def test_render_site_page_passes_custom_css(self) -> None:
        """Site page context propagates custom_css to head."""
        from dazzle_ui.runtime.site_context import build_site_page_context
        from dazzle_ui.runtime.template_renderer import render_site_page

        sitespec: dict = {"brand": {"product_name": "TestApp"}, "layout": {}}
        ctx = build_site_page_context(sitespec, "/", custom_css=True)
        html = render_site_page("site/page.html", ctx)
        assert "/static/css/custom.css" in html

    def test_render_auth_page_passes_custom_css(self) -> None:
        """Auth page context propagates custom_css to head."""
        from dazzle_ui.runtime.site_context import build_site_auth_context
        from dazzle_ui.runtime.template_renderer import render_site_page

        sitespec: dict = {"brand": {"product_name": "TestApp"}}
        ctx = build_site_auth_context(sitespec, "login", custom_css=True)
        html = render_site_page("site/auth/login.html", ctx)
        assert "/static/css/custom.css" in html

    def test_render_404_page_passes_custom_css(self) -> None:
        """404 page context propagates custom_css to head."""
        from dazzle_ui.runtime.site_context import build_site_404_context
        from dazzle_ui.runtime.template_renderer import render_site_page

        sitespec: dict = {"brand": {"product_name": "TestApp"}, "layout": {}}
        ctx = build_site_404_context(sitespec, custom_css=True)
        html = render_site_page("site/404.html", ctx)
        assert "/static/css/custom.css" in html

    def test_render_forgot_password_passes_custom_css(self) -> None:
        """Forgot password context propagates custom_css to head."""
        from dazzle_ui.runtime.site_context import build_site_auth_context
        from dazzle_ui.runtime.template_renderer import render_site_page

        sitespec: dict = {"brand": {"product_name": "TestApp"}}
        ctx = build_site_auth_context(sitespec, "forgot_password", custom_css=True)
        html = render_site_page("site/auth/forgot_password.html", ctx)
        assert "/static/css/custom.css" in html

    def test_render_reset_password_passes_custom_css(self) -> None:
        """Reset password context propagates custom_css to head."""
        from dazzle_ui.runtime.site_context import build_site_auth_context
        from dazzle_ui.runtime.template_renderer import render_site_page

        sitespec: dict = {"brand": {"product_name": "TestApp"}}
        ctx = build_site_auth_context(sitespec, "reset_password", custom_css=True)
        html = render_site_page("site/auth/reset_password.html", ctx)
        assert "/static/css/custom.css" in html

    def test_create_site_page_routes_detects_custom_css(self, tmp_path: Path) -> None:
        """create_site_page_routes enables custom_css when file exists."""

        from dazzle_back.runtime.site_routes import create_site_page_routes

        # Create the custom.css file
        css_dir = tmp_path / "static" / "css"
        css_dir.mkdir(parents=True)
        (css_dir / "custom.css").write_text("body { color: red; }")

        sitespec: dict = {
            "brand": {"product_name": "TestApp"},
            "layout": {},
            "pages": [{"route": "/", "type": "landing", "sections": []}],
            "legal": {},
        }

        router = create_site_page_routes(sitespec, project_root=tmp_path)

        # Inspect the route handler to verify custom_css is passed
        # Find the serve_page route and call it
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        app = FastAPI()
        # Need dazzle.css route to exist
        app.include_router(router)
        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "/static/css/custom.css" in resp.text

    def test_create_site_page_routes_no_custom_css_without_file(self, tmp_path: Path) -> None:
        """create_site_page_routes omits custom_css when file doesn't exist."""
        from dazzle_back.runtime.site_routes import create_site_page_routes

        sitespec: dict = {
            "brand": {"product_name": "TestApp"},
            "layout": {},
            "pages": [{"route": "/", "type": "landing", "sections": []}],
            "legal": {},
        }

        router = create_site_page_routes(sitespec, project_root=tmp_path)

        from fastapi import FastAPI
        from starlette.testclient import TestClient

        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.get("/")
        assert resp.status_code == 200
        assert "/static/css/custom.css" not in resp.text
