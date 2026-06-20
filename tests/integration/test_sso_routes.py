"""Integration tests for SSO routes (Phase 1.C).

Uses a fake OAuth client to drive the initiation + callback flow
without contacting Google / Microsoft. The fake is installed by
seeding `app.state._sso_clients` before the request, so
`_get_or_create_oauth_client` returns the fake instead of building
a real Authlib client.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

pytest.importorskip("dazzle.http.runtime.auth.sso_routes")
from dazzle.http.runtime.auth.sso_config import SsoProviderConfig  # noqa: E402
from dazzle.http.runtime.auth.sso_routes import create_sso_routes  # noqa: E402


def _google() -> SsoProviderConfig:
    return SsoProviderConfig(
        name="google",
        display_name="Google",
        client_id="id",
        client_secret="secret",
        discovery_url="https://accounts.google.com/.well-known/openid-configuration",
        scopes="openid email profile",
    )


class _StubUser:
    def __init__(self, user_id: str = "user-1") -> None:
        self.id = user_id


class _StubSession:
    def __init__(self, sid: str = "sess-1") -> None:
        self.id = sid
        # Declarative-CSRF Phase 1: the SSO callback now also reads
        # session.csrf_secret to set the session-bound dazzle_csrf cookie,
        # so the stub must mirror that field of the real SessionRecord.
        self.csrf_secret = f"csrf-{sid}"


class _StubAuthStore:
    def __init__(self, *, known_email: str | None = None) -> None:
        self._known_email = (known_email or "").lower()
        self.created_users: list[tuple[str, str | None]] = []
        self.created_sessions: list[str] = []

    def get_user_by_email(self, email: str) -> _StubUser | None:
        if email.lower() == self._known_email:
            return _StubUser(user_id="existing-user")
        return None

    def create_user(self, *, email: str, password: str, username: str | None = None) -> _StubUser:
        self.created_users.append((email, username))
        return _StubUser(user_id="new-user")

    def get_memberships_for_identity(self, identity_id: str) -> list:
        return []  # auth Plan 1b — no memberships in this stub

    def create_session(
        self, user: _StubUser, *, active_membership_id: str | None = None
    ) -> _StubSession:
        sid = f"sess-for-{user.id}"
        self.created_sessions.append(sid)
        return _StubSession(sid=sid)


class _FakeOAuthClient:
    """Stand-in for `StarletteOAuth2App`.

    `authorize_redirect` returns a 302 to a fake provider URL.
    `authorize_access_token` returns a token dict carrying a
    userinfo block built from constructor args.
    """

    def __init__(
        self,
        *,
        userinfo: dict[str, Any] | None = None,
        token_raises: BaseException | None = None,
    ) -> None:
        self._userinfo = userinfo
        self._token_raises = token_raises
        self.authorize_redirect_calls: list[tuple[str, str]] = []
        self.authorize_access_token_calls = 0

    async def authorize_redirect(self, request: Any, callback_url: str) -> Any:
        from fastapi.responses import RedirectResponse

        self.authorize_redirect_calls.append((str(request.url.path), callback_url))
        return RedirectResponse(
            url=f"https://fake-provider.example/authorize?redirect_uri={callback_url}",
            status_code=302,
        )

    async def authorize_access_token(self, request: Any) -> dict[str, Any]:
        self.authorize_access_token_calls += 1
        if self._token_raises is not None:
            raise self._token_raises
        return {"userinfo": self._userinfo or {}}


def _build_app(
    *,
    google_client: _FakeOAuthClient | None = None,
    known_email: str | None = None,
    provider_configured: bool = True,
) -> tuple[TestClient, _StubAuthStore]:
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret")
    app.state.sso_providers = (_google(),) if provider_configured else ()
    app.state.auth_store = _StubAuthStore(known_email=known_email)
    if google_client is not None:
        app.state._sso_clients = {"google": google_client}
    app.include_router(create_sso_routes())
    return TestClient(app, follow_redirects=False), app.state.auth_store


# ───────────────── GET /auth/sso/{provider} initiation ─────────────────


def test_initiate_redirects_to_provider_authorize_url() -> None:
    fake = _FakeOAuthClient(userinfo={"email": "alice@example.com"})
    client, _ = _build_app(google_client=fake)
    resp = client.get("/auth/sso/google")
    assert resp.status_code == 302
    assert "fake-provider.example/authorize" in resp.headers["location"]
    # The callback URL was passed to authorize_redirect.
    assert fake.authorize_redirect_calls
    callback_url = fake.authorize_redirect_calls[0][1]
    assert callback_url.endswith("/auth/sso/google/callback")


def test_initiate_unknown_provider_redirects_with_error() -> None:
    client, _ = _build_app()
    resp = client.get("/auth/sso/unknown-provider")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login?error=sso_provider_unknown"


def test_initiate_when_no_providers_configured_redirects_with_error() -> None:
    """A provider name that LOOKS valid but isn't on this deployment
    still gets the same friendly error."""
    fake = _FakeOAuthClient()
    client, _ = _build_app(google_client=fake, provider_configured=False)
    resp = client.get("/auth/sso/google")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login?error=sso_provider_unknown"


def test_initiate_stashes_safe_next_in_session() -> None:
    fake = _FakeOAuthClient()
    client, _ = _build_app(google_client=fake)
    resp = client.get("/auth/sso/google?next=/app/tasks")
    assert resp.status_code == 302  # the fake-provider redirect
    # The session cookie was set — the next-URL is opaque to us but
    # the callback test will verify it threads through.
    assert "session=" in resp.headers.get("set-cookie", "")


# ───────────────── GET /auth/sso/{provider}/callback ─────────────────


def test_callback_existing_email_creates_session_and_redirects_app() -> None:
    fake = _FakeOAuthClient(userinfo={"email": "alice@example.com", "email_verified": True})
    client, store = _build_app(google_client=fake, known_email="alice@example.com")
    resp = client.get("/auth/sso/google/callback?code=fake-code")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/app"
    # No new user — existing one was matched.
    assert store.created_users == []
    # A session was created for the existing user.
    assert store.created_sessions == ["sess-for-existing-user"]
    # Session cookie set.
    assert "dazzle_session=" in resp.headers.get("set-cookie", "")


def test_callback_unknown_email_provisions_new_user() -> None:
    fake = _FakeOAuthClient(
        userinfo={"email": "bob@example.com", "email_verified": True, "name": "Bob"}
    )
    client, store = _build_app(google_client=fake)
    resp = client.get("/auth/sso/google/callback?code=fake-code")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/app"
    # New passwordless user created with the OAuth-verified email + name.
    assert store.created_users == [("bob@example.com", "Bob")]
    assert store.created_sessions == ["sess-for-new-user"]


def test_callback_token_exchange_failure_redirects_with_error() -> None:
    fake = _FakeOAuthClient(token_raises=RuntimeError("provider unreachable"))
    client, store = _build_app(google_client=fake)
    resp = client.get("/auth/sso/google/callback?code=fake-code")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login?error=sso_failed"
    assert store.created_users == []
    assert store.created_sessions == []


def test_callback_missing_email_in_userinfo_rejects() -> None:
    """A provider that omits the email field (configured wrong) gets
    a friendly redirect rather than crashing the request."""
    fake = _FakeOAuthClient(userinfo={"name": "no-email"})
    client, store = _build_app(google_client=fake)
    resp = client.get("/auth/sso/google/callback?code=fake-code")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login?error=sso_no_email"
    assert store.created_users == []


def test_callback_unverified_email_refuses_signin() -> None:
    """Email-takeover guard — only trust the email when the IdP
    explicitly says it's verified."""
    fake = _FakeOAuthClient(userinfo={"email": "alice@example.com", "email_verified": False})
    client, store = _build_app(google_client=fake)
    resp = client.get("/auth/sso/google/callback?code=fake-code")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login?error=sso_email_unverified"
    assert store.created_users == []
    assert store.created_sessions == []


def test_callback_unknown_provider_redirects_with_error() -> None:
    client, _ = _build_app()
    resp = client.get("/auth/sso/bogus/callback?code=x")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login?error=sso_provider_unknown"


def test_callback_normalises_email_to_lowercase() -> None:
    fake = _FakeOAuthClient(userinfo={"email": "  ALICE@EXAMPLE.COM  ", "email_verified": True})
    client, store = _build_app(google_client=fake, known_email="alice@example.com")
    resp = client.get("/auth/sso/google/callback?code=fake-code")
    assert resp.status_code == 303
    # Existing user matched via lowercase comparison.
    assert store.created_users == []
    assert store.created_sessions == ["sess-for-existing-user"]


def test_callback_with_session_stashed_next_threads_through() -> None:
    """End-to-end: initiate stashes ?next= in session, callback
    pulls it out and uses it as the post-login redirect."""
    fake = _FakeOAuthClient(userinfo={"email": "alice@example.com", "email_verified": True})
    client, _ = _build_app(google_client=fake, known_email="alice@example.com")
    # Initiate request — TestClient persists the session cookie.
    client.get("/auth/sso/google?next=/app/dashboard", follow_redirects=False)
    resp = client.get("/auth/sso/google/callback?code=fake-code")
    assert resp.status_code == 303
    assert resp.headers["location"] == "/app/dashboard"


def test_callback_unsafe_session_stashed_next_falls_back() -> None:
    """If the session somehow ended up with an off-origin next-URL,
    the callback must reject it."""
    fake = _FakeOAuthClient(userinfo={"email": "alice@example.com", "email_verified": True})
    client, _ = _build_app(google_client=fake, known_email="alice@example.com")
    client.get("/auth/sso/google?next=//evil.example/x", follow_redirects=False)
    resp = client.get("/auth/sso/google/callback?code=fake-code")
    assert resp.status_code == 303
    # The unsafe value was rejected at the initiate stash AND/OR the
    # callback validation — either way we land on /app.
    assert resp.headers["location"] == "/app"
