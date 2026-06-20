"""Tests for auth-aware navigation on site pages.

When a user is authenticated, the nav CTA should render "Dashboard" linking
to their workspace.  When unauthenticated, the configured CTA (e.g. "Sign In")
is shown instead.
"""

from typing import Any
from unittest.mock import MagicMock

import pytest

# Skip if FastAPI not installed
pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from dazzle.http.runtime.site_routes import create_site_page_routes  # noqa: E402
from dazzle.page.runtime.site_context import (  # noqa: E402
    _extract_nav_items,
    build_site_page_context,
)
from dazzle.render.context import SitePageContext  # noqa: E402

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

    @pytest.mark.parametrize(
        ("nav", "is_authenticated", "expected_label"),
        [
            (
                {
                    "public": [{"label": "Home", "href": "/"}],
                    "authenticated": [{"label": "My Account", "href": "/account"}],
                },
                False,
                "Home",
            ),
            (
                {
                    "public": [{"label": "Home", "href": "/"}],
                    "authenticated": [{"label": "My Account", "href": "/account"}],
                },
                True,
                "My Account",
            ),
            (
                {
                    "public": [{"label": "Home", "href": "/"}],
                    "authenticated": [],
                },
                True,
                "Home",
            ),
            (
                {"public": [{"label": "Home", "href": "/"}]},
                True,
                "Home",
            ),
        ],
        ids=[
            "test_public_items_when_not_authenticated",
            "test_authenticated_items_when_authenticated",
            "test_falls_back_to_public_when_authenticated_empty",
            "test_falls_back_to_public_when_authenticated_missing",
        ],
    )
    def test_extract_nav_items(
        self, nav: dict, is_authenticated: bool, expected_label: str
    ) -> None:
        items = _extract_nav_items(nav, is_authenticated=is_authenticated)
        assert len(items) == 1
        assert items[0].label == expected_label


# ---------------------------------------------------------------------------
# Nav template rendering tests
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason="v0.67.69 retired site/inner_only.html — auth-CTA-vs-dashboard "
    "rendering is now in site_routes._render_site_inner_html (inline Python). "
    "Behavioural coverage migrated to test_site_routes_no_duplicate_registration "
    "+ end-to-end site-route tests."
)
class TestNavTemplateRendering:
    """Nav template renders Dashboard vs CTA based on auth state."""

    def test_unauthenticated_shows_cta(self) -> None: ...

    def test_authenticated_shows_dashboard(self) -> None: ...


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
