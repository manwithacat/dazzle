"""Tests for GET /auth/magic/{token} — magic link consumer endpoint."""

import logging
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.back.runtime.auth.magic_link_routes import (
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
            "dazzle.back.runtime.auth.magic_link_routes.validate_magic_link",
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
            "dazzle.back.runtime.auth.magic_link_routes.validate_magic_link",
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
            "dazzle.back.runtime.auth.magic_link_routes.validate_magic_link",
            return_value="ghost-user",
        ):
            resp = client.get("/auth/magic/valid_token", follow_redirects=False)

        assert resp.status_code == 303
        assert "error=invalid_magic_link" in resp.headers["location"]

    def test_valid_token_honours_next_query_param(self, client, mock_auth_store):
        """?next=/foo redirects to /foo after session creation."""
        _setup_valid_flow(mock_auth_store)
        with patch(
            "dazzle.back.runtime.auth.magic_link_routes.validate_magic_link",
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
            "dazzle.back.runtime.auth.magic_link_routes.validate_magic_link",
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
            "dazzle.back.runtime.auth.magic_link_routes.validate_magic_link",
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
            "dazzle.back.runtime.auth.magic_link_routes.validate_magic_link",
            return_value="user-123",
        ):
            resp = client.get(
                f"/auth/magic/valid_token?next={attack}",
                follow_redirects=False,
            )

        assert resp.status_code == 303
        assert resp.headers["location"] == "/"


class TestNextParamQueryInjection132:
    """CodeQL alert #132 / py/url-redirection: `_is_safe_redirect_path`
    accepts paths whose value contains `&` (e.g. `/foo&inject=1`),
    because urlparse treats them as path-with-query. When such a value
    was f-string-interpolated into another URL via `&next={next}`, the
    `&` was treated as a top-level query separator at the receiving
    endpoint, injecting an unrelated query parameter.

    The fix uses `urllib.parse.quote(value, safe="/")` so the `&` is
    percent-encoded as `%26` and remains part of the `next` value.
    """

    @pytest.mark.parametrize(
        "raw_next, expected_encoded",
        [
            ("/foo&inject=1", "/foo%26inject%3D1"),
            ("/path?bar=baz", "/path%3Fbar%3Dbaz"),
            ("/with spaces", "/with%20spaces"),
            ("/safe/path", "/safe/path"),  # No special chars — passes through.
        ],
    )
    def test_login_sent_redirect_encodes_next_param_132(
        self, client, mock_auth_store, raw_next: str, expected_encoded: str
    ) -> None:
        """`/login/sent?next=<encoded>` — the `next` value must be
        percent-encoded so any `&` / `?` in it cannot inject extra
        query params at the receiving endpoint."""
        mock_auth_store.get_user_by_email = MagicMock(return_value=None)
        resp = client.post(
            "/auth/login/magic-link",
            data={"email": "noone@example.com"},
            params={"next": raw_next},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        # Either: (a) /login/sent with no next (guard rejected it), or
        # (b) /login/sent?next=<expected_encoded>. Both are safe — the
        # invariant is that the raw `&inject=1` substring NEVER appears
        # as a top-level separator in the location header.
        if "next=" in location:
            assert f"next={expected_encoded}" in location, (
                f"Location {location!r} did not contain properly encoded next; "
                f"expected `next={expected_encoded}`. CodeQL #132 regression."
            )
        # Confirm the dangerous unencoded shape is absent.
        assert "&inject=" not in location, f"Query injection via &: location={location!r} (#132)"


_MAGIC_LOGGER = "dazzle.back.runtime.auth.magic_link_routes"


class TestMisencodedBodyWarning:
    """#1417 — a JSON (non-form) body makes Form() parse empty so the handler silently
    redirects with no mail; that now logs a WARNING (distinct from a genuinely empty form,
    which stays the quiet enumeration-guard path). The contract remains form-urlencoded."""

    def test_login_json_body_warns_and_no_mail(self, client, mock_auth_store, caplog) -> None:
        mailer = MagicMock()
        client.app.state.mailer = mailer
        with caplog.at_level(logging.WARNING, logger=_MAGIC_LOGGER):
            resp = client.post(
                "/auth/login/magic-link",
                json={"email": "alice@example.com"},  # JSON body → Form() reads empty
                follow_redirects=False,
            )
        assert resp.status_code == 303  # still redirects (enumeration-guard parity)
        mailer.send_magic_link.assert_not_called()
        assert any(
            "non-form request body" in r.message and r.levelno == logging.WARNING
            for r in caplog.records
        ), [r.message for r in caplog.records]

    def test_empty_form_does_not_warn(self, client, mock_auth_store, caplog) -> None:
        mock_auth_store.get_user_by_email = MagicMock(return_value=None)
        with caplog.at_level(logging.WARNING, logger=_MAGIC_LOGGER):
            resp = client.post(
                "/auth/login/magic-link",
                data={"email": ""},  # genuinely empty form field — not a misencoding
                follow_redirects=False,
            )
        assert resp.status_code == 303
        assert not any("non-form request body" in r.message for r in caplog.records)

    def test_signup_json_body_warns(self, client, mock_auth_store, caplog) -> None:
        client.app.state.mailer = MagicMock()
        with caplog.at_level(logging.WARNING, logger=_MAGIC_LOGGER):
            resp = client.post(
                "/auth/signup/magic-link",
                json={"email": "bob@example.com", "name": "Bob"},
                follow_redirects=False,
            )
        assert resp.status_code == 303
        assert any("non-form request body" in r.message for r in caplog.records)
