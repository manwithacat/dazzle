"""Tests for the email-verification routes (#1109).

Modelled on ``test_magic_link_routes.py`` — same test client wiring,
same mock-store shape — so the two flows have parallel coverage and
the contract is obvious in diff.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.auth.email_verification_routes import (
    _build_verify_url,
    _is_safe_redirect_path,
    create_email_verification_routes,
)


@pytest.fixture
def mock_auth_store() -> MagicMock:
    store = MagicMock()
    # #1424 Task 3.4: the verify-email handler now evaluates a verified-domain
    # self-service join after marking the email verified. Give the bare MagicMock
    # store no-op domain-join reads so the join path cleanly resolves to "none"
    # (no tenant for the domain) instead of following MagicMock truthiness into a
    # spurious join. Tests that exercise the join itself use a dedicated fake
    # (see test_email_verify_domain_join.py).
    store.get_connection_by_verified_domain = MagicMock(return_value=None)
    store.get_org_settings = MagicMock(return_value={})
    store.get_connections_for_tenant = MagicMock(return_value=[])
    store.get_memberships_for_identity = MagicMock(return_value=[])
    return store


@pytest.fixture
def app(mock_auth_store: MagicMock) -> FastAPI:
    app = FastAPI()
    app.state.auth_store = mock_auth_store
    # Tighten the rate-limit window so resend tests can race without
    # waiting in real time.
    router = create_email_verification_routes(resend_rate_limit_seconds=0.05)
    app.include_router(router)
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /auth/verify-email — consume the token
# ---------------------------------------------------------------------------


class TestVerifyEmailConsumer:
    def test_valid_token_redirects_with_success_flag(
        self, client: TestClient, mock_auth_store: MagicMock
    ) -> None:
        user = MagicMock()
        user.email = "alice@example.com"
        mock_auth_store.get_user_by_id = MagicMock(return_value=user)
        with patch(
            "dazzle.http.runtime.auth.email_verification_routes.validate_email_verification_token",
            return_value="user-123",
        ):
            resp = client.get("/auth/verify-email?token=valid", follow_redirects=False)
        assert resp.status_code == 303
        assert "verified=ok" in resp.headers["location"]

    def test_invalid_token_redirects_to_login_with_error_flag(self, client: TestClient) -> None:
        with patch(
            "dazzle.http.runtime.auth.email_verification_routes.validate_email_verification_token",
            return_value=None,
        ):
            resp = client.get("/auth/verify-email?token=bad_or_expired", follow_redirects=False)
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "/auth/login" in location
        assert "verified=error" in location
        assert "invalid_or_expired" in location

    def test_missing_token_returns_error_redirect(self, client: TestClient) -> None:
        resp = client.get("/auth/verify-email", follow_redirects=False)
        assert resp.status_code == 303
        assert "missing_token" in resp.headers["location"]

    def test_success_threads_next_param_with_flag(
        self, client: TestClient, mock_auth_store: MagicMock
    ) -> None:
        user = MagicMock()
        user.email = "alice@example.com"
        mock_auth_store.get_user_by_id = MagicMock(return_value=user)
        with patch(
            "dazzle.http.runtime.auth.email_verification_routes.validate_email_verification_token",
            return_value="user-123",
        ):
            resp = client.get(
                "/auth/verify-email?token=valid&next=/dashboard", follow_redirects=False
            )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/dashboard?verified=ok"

    def test_unsafe_next_falls_back_to_root(
        self, client: TestClient, mock_auth_store: MagicMock
    ) -> None:
        user = MagicMock()
        user.email = "alice@example.com"
        mock_auth_store.get_user_by_id = MagicMock(return_value=user)
        with patch(
            "dazzle.http.runtime.auth.email_verification_routes.validate_email_verification_token",
            return_value="user-123",
        ):
            resp = client.get(
                "/auth/verify-email?token=valid&next=//evil.com",
                follow_redirects=False,
            )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/?verified=ok"


# ---------------------------------------------------------------------------
# POST /auth/send-verification + /auth/resend-verification
# ---------------------------------------------------------------------------


class TestSendVerification:
    def test_unknown_email_still_returns_sent_page(
        self, client: TestClient, mock_auth_store: MagicMock
    ) -> None:
        """Account-enumeration guard — same response shape whether the
        email matches a user or not."""
        mock_auth_store.get_user_by_email = MagicMock(return_value=None)
        resp = client.post(
            "/auth/send-verification",
            data={"email": "nobody@example.com"},
            follow_redirects=False,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/verification/sent"

    def test_known_unverified_email_triggers_mail(
        self, client: TestClient, mock_auth_store: MagicMock
    ) -> None:
        user = MagicMock()
        user.id = "user-123"
        user.email_verified = False
        mock_auth_store.get_user_by_email = MagicMock(return_value=user)
        with (
            patch(
                "dazzle.http.runtime.auth.email_verification_routes."
                "create_email_verification_token",
                return_value="generated-token",
            ),
            patch(
                "dazzle.http.runtime.auth.email_verification_routes.get_verification_mailer"
            ) as get_mailer,
        ):
            mailer = MagicMock()
            get_mailer.return_value = mailer
            resp = client.post(
                "/auth/send-verification",
                data={"email": "alice@example.com"},
                follow_redirects=False,
            )
        assert resp.status_code == 303
        mailer.send_verification_email.assert_called_once()
        call_kwargs = mailer.send_verification_email.call_args.kwargs
        assert call_kwargs["to_email"] == "alice@example.com"
        assert "/auth/verify-email?token=generated-token" in call_kwargs["verify_url"]

    def test_already_verified_email_skips_mail(
        self, client: TestClient, mock_auth_store: MagicMock
    ) -> None:
        user = MagicMock()
        user.id = "user-123"
        user.email_verified = True
        mock_auth_store.get_user_by_email = MagicMock(return_value=user)
        with patch(
            "dazzle.http.runtime.auth.email_verification_routes.get_verification_mailer"
        ) as get_mailer:
            mailer = MagicMock()
            get_mailer.return_value = mailer
            resp = client.post(
                "/auth/send-verification",
                data={"email": "alice@example.com"},
                follow_redirects=False,
            )
        assert resp.status_code == 303
        mailer.send_verification_email.assert_not_called()


class TestResendVerificationRateLimit:
    def test_resend_throttled_within_window(
        self, client: TestClient, mock_auth_store: MagicMock
    ) -> None:
        user = MagicMock()
        user.id = "user-123"
        user.email_verified = False
        mock_auth_store.get_user_by_email = MagicMock(return_value=user)
        with (
            patch(
                "dazzle.http.runtime.auth.email_verification_routes."
                "create_email_verification_token",
                return_value="generated-token",
            ),
            patch(
                "dazzle.http.runtime.auth.email_verification_routes.get_verification_mailer"
            ) as get_mailer,
        ):
            mailer = MagicMock()
            get_mailer.return_value = mailer
            # Two rapid resends in the 50ms rate-limit window: the second
            # must NOT send mail.
            client.post(
                "/auth/resend-verification",
                data={"email": "alice@example.com"},
                follow_redirects=False,
            )
            client.post(
                "/auth/resend-verification",
                data={"email": "alice@example.com"},
                follow_redirects=False,
            )
        assert mailer.send_verification_email.call_count == 1


# ---------------------------------------------------------------------------
# URL builder + redirect-safety helpers
# ---------------------------------------------------------------------------


def test_build_verify_url_threads_next_param() -> None:
    request = MagicMock()
    request.base_url = "https://example.com/"
    url = _build_verify_url(request=request, token="abc", next_path="/dashboard")
    assert url == "https://example.com/auth/verify-email?token=abc&next=/dashboard"


def test_build_verify_url_omits_next_when_default() -> None:
    request = MagicMock()
    request.base_url = "https://example.com/"
    url = _build_verify_url(request=request, token="abc", next_path="/")
    assert url == "https://example.com/auth/verify-email?token=abc"


@pytest.mark.parametrize(
    "value,expected",
    [
        ("/dashboard", True),
        ("/", True),
        ("//evil.com", False),
        ("http://evil.com", False),
        ("javascript:alert(1)", False),
        ("/\\evil.com", False),
        ("relative", False),
    ],
)
def test_is_safe_redirect_path(value: str, expected: bool) -> None:
    assert _is_safe_redirect_path(value) is expected
