"""Tests for auth-aware navigation on site pages.

When a user is authenticated, the nav CTA should render "Dashboard" linking
to their workspace.  When unauthenticated, the configured CTA (e.g. "Sign In")
is shown instead.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

# Skip if FastAPI not installed
pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from dazzle_back.runtime.site_routes import create_site_page_routes  # noqa: E402
from dazzle_ui.runtime.site_context import (  # noqa: E402
    _extract_nav_items,
    build_site_page_context,
)
from dazzle_ui.runtime.template_context import SitePageContext  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PERSONA_ROUTES = {
    "customer": "/app/workspaces/customer_dashboard",
    "agent": "/app/workspaces/agent_dashboard",
}


def _minimal_sitespec() -> dict[str, Any]:
    return {
        "version": 1,
        "brand": {"product_name": "Test App"},
        "pages": [
            {"route": "/", "type": "landing", "title": "Home", "sections": []},
            {"route": "/pricing", "type": "page", "title": "Pricing", "sections": []},
        ],
        "layout": {
            "nav": {
                "public": [{"label": "Features", "href": "/features"}],
                "cta": {"label": "Sign In", "href": "/login"},
            },
            "footer": {},
        },
        "legal": {},
    }


def _make_auth_context(*, authenticated: bool = False, roles: list[str] | None = None) -> Any:
    ctx = MagicMock()
    ctx.is_authenticated = authenticated
    ctx.roles = roles or []
    return ctx


def _get_auth_factory(auth_ctx: Any):
    def get_auth_context(request: Any) -> Any:
        return auth_ctx

    return get_auth_context


def _build_app(
    get_auth_context=None,
    persona_routes=None,
    sitespec=None,
) -> FastAPI:
    app = FastAPI()
    router = create_site_page_routes(
        sitespec_data=sitespec or _minimal_sitespec(),
        project_root=None,
        get_auth_context=get_auth_context,
        persona_routes=persona_routes,
    )
    app.include_router(router)
    return app


# ---------------------------------------------------------------------------
# Context model tests
# ---------------------------------------------------------------------------


class TestSitePageContextAuthFields:
    """SitePageContext has auth fields with correct defaults."""

    def test_defaults(self) -> None:
        ctx = SitePageContext()
        assert ctx.is_authenticated is False
        assert ctx.dashboard_url == "/app"

    def test_set_authenticated(self) -> None:
        ctx = SitePageContext(is_authenticated=True, dashboard_url="/app/dashboard")
        assert ctx.is_authenticated is True
        assert ctx.dashboard_url == "/app/dashboard"


# ---------------------------------------------------------------------------
# build_site_page_context tests
# ---------------------------------------------------------------------------


class TestBuildSitePageContextAuth:
    """build_site_page_context passes auth state through."""

    def test_unauthenticated_defaults(self) -> None:
        ctx = build_site_page_context(_minimal_sitespec(), "/")
        assert ctx.is_authenticated is False
        assert ctx.dashboard_url == "/app"

    def test_authenticated_passed_through(self) -> None:
        ctx = build_site_page_context(
            _minimal_sitespec(),
            "/pricing",
            is_authenticated=True,
            dashboard_url="/app/workspaces/customer_dashboard",
        )
        assert ctx.is_authenticated is True
        assert ctx.dashboard_url == "/app/workspaces/customer_dashboard"


# ---------------------------------------------------------------------------
# _extract_nav_items tests
# ---------------------------------------------------------------------------


class TestExtractNavItemsAuth:
    """_extract_nav_items prefers authenticated items when authenticated."""

    def test_public_items_when_not_authenticated(self) -> None:
        nav = {
            "public": [{"label": "Home", "href": "/"}],
            "authenticated": [{"label": "My Account", "href": "/account"}],
        }
        items = _extract_nav_items(nav, is_authenticated=False)
        assert len(items) == 1
        assert items[0].label == "Home"

    def test_authenticated_items_when_authenticated(self) -> None:
        nav = {
            "public": [{"label": "Home", "href": "/"}],
            "authenticated": [{"label": "My Account", "href": "/account"}],
        }
        items = _extract_nav_items(nav, is_authenticated=True)
        assert len(items) == 1
        assert items[0].label == "My Account"

    def test_falls_back_to_public_when_authenticated_empty(self) -> None:
        nav = {
            "public": [{"label": "Home", "href": "/"}],
            "authenticated": [],
        }
        items = _extract_nav_items(nav, is_authenticated=True)
        assert len(items) == 1
        assert items[0].label == "Home"

    def test_falls_back_to_public_when_authenticated_missing(self) -> None:
        nav = {"public": [{"label": "Home", "href": "/"}]}
        items = _extract_nav_items(nav, is_authenticated=True)
        assert len(items) == 1
        assert items[0].label == "Home"


# ---------------------------------------------------------------------------
# Nav template rendering tests
# ---------------------------------------------------------------------------


class TestNavTemplateRendering:
    """Nav template renders Dashboard vs CTA based on auth state."""

    def test_unauthenticated_shows_cta(self) -> None:
        ctx = build_site_page_context(_minimal_sitespec(), "/")
        from dazzle_ui.runtime.template_renderer import render_site_page

        html = render_site_page("site/page.html", ctx)
        assert "Sign In" in html
        assert 'href="/login"' in html

    def test_authenticated_shows_dashboard(self) -> None:
        ctx = build_site_page_context(
            _minimal_sitespec(),
            "/",
            is_authenticated=True,
            dashboard_url="/app/workspaces/customer_dashboard",
        )
        from dazzle_ui.runtime.template_renderer import render_site_page

        html = render_site_page("site/page.html", ctx)
        assert "Dashboard" in html
        assert 'href="/app/workspaces/customer_dashboard"' in html
        # Should NOT show Sign In
        assert "Sign In" not in html


# ---------------------------------------------------------------------------
# Integration tests (FastAPI routes)
# ---------------------------------------------------------------------------


class TestAuthNavIntegration:
    """End-to-end: route handlers pass auth state to template."""

    def test_unauthenticated_page_shows_cta(self) -> None:
        auth_ctx = _make_auth_context(authenticated=False)
        app = _build_app(
            get_auth_context=_get_auth_factory(auth_ctx),
            persona_routes=PERSONA_ROUTES,
        )
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/pricing")
        assert resp.status_code == 200
        assert "Sign In" in resp.text

    def test_authenticated_page_shows_dashboard(self) -> None:
        auth_ctx = _make_auth_context(authenticated=True, roles=["customer"])
        app = _build_app(
            get_auth_context=_get_auth_factory(auth_ctx),
            persona_routes=PERSONA_ROUTES,
        )
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/pricing")
        assert resp.status_code == 200
        assert "Dashboard" in resp.text
        assert "/app/workspaces/customer_dashboard" in resp.text

    def test_authenticated_with_persona_routes_resolves_dashboard(self) -> None:
        auth_ctx = _make_auth_context(authenticated=True, roles=["agent"])
        app = _build_app(
            get_auth_context=_get_auth_factory(auth_ctx),
            persona_routes=PERSONA_ROUTES,
        )
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/pricing")
        assert resp.status_code == 200
        assert "/app/workspaces/agent_dashboard" in resp.text

    def test_auth_failure_shows_cta(self) -> None:
        """Auth exception should not break page rendering."""

        def broken_auth(request: Any) -> Any:
            raise RuntimeError("session store down")

        app = _build_app(
            get_auth_context=broken_auth,
            persona_routes=PERSONA_ROUTES,
        )
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/pricing")
        assert resp.status_code == 200
        assert "Sign In" in resp.text

    def test_no_auth_middleware_shows_cta(self) -> None:
        app = _build_app(get_auth_context=None, persona_routes=None)
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/pricing")
        assert resp.status_code == 200
        assert "Sign In" in resp.text
