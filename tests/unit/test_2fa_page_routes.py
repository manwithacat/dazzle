"""
Tests for 2FA page routes (#831).

Verifies that /2fa/setup, /2fa/settings, and /2fa/challenge are registered
and serve their templates correctly; that /2fa/setup and /2fa/settings
redirect unauthenticated users to /login; and that /2fa/challenge accepts
a session token via the ``?session=`` query param.
"""

from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from starlette.testclient import TestClient

from dazzle.http.runtime.site_routes import create_auth_page_routes

SITESPEC: dict[str, Any] = {"brand": {"product_name": "TestApp"}}


class TestTwoFactorPageContextBuilder:
    """The site-context builder must understand the three new page types."""

    def test_setup_view_renders_with_product_name(self) -> None:
        """Phase 1.D.2 (v0.67.37): setup is a typed-Fragment view."""
        from dazzle.http.runtime.auth.two_factor_views import build_2fa_setup_view
        from dazzle.render.fragment.renderer import FragmentRenderer

        html = FragmentRenderer().render(build_2fa_setup_view(product_name="TestApp"))
        assert "Set Up 2FA" in html
        assert "TestApp" in html
        # External JS reference, not inline script.
        assert "/static/js/dz-2fa-setup.js" in html

    def test_settings_view_renders_with_product_name(self) -> None:
        """Phase 1.D.2 (v0.67.37): settings is a typed-Fragment view."""
        from dazzle.http.runtime.auth.two_factor_views import (
            build_2fa_settings_view,
        )
        from dazzle.render.fragment.renderer import FragmentRenderer

        html = FragmentRenderer().render(build_2fa_settings_view(product_name="TestApp"))
        assert "2FA Settings" in html
        assert "TestApp" in html
        assert "/static/js/dz-2fa-settings.js" in html

    def test_challenge_view_carries_session_token(self) -> None:
        """Phase 1.D.1 (v0.67.35): challenge surface is now a typed-
        Fragment view, not a Jinja template. The token threads
        through `build_2fa_challenge_view` rather than the legacy
        SiteAuthContext."""
        from dazzle.http.runtime.auth.two_factor_views import (
            build_2fa_challenge_view,
        )
        from dazzle.render.fragment.renderer import FragmentRenderer

        page = build_2fa_challenge_view(
            product_name="TestApp",
            session_token="abc-123",
            mode="totp",
            email_otp_enabled=True,
        )
        html = FragmentRenderer().render(page)
        assert "abc-123" in html
        # Mode-switch link to email-otp is rendered when that method is enabled.
        assert "mode=email_otp" in html


class TestTwoFactorRoutesWithoutAuth:
    """Without an auth callable wired, setup/settings fall through (dev mode)."""

    def _client(self) -> TestClient:
        router = create_auth_page_routes(SITESPEC)
        app = FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_setup_route_returns_200(self) -> None:
        resp = self._client().get("/2fa/setup")
        assert resp.status_code == 200
        assert "Set Up 2FA" in resp.text

    def test_settings_route_returns_200(self) -> None:
        resp = self._client().get("/2fa/settings")
        assert resp.status_code == 200
        assert "2FA Settings" in resp.text

    def test_challenge_route_returns_200(self) -> None:
        resp = self._client().get("/2fa/challenge?session=xyz-789")
        assert resp.status_code == 200
        assert "xyz-789" in resp.text
        assert "Verify" in resp.text

    def test_challenge_route_without_session_still_renders(self) -> None:
        resp = self._client().get("/2fa/challenge")
        assert resp.status_code == 200
        # Empty session_token is still rendered into the hidden input
        assert 'name="session_token"' in resp.text


class TestTwoFactorAuthGuards:
    """setup/settings redirect unauthenticated users; challenge is public."""

    def _client(self, *, authenticated: bool) -> TestClient:
        def get_auth_context(_request: Any) -> SimpleNamespace:
            return SimpleNamespace(is_authenticated=authenticated, roles=[])

        router = create_auth_page_routes(SITESPEC, get_auth_context=get_auth_context)
        app = FastAPI()
        app.include_router(router)
        # Also mount /login so redirects don't 404
        from dazzle.http.runtime.site_routes import create_auth_page_routes as _mk

        app.include_router(_mk(SITESPEC))
        return TestClient(app)

    def test_setup_redirects_when_unauthenticated(self) -> None:
        resp = self._client(authenticated=False).get("/2fa/setup", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/login?next=/2fa/setup"

    def test_settings_redirects_when_unauthenticated(self) -> None:
        resp = self._client(authenticated=False).get("/2fa/settings", follow_redirects=False)
        assert resp.status_code == 302
        assert resp.headers["location"] == "/login?next=/2fa/settings"

    def test_setup_renders_when_authenticated(self) -> None:
        resp = self._client(authenticated=True).get("/2fa/setup")
        assert resp.status_code == 200
        assert "Set Up 2FA" in resp.text

    def test_settings_renders_when_authenticated(self) -> None:
        resp = self._client(authenticated=True).get("/2fa/settings")
        assert resp.status_code == 200
        assert "2FA Settings" in resp.text

    def test_challenge_is_public_even_with_auth_wired(self) -> None:
        """The mid-login challenge must remain reachable pre-authentication."""
        resp = self._client(authenticated=False).get("/2fa/challenge?session=mid-login")
        assert resp.status_code == 200
        assert "mid-login" in resp.text

    def test_setup_redirects_when_auth_callable_raises(self) -> None:
        """A broken auth callable must fail closed (redirect, not render)."""

        def raising_auth(_request: Any) -> Any:
            raise RuntimeError("auth backend unavailable")

        router = create_auth_page_routes(SITESPEC, get_auth_context=raising_auth)
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        resp = client.get("/2fa/setup", follow_redirects=False)
        assert resp.status_code == 302
