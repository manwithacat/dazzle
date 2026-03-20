"""Tests for authenticated user redirect from / to persona default workspace (#569).

When a user with an active session hits /, they should be redirected (302) to
their persona's default_route.  Unauthenticated users see the marketing page.
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_sitespec() -> dict[str, Any]:
    """Minimal sitespec with a landing page at /."""
    return {
        "version": 1,
        "brand": {"product_name": "Test App"},
        "pages": [
            {"route": "/", "type": "landing", "title": "Home", "sections": []},
            {"route": "/pricing", "type": "page", "title": "Pricing", "sections": []},
        ],
        "layout": {},
        "legal": {},
    }


def _make_auth_context(*, authenticated: bool = False, roles: list[str] | None = None) -> Any:
    ctx = MagicMock()
    ctx.is_authenticated = authenticated
    ctx.roles = roles or []
    return ctx


def _get_auth_factory(auth_ctx: Any):
    """Return a get_auth_context callable that always returns *auth_ctx*."""

    def get_auth_context(request: Any) -> Any:
        return auth_ctx

    return get_auth_context


PERSONA_ROUTES = {
    "customer": "/app/workspaces/customer_dashboard",
    "agent": "/app/workspaces/agent_dashboard",
}


def _build_app(
    get_auth_context=None,
    persona_routes=None,
) -> FastAPI:
    """Build a minimal FastAPI app with site page routes."""
    app = FastAPI()
    router = create_site_page_routes(
        sitespec_data=_minimal_sitespec(),
        project_root=None,
        get_auth_context=get_auth_context,
        persona_routes=persona_routes,
    )
    app.include_router(router)
    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRootRedirectAuthenticated:
    """Authenticated users hitting / are redirected to their workspace."""

    def test_authenticated_customer_redirected(self) -> None:
        auth_ctx = _make_auth_context(authenticated=True, roles=["customer"])
        app = _build_app(
            get_auth_context=_get_auth_factory(auth_ctx),
            persona_routes=PERSONA_ROUTES,
        )
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/")
        assert resp.status_code == 302
        assert resp.headers["location"] == "/app/workspaces/customer_dashboard"

    def test_authenticated_agent_redirected(self) -> None:
        auth_ctx = _make_auth_context(authenticated=True, roles=["agent"])
        app = _build_app(
            get_auth_context=_get_auth_factory(auth_ctx),
            persona_routes=PERSONA_ROUTES,
        )
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/")
        assert resp.status_code == 302
        assert resp.headers["location"] == "/app/workspaces/agent_dashboard"

    def test_first_matching_role_wins(self) -> None:
        """When user has multiple roles, the first one with a route wins."""
        auth_ctx = _make_auth_context(authenticated=True, roles=["agent", "customer"])
        app = _build_app(
            get_auth_context=_get_auth_factory(auth_ctx),
            persona_routes=PERSONA_ROUTES,
        )
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/")
        assert resp.status_code == 302
        assert resp.headers["location"] == "/app/workspaces/agent_dashboard"


class TestRootLandingForUnauthenticated:
    """Unauthenticated users see the marketing page."""

    def test_unauthenticated_sees_landing_page(self) -> None:
        auth_ctx = _make_auth_context(authenticated=False)
        app = _build_app(
            get_auth_context=_get_auth_factory(auth_ctx),
            persona_routes=PERSONA_ROUTES,
        )
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/")
        assert resp.status_code == 200

    def test_no_auth_context_sees_landing_page(self) -> None:
        """When no auth middleware is configured, / serves the landing page."""
        app = _build_app(get_auth_context=None, persona_routes=None)
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/")
        assert resp.status_code == 200

    def test_auth_exception_falls_back_to_landing(self) -> None:
        """If auth check throws, gracefully fall back to the landing page."""

        def broken_auth(request: Any) -> Any:
            raise RuntimeError("session store unavailable")

        app = _build_app(
            get_auth_context=broken_auth,
            persona_routes=PERSONA_ROUTES,
        )
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/")
        assert resp.status_code == 200


class TestNonRootPagesUnaffected:
    """Public pages other than / must NOT redirect."""

    def test_pricing_page_not_redirected(self) -> None:
        auth_ctx = _make_auth_context(authenticated=True, roles=["customer"])
        app = _build_app(
            get_auth_context=_get_auth_factory(auth_ctx),
            persona_routes=PERSONA_ROUTES,
        )
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/pricing")
        assert resp.status_code == 200


class TestAuthenticatedNoMatchingRoute:
    """Authenticated user whose role has no persona route sees landing page."""

    def test_unknown_role_sees_landing(self) -> None:
        auth_ctx = _make_auth_context(authenticated=True, roles=["admin"])
        app = _build_app(
            get_auth_context=_get_auth_factory(auth_ctx),
            persona_routes=PERSONA_ROUTES,  # no "admin" entry
        )
        client = TestClient(app, follow_redirects=False)
        resp = client.get("/")
        assert resp.status_code == 200
