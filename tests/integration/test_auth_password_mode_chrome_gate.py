"""Phase 1.B.3 (v0.67.32): integration tests for the typed-Fragment
password-mode login + signup flow.

Coverage:
  1. GET /login under chrome=on + password_mode=True renders the
     password view; chrome=on + password_mode=False keeps the
     magic-link view (default).
  2. GET /signup under the same flag matrix.
  3. POST /auth/login/password authenticates against the auth store,
     sets the dazzle_session cookie, and redirects to ?next= when
     safe (or /app). Failure → 303 to /login?error=invalid_credentials.
  4. POST /auth/login/password handles 2FA-enabled accounts by
     redirecting to /2fa/challenge with the pending session id.
  5. POST /auth/signup/password creates a user + session, handles
     mismatch / already_registered / create_failed / invalid_email.
  6. Account-enumeration NOT a concern for password-mode signup —
     the existing-email path returns a clear error (intended UX:
     password-mode deployments accept that signup leaks email
     existence in exchange for friendlier errors).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytest.importorskip("dazzle.http.runtime.site_routes")
from dazzle.http.runtime.auth.password_login_routes import (  # noqa: E402
    create_password_login_routes,
)
from dazzle.http.runtime.site_routes import create_auth_page_routes  # noqa: E402

_MIN_SITESPEC = {
    "version": 1,
    "brand": {
        "product_name": "TestApp",
        "tagline": "Test",
        "company_legal_name": "Test",
        "support_email": "test@example.com",
    },
    "pages": [],
    "layout": {"nav": {"public": []}, "footer": {"columns": [], "disclaimer": ""}},
}


class _StubSession:
    def __init__(self, session_id: str = "session-abc") -> None:
        self.id = session_id
        # Mirror the real SessionRecord.csrf_secret (declarative-CSRF Phase 1):
        # the form-login/signup routes now read session.csrf_secret to set the
        # session-bound dazzle_csrf cookie.
        self.csrf_secret = f"csrf-{session_id}"


class _StubUser:
    def __init__(
        self,
        *,
        user_id: str = "user-123",
        two_factor_enabled: bool = False,
    ) -> None:
        self.id = user_id
        self.two_factor_enabled = two_factor_enabled


class _StubAuthStore:
    """Minimal auth-store stub exposing the methods the password-mode
    endpoints call: authenticate, get_user_by_email, create_user,
    create_session."""

    def __init__(
        self,
        *,
        known_email: str | None = None,
        valid_password: str | None = None,
        two_factor: bool = False,
        create_should_raise: bool = False,
    ) -> None:
        self._known_email = (known_email or "").strip().lower()
        self._valid_password = valid_password
        self._two_factor = two_factor
        self._create_should_raise = create_should_raise
        self.created_users: list[tuple[str, str, str | None]] = []
        self.created_sessions: list[str] = []

    def authenticate(self, email: str, password: str) -> _StubUser | None:
        if email.strip().lower() == self._known_email and password == self._valid_password:
            return _StubUser(two_factor_enabled=self._two_factor)
        return None

    def get_user_by_email(self, email: str) -> _StubUser | None:
        if email.strip().lower() == self._known_email:
            return _StubUser(two_factor_enabled=self._two_factor)
        return None

    def create_user(self, *, email: str, password: str, username: str | None = None) -> _StubUser:
        if self._create_should_raise:
            raise ValueError("unique-constraint race")
        self.created_users.append((email, password, username))
        return _StubUser(user_id="new-user-999")

    def get_memberships_for_identity(self, identity_id: str) -> list:
        return []  # auth Plan 1b — no memberships in this stub

    def create_session(
        self, user: _StubUser, *, active_membership_id: str | None = None
    ) -> _StubSession:
        sid = f"sess-for-{user.id}"
        self.created_sessions.append(sid)
        return _StubSession(session_id=sid)


def _build_app(
    *,
    chrome: bool,
    password_mode: bool,
    known_email: str | None = None,
    valid_password: str | None = None,
    two_factor: bool = False,
    create_should_raise: bool = False,
) -> tuple[TestClient, _StubAuthStore]:
    app = FastAPI()
    app.state.fragment_chrome = chrome
    app.state.auth_password_mode_enabled = password_mode
    store = _StubAuthStore(
        known_email=known_email,
        valid_password=valid_password,
        two_factor=two_factor,
        create_should_raise=create_should_raise,
    )
    app.state.auth_store = store
    app.include_router(create_auth_page_routes(_MIN_SITESPEC, project_root=None))
    app.include_router(create_password_login_routes())
    return TestClient(app, follow_redirects=False), store


# ───────────────── GET /login flag matrix ────────────────────


def test_get_login_chrome_on_password_mode_renders_password_view() -> None:
    client, _ = _build_app(chrome=True, password_mode=True)
    resp = client.get("/login")
    assert resp.status_code == 200
    body = resp.text
    assert "/auth/login/password" in body
    assert 'type="password"' in body
    # No magic-link form action when password mode is on.
    assert "/auth/login/magic-link" not in body


def test_get_login_chrome_on_password_mode_off_renders_magic_link_view() -> None:
    client, _ = _build_app(chrome=True, password_mode=False)
    resp = client.get("/login")
    assert resp.status_code == 200
    body = resp.text
    assert "/auth/login/magic-link" in body
    assert 'type="password"' not in body


def test_get_login_password_mode_renders_invalid_credentials_error() -> None:
    client, _ = _build_app(chrome=True, password_mode=True)
    resp = client.get("/login?error=invalid_credentials")
    assert resp.status_code == 200
    assert "didn" in resp.text and "match" in resp.text


def test_get_login_password_mode_threads_next_param_into_form() -> None:
    client, _ = _build_app(chrome=True, password_mode=True)
    resp = client.get("/login?next=/app/tasks")
    assert resp.status_code == 200
    assert "next=/app/tasks" in resp.text


# ───────────────── GET /signup flag matrix ────────────────────


def test_get_signup_chrome_on_password_mode_renders_password_view() -> None:
    client, _ = _build_app(chrome=True, password_mode=True)
    resp = client.get("/signup")
    assert resp.status_code == 200
    body = resp.text
    assert "/auth/signup/password" in body
    assert 'name="confirm_password"' in body
    assert "/auth/signup/magic-link" not in body


def test_get_signup_chrome_on_password_mode_off_renders_magic_link_view() -> None:
    client, _ = _build_app(chrome=True, password_mode=False)
    resp = client.get("/signup")
    assert resp.status_code == 200
    body = resp.text
    assert "/auth/signup/magic-link" in body
    assert 'name="confirm_password"' not in body


def test_get_signup_renders_already_registered_error() -> None:
    client, _ = _build_app(chrome=True, password_mode=True)
    resp = client.get("/signup?error=already_registered")
    assert resp.status_code == 200
    assert "already exists" in resp.text


def test_get_signup_renders_mismatch_error() -> None:
    client, _ = _build_app(chrome=True, password_mode=True)
    resp = client.get("/signup?error=mismatch")
    assert resp.status_code == 200
    assert "didn" in resp.text and "match" in resp.text


def test_get_signup_renders_create_failed_error() -> None:
    client, _ = _build_app(chrome=True, password_mode=True)
    resp = client.get("/signup?error=create_failed")
    assert resp.status_code == 200
    assert "couldn" in resp.text


# ───────────────── POST /auth/login/password ────────────────────


def test_post_login_password_valid_creates_session_and_redirects() -> None:
    client, store = _build_app(
        chrome=True,
        password_mode=True,
        known_email="alice@example.com",
        valid_password="hunter2",
    )
    resp = client.post(
        "/auth/login/password",
        data={"email": "alice@example.com", "password": "hunter2"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/app"
    assert "dazzle_session=" in resp.headers.get("set-cookie", "")
    assert store.created_sessions == ["sess-for-user-123"]


def test_post_login_password_invalid_redirects_with_error() -> None:
    client, store = _build_app(
        chrome=True,
        password_mode=True,
        known_email="alice@example.com",
        valid_password="hunter2",
    )
    resp = client.post(
        "/auth/login/password",
        data={"email": "alice@example.com", "password": "wrong"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login?error=invalid_credentials"
    assert store.created_sessions == []
    assert "dazzle_session=" not in resp.headers.get("set-cookie", "")


def test_post_login_password_unknown_email_redirects_with_error() -> None:
    client, _ = _build_app(
        chrome=True,
        password_mode=True,
        known_email="alice@example.com",
        valid_password="hunter2",
    )
    resp = client.post(
        "/auth/login/password",
        data={"email": "bob@example.com", "password": "hunter2"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login?error=invalid_credentials"


def test_post_login_password_threads_next_into_redirect() -> None:
    client, _ = _build_app(
        chrome=True,
        password_mode=True,
        known_email="alice@example.com",
        valid_password="hunter2",
    )
    resp = client.post(
        "/auth/login/password?next=/app/tasks",
        data={"email": "alice@example.com", "password": "hunter2"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/app/tasks"


def test_post_login_password_unsafe_next_falls_back_to_app() -> None:
    client, _ = _build_app(
        chrome=True,
        password_mode=True,
        known_email="alice@example.com",
        valid_password="hunter2",
    )
    resp = client.post(
        "/auth/login/password?next=//evil.com/x",
        data={"email": "alice@example.com", "password": "hunter2"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/app"


def test_post_login_password_invalid_threads_safe_next_into_redirect() -> None:
    """Failed login keeps the safe `next` so the user lands on the
    original page after a successful retry."""
    client, _ = _build_app(
        chrome=True,
        password_mode=True,
        known_email="alice@example.com",
        valid_password="hunter2",
    )
    resp = client.post(
        "/auth/login/password?next=/app/tasks",
        data={"email": "alice@example.com", "password": "wrong"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == ("/login?error=invalid_credentials&next=/app/tasks")


def test_post_login_password_2fa_redirects_to_challenge() -> None:
    client, store = _build_app(
        chrome=True,
        password_mode=True,
        known_email="alice@example.com",
        valid_password="hunter2",
        two_factor=True,
    )
    resp = client.post(
        "/auth/login/password",
        data={"email": "alice@example.com", "password": "hunter2"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"].startswith("/2fa/challenge?session=")
    # Pending session was created.
    assert store.created_sessions == ["sess-for-user-123"]
    # Cookie NOT set on 2FA branch — typed view consumes pending session.
    assert "dazzle_session=" not in resp.headers.get("set-cookie", "")


def test_post_login_password_empty_password_redirects_with_error() -> None:
    client, _ = _build_app(
        chrome=True,
        password_mode=True,
        known_email="alice@example.com",
        valid_password="hunter2",
    )
    resp = client.post(
        "/auth/login/password",
        data={"email": "alice@example.com", "password": ""},
    )
    assert resp.status_code == 303
    assert "invalid_credentials" in resp.headers["location"]


# ───────────────── POST /auth/signup/password ────────────────────


def test_post_signup_password_creates_user_and_session() -> None:
    client, store = _build_app(chrome=True, password_mode=True)
    resp = client.post(
        "/auth/signup/password",
        data={
            "name": "Alice Wong",
            "email": "alice@example.com",
            "password": "hunter2",
            "confirm_password": "hunter2",
        },
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/app"
    assert store.created_users == [("alice@example.com", "hunter2", "Alice Wong")]
    assert "dazzle_session=" in resp.headers.get("set-cookie", "")


def test_post_signup_password_mismatch_redirects_with_error() -> None:
    client, store = _build_app(chrome=True, password_mode=True)
    resp = client.post(
        "/auth/signup/password",
        data={
            "email": "alice@example.com",
            "password": "hunter2",
            "confirm_password": "different",
        },
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/signup?error=mismatch"
    assert store.created_users == []


def test_post_signup_password_existing_email_redirects_with_error() -> None:
    client, store = _build_app(
        chrome=True,
        password_mode=True,
        known_email="alice@example.com",
    )
    resp = client.post(
        "/auth/signup/password",
        data={
            "email": "alice@example.com",
            "password": "hunter2",
            "confirm_password": "hunter2",
        },
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/signup?error=already_registered"
    assert store.created_users == []


def test_post_signup_password_create_failure_redirects_with_error() -> None:
    """A create_user exception (e.g. unique-constraint race) lands
    the user back on /signup with a generic create_failed error."""
    client, store = _build_app(
        chrome=True,
        password_mode=True,
        create_should_raise=True,
    )
    resp = client.post(
        "/auth/signup/password",
        data={
            "email": "alice@example.com",
            "password": "hunter2",
            "confirm_password": "hunter2",
        },
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/signup?error=create_failed"
    assert store.created_sessions == []


def test_post_signup_password_invalid_email_redirects_with_error() -> None:
    client, store = _build_app(chrome=True, password_mode=True)
    resp = client.post(
        "/auth/signup/password",
        data={
            "email": "not-an-email",
            "password": "hunter2",
            "confirm_password": "hunter2",
        },
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/signup?error=invalid_email"
    assert store.created_users == []


def test_post_signup_password_empty_password_treated_as_mismatch() -> None:
    """Both passwords empty would satisfy `==` but the explicit
    emptiness check rejects it — defends against accidental submit."""
    client, store = _build_app(chrome=True, password_mode=True)
    resp = client.post(
        "/auth/signup/password",
        data={
            "email": "alice@example.com",
            "password": "",
            "confirm_password": "",
        },
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/signup?error=mismatch"
    assert store.created_users == []


def test_post_signup_password_threads_safe_next_into_redirect() -> None:
    client, _ = _build_app(chrome=True, password_mode=True)
    resp = client.post(
        "/auth/signup/password?next=/app/tasks",
        data={
            "name": "Alice",
            "email": "alice@example.com",
            "password": "hunter2",
            "confirm_password": "hunter2",
        },
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/app/tasks"


def test_post_signup_password_unsafe_next_falls_back_to_app() -> None:
    client, _ = _build_app(chrome=True, password_mode=True)
    resp = client.post(
        "/auth/signup/password?next=https://evil.com/x",
        data={
            "name": "Alice",
            "email": "alice@example.com",
            "password": "hunter2",
            "confirm_password": "hunter2",
        },
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/app"
