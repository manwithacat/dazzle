"""
Unit tests for password reset flow and SSR rendering.

Tests cover:
- Password reset token creation and validation (e2e — requires PostgreSQL)
- Forgot-password / reset-password endpoints (via auth routes)
- Server-side rendering of sitespec pages
- OG meta tag generation
- Auth page rendering (forgot-password link, page renderers)
"""

import time
from datetime import timedelta
from pathlib import Path

import pytest

from dazzle.http.runtime.auth import AuthStore
from tests.unit._auth_pg import AUTH_TABLES, fresh_url


@pytest.fixture
def auth_store() -> AuthStore:
    """An AuthStore backed by a real PostgreSQL test database, clean per test."""
    return AuthStore(database_url=fresh_url(*AUTH_TABLES))


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
        from dazzle.http.runtime.auth import AuthMiddleware

        middleware = AuthMiddleware(auth_store)
        assert middleware.is_excluded_path("/auth/forgot-password")

    def test_reset_password_excluded(self, auth_store: AuthStore) -> None:
        """Test that /auth/reset-password is in the middleware exclude list."""
        from dazzle.http.runtime.auth import AuthMiddleware

        middleware = AuthMiddleware(auth_store)
        assert middleware.is_excluded_path("/auth/reset-password")


# TestSiteRendererSSR + TestOGMetaTags retired in Phase 4 chrome-flag
# flip (v0.67.43). Both rendered `site/page.html` directly to assert
# `<!DOCTYPE html>` / `og:title` lived in the rendered output — that
# chrome moved to the typed Page primitive when `site/page.html` was
# retired. Coverage moved to:
#   - tests/unit/test_page_og_meta.py — Page.og_meta + property=meta render
#   - tests/integration/test_sitespec_chrome_gate_flip.py — chrome=on
#     OG tag emission end-to-end + custom.css threading


# Auth page Jinja renderers retired in Phase 1.E (v0.67.33).
# login / signup / forgot_password / reset_password now render as
# typed-Fragment Pages. Equivalent coverage lives in:
#   tests/unit/test_auth_views_login_magic_link.py
#   tests/unit/test_auth_views_signup_magic_link.py
#   tests/unit/test_auth_views_password_mode.py
#   tests/unit/test_auth_views_password_reset.py
# and the corresponding tests/integration/test_auth_*_chrome_gate.py
# integration suites.


class TestCustomCssOverride:
    """Tests for project-level custom CSS override (#187)."""

    def test_get_shared_head_html_includes_custom_css_when_enabled(self) -> None:
        """custom_css=True adds a link to /static/css/custom.css."""
        from dazzle.page.runtime.site_renderer import get_shared_head_html

        html = get_shared_head_html("Test Page", custom_css=True)
        assert "/static/css/custom.css" in html
        # Must appear after dazzle.css
        dazzle_pos = html.index("/styles/dazzle.css")
        custom_pos = html.index("/static/css/custom.css")
        assert custom_pos > dazzle_pos

    def test_get_shared_head_html_no_custom_css_by_default(self) -> None:
        """custom_css defaults to False — no custom.css link."""
        from dazzle.page.runtime.site_renderer import get_shared_head_html

        html = get_shared_head_html("Test Page")
        assert "/static/css/custom.css" not in html

    # test_render_site_page_passes_custom_css retired in Phase 4
    # chrome-flag flip (v0.67.43). Used to render site/page.html
    # directly — that template is gone. The custom.css override now
    # threads through the typed Page wrapper; the end-to-end behavior
    # is covered by test_create_site_page_routes_detects_custom_css
    # below (full TestClient request) plus the chrome-gate parity
    # tests in tests/integration/test_sitespec_chrome_gate_flip.py.

    def test_create_site_page_routes_detects_custom_css(self, tmp_path: Path) -> None:
        """create_site_page_routes enables custom_css when file exists."""

        from dazzle.http.runtime.site_routes import create_site_page_routes

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
        from dazzle.http.runtime.site_routes import create_site_page_routes

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
