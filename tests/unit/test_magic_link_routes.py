"""Tests for GET /auth/magic/{token} — magic link consumer endpoint."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle_back.runtime.auth.magic_link_routes import create_magic_link_routes


@pytest.fixture
def mock_auth_store():
    store = MagicMock()
    return store


@pytest.fixture
def app(mock_auth_store):
    app = FastAPI()
    app.state.auth_store = mock_auth_store
    router = create_magic_link_routes()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def _setup_valid_flow(mock_auth_store):
    """Wire the mock store for the successful validation code path."""
    user = MagicMock()
    user.id = "user-123"
    mock_auth_store.get_user_by_id = MagicMock(return_value=user)
    session = MagicMock()
    session.id = "session-token-abc"
    mock_auth_store.create_session = MagicMock(return_value=session)


class TestMagicLinkConsumer:
    def test_valid_token_creates_session_and_redirects(self, client, mock_auth_store):
        """Valid token → 303 redirect with session cookie set."""
        _setup_valid_flow(mock_auth_store)
        with patch(
            "dazzle_back.runtime.auth.magic_link_routes.validate_magic_link",
            return_value="user-123",
        ):
            resp = client.get("/auth/magic/valid_token", follow_redirects=False)

        assert resp.status_code == 303
        assert resp.headers["location"] == "/"
        assert "dazzle_session" in resp.cookies
        assert resp.cookies["dazzle_session"] == "session-token-abc"

    def test_invalid_token_redirects_to_login_with_error(self, client, mock_auth_store):
        """Invalid/expired/used token → redirect to login with error query param."""
        with patch(
            "dazzle_back.runtime.auth.magic_link_routes.validate_magic_link",
            return_value=None,
        ):
            resp = client.get("/auth/magic/bad_token", follow_redirects=False)

        assert resp.status_code == 303
        assert "error=invalid_magic_link" in resp.headers["location"]
        assert "/auth/login" in resp.headers["location"]

    def test_user_not_found_redirects_to_login(self, client, mock_auth_store):
        """Valid token but user no longer exists → redirect to login with error."""
        mock_auth_store.get_user_by_id = MagicMock(return_value=None)
        with patch(
            "dazzle_back.runtime.auth.magic_link_routes.validate_magic_link",
            return_value="ghost-user",
        ):
            resp = client.get("/auth/magic/valid_token", follow_redirects=False)

        assert resp.status_code == 303
        assert "error=invalid_magic_link" in resp.headers["location"]

    def test_valid_token_honours_next_query_param(self, client, mock_auth_store):
        """?next=/foo redirects to /foo after session creation."""
        _setup_valid_flow(mock_auth_store)
        with patch(
            "dazzle_back.runtime.auth.magic_link_routes.validate_magic_link",
            return_value="user-123",
        ):
            resp = client.get(
                "/auth/magic/valid_token?next=/dashboard",
                follow_redirects=False,
            )

        assert resp.status_code == 303
        assert resp.headers["location"] == "/dashboard"

    def test_next_query_param_must_be_same_origin(self, client, mock_auth_store):
        """?next=https://evil.com should be rejected and redirect to /."""
        _setup_valid_flow(mock_auth_store)
        with patch(
            "dazzle_back.runtime.auth.magic_link_routes.validate_magic_link",
            return_value="user-123",
        ):
            resp = client.get(
                "/auth/magic/valid_token?next=https://evil.com",
                follow_redirects=False,
            )

        assert resp.status_code == 303
        assert resp.headers["location"] == "/"

    def test_protocol_relative_next_rejected(self, client, mock_auth_store):
        """?next=//evil.com (protocol-relative) should also be rejected."""
        _setup_valid_flow(mock_auth_store)
        with patch(
            "dazzle_back.runtime.auth.magic_link_routes.validate_magic_link",
            return_value="user-123",
        ):
            resp = client.get(
                "/auth/magic/valid_token?next=//evil.com/stealcookies",
                follow_redirects=False,
            )

        assert resp.status_code == 303
        assert resp.headers["location"] == "/"
