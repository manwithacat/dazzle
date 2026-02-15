"""Unit tests for container auth endpoints (dazzle_ui.runtime.container.auth).

These tests run without DATABASE_URL — they use the in-memory auth store.
"""

from __future__ import annotations

from typing import Any

import pytest

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

pytestmark = pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")


@pytest.fixture(autouse=True)
def _clean_auth_data() -> Any:
    """Clean in-memory auth data between tests."""
    from dazzle_ui.runtime.container.auth import clear_auth_data

    clear_auth_data()
    yield
    clear_auth_data()


@pytest.fixture()
def client() -> Any:
    """Create a TestClient with auth routes registered."""
    from dazzle_ui.runtime.container.auth import register_auth_routes

    app = FastAPI()
    register_auth_routes(app)
    return TestClient(app)


def _login(client: Any, email: str = "test@example.com", password: str = "pass") -> Any:
    """Register + login helper, returns login response."""
    from dazzle_ui.runtime.container.auth import AUTH_USERS, hash_password

    AUTH_USERS[email] = {
        "id": "user-1",
        "email": email,
        "password_hash": hash_password(password),
        "display_name": email.split("@")[0],
        "is_active": True,
    }
    return client.post("/auth/login", json={"email": email, "password": password})


class TestLogoutContentNegotiation:
    """Logout endpoint content-negotiates on Accept header."""

    def test_browser_redirect(self, client: Any) -> None:
        """Accept: text/html → 302 redirect to /."""
        login_resp = _login(client)
        response = client.post(
            "/auth/logout",
            cookies=login_resp.cookies,
            headers={"Accept": "text/html"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/"

    def test_api_json(self, client: Any) -> None:
        """Accept: application/json → 200 JSON."""
        login_resp = _login(client)
        response = client.post(
            "/auth/logout",
            cookies=login_resp.cookies,
            headers={"Accept": "application/json"},
        )
        assert response.status_code == 200
        assert response.json()["message"] == "Logout successful"

    def test_no_accept_header_returns_json(self, client: Any) -> None:
        """No Accept header → JSON (API client default)."""
        login_resp = _login(client)
        response = client.post("/auth/logout", cookies=login_resp.cookies)
        assert response.status_code == 200

    def test_cookie_cleared_on_redirect(self, client: Any) -> None:
        """Session cookie is deleted in both redirect and JSON responses."""
        login_resp = _login(client)
        response = client.post(
            "/auth/logout",
            cookies=login_resp.cookies,
            headers={"Accept": "text/html"},
            follow_redirects=False,
        )
        set_cookie = response.headers.get("set-cookie", "")
        assert "dazzle_session" in set_cookie


class TestLoginRedirectUrl:
    """Login response includes redirect_url for post-login navigation."""

    def test_default_redirect_url(self, client: Any) -> None:
        """Without persona routes, redirect_url defaults to /app."""
        response = _login(client)
        assert response.status_code == 200
        assert response.json()["redirect_url"] == "/app"

    def test_persona_route_resolved(self) -> None:
        """When persona_routes is set, redirect_url matches user's role."""
        from dazzle_ui.runtime.container.auth import (
            AUTH_USERS,
            hash_password,
            register_auth_routes,
        )

        app = FastAPI()
        register_auth_routes(app, persona_routes={"admin": "/app/workspaces/admin_dashboard"})
        client = TestClient(app)

        AUTH_USERS["admin@test.com"] = {
            "id": "u-admin",
            "email": "admin@test.com",
            "password_hash": hash_password("pass"),
            "display_name": "Admin",
            "is_active": True,
            "roles": ["admin"],
        }

        response = client.post("/auth/login", json={"email": "admin@test.com", "password": "pass"})
        assert response.json()["redirect_url"] == "/app/workspaces/admin_dashboard"

    def test_no_matching_role_falls_back(self) -> None:
        """User with no matching role gets default /app."""
        from dazzle_ui.runtime.container.auth import (
            AUTH_USERS,
            hash_password,
            register_auth_routes,
        )

        app = FastAPI()
        register_auth_routes(app, persona_routes={"admin": "/app/workspaces/admin_dashboard"})
        client = TestClient(app)

        AUTH_USERS["user@test.com"] = {
            "id": "u-user",
            "email": "user@test.com",
            "password_hash": hash_password("pass"),
            "display_name": "User",
            "is_active": True,
            "roles": ["viewer"],
        }

        response = client.post("/auth/login", json={"email": "user@test.com", "password": "pass"})
        assert response.json()["redirect_url"] == "/app"
