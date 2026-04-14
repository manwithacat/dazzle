"""Tests for GET /auth/magic/{token} — magic link consumer endpoint."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle_back.runtime.auth.magic_link_routes import (
    _is_safe_redirect_path,
    create_magic_link_routes,
)


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


class TestIsSafeRedirectPath:
    """Unit tests for the same-origin redirect validator.

    Covers the CodeQL py/url-redirection alert bypass patterns: backslash
    escaping, scheme injection, authority smuggling, and other URL parser
    edge cases that string-prefix checks miss.
    """

    # Accepted: valid same-origin paths
    @pytest.mark.parametrize(
        "path",
        [
            "/",
            "/dashboard",
            "/app/tasks/create",
            "/path?query=1",
            "/path#fragment",
            "/path?q=1#frag",
            "/deep/nested/path",
        ],
    )
    def test_accepts_same_origin_paths(self, path: str) -> None:
        assert _is_safe_redirect_path(path) is True

    # Rejected: protocol-relative (// prefix)
    @pytest.mark.parametrize(
        "path",
        [
            "//evil.com",
            "//evil.com/path",
            "//evil.com/stealcookies?c=1",
        ],
    )
    def test_rejects_protocol_relative(self, path: str) -> None:
        assert _is_safe_redirect_path(path) is False

    # Rejected: absolute URLs with scheme
    @pytest.mark.parametrize(
        "path",
        [
            "http://evil.com",
            "https://evil.com/path",
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "file:///etc/passwd",
        ],
    )
    def test_rejects_schemes(self, path: str) -> None:
        assert _is_safe_redirect_path(path) is False

    # Rejected: backslash bypass patterns (browsers may normalize \ to /)
    @pytest.mark.parametrize(
        "path",
        [
            "/\\evil.com",
            "/\\\\evil.com",
            "/\\@evil.com",
            "\\evil.com",
            "/path\\with\\backslashes",
        ],
    )
    def test_rejects_backslash_bypasses(self, path: str) -> None:
        """Backslash-containing paths must be rejected to close the CodeQL gap.

        Modern browsers normalize backslash to forward slash in some URL
        parsing contexts per the WHATWG URL spec. A path like /\\@evil.com
        may get re-parsed by the browser as //@evil.com, a protocol-relative
        URL with empty userinfo pointing at evil.com.
        """
        assert _is_safe_redirect_path(path) is False

    # Rejected: non-path inputs
    @pytest.mark.parametrize(
        "path",
        [
            "",
            "not-a-path",
            "evil.com",
            "relative/path",
        ],
    )
    def test_rejects_non_absolute_paths(self, path: str) -> None:
        assert _is_safe_redirect_path(path) is False


class TestMagicLinkBackslashBypass:
    """Integration regression tests for the backslash-bypass attack surface.

    These tests go through the full FastAPI route handler, not just the
    validator helper, to prove the end-to-end guard holds.
    """

    @pytest.mark.parametrize(
        "attack",
        [
            "/\\evil.com",
            "/\\\\evil.com",
            "/\\@evil.com",
            "http://evil.com",
            "javascript:alert(1)",
        ],
    )
    def test_malicious_next_parameter_falls_back_to_root(
        self, client, mock_auth_store, attack: str
    ) -> None:
        """Any of the known URL-redirect bypass attacks must fall back to /."""
        _setup_valid_flow(mock_auth_store)
        with patch(
            "dazzle_back.runtime.auth.magic_link_routes.validate_magic_link",
            return_value="user-123",
        ):
            resp = client.get(
                f"/auth/magic/valid_token?next={attack}",
                follow_redirects=False,
            )

        assert resp.status_code == 303
        assert resp.headers["location"] == "/"
