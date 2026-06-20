"""Phase 1.B.2 (v0.67.31): integration tests for the typed-Fragment
forgot/reset chrome gates and their form-encoded submit endpoints.

Coverage:
  1. GET /forgot-password chrome=on renders the typed view; chrome=off
     keeps the legacy Jinja path.
  2. POST /auth/forgot-password/submit issues a reset token via the
     auth store, dispatches a mailer notification, and redirects to
     /forgot-password/sent — same response whether the email matches
     a real user or not (account-enumeration guard).
  3. GET /reset-password threads `?token=` into the form's hidden
     token field; `?error=mismatch` / `?error=invalid` render
     friendly error messages.
  4. POST /auth/reset-password/submit consumes the token, updates
     the password, redirects to /reset-password/done. Mismatched
     password fields redirect back with `?error=mismatch`; an
     invalid/expired token redirects with `?error=invalid`.
  5. GET /forgot-password/sent + /reset-password/done render their
     typed confirmation pages under chrome=on and minimal HTML
     fallbacks under chrome=off.
"""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytest.importorskip("dazzle.http.runtime.site_routes")
from dazzle.http.runtime.auth.password_reset_routes import (  # noqa: E402
    create_password_reset_routes,
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


class _StubUser:
    def __init__(self, user_id: str = "user-123", is_active: bool = True) -> None:
        self.id = user_id
        self.is_active = is_active


class _StubAuthStore:
    """Minimal auth-store stub exposing the four methods the
    password-reset endpoints call: get_user_by_email,
    create_password_reset_token, validate_password_reset_token,
    consume_password_reset_token, update_password, delete_user_sessions."""

    def __init__(
        self,
        *,
        known_email: str | None = None,
        valid_token: str | None = None,
        active: bool = True,
    ) -> None:
        self._known_email = (known_email or "").strip().lower()
        self._valid_token = valid_token
        self._active = active
        self.created_tokens: list[str] = []
        self.consumed_tokens: list[str] = []
        self.updated_passwords: list[tuple[str, str]] = []
        self.deleted_sessions: list[str] = []

    def get_user_by_email(self, email: str) -> _StubUser | None:
        if email.strip().lower() == self._known_email:
            return _StubUser(is_active=self._active)
        return None

    def create_password_reset_token(self, user_id: str) -> str:
        token = f"reset-token-for-{user_id}"
        self.created_tokens.append(token)
        return token

    def validate_password_reset_token(self, token: str) -> _StubUser | None:
        if token and token == self._valid_token:
            return _StubUser()
        return None

    def consume_password_reset_token(self, token: str) -> None:
        self.consumed_tokens.append(token)

    def update_password(self, user_id: str, new_password: str) -> None:
        self.updated_passwords.append((user_id, new_password))

    def delete_user_sessions(self, user_id: str) -> None:
        self.deleted_sessions.append(user_id)


def _build_app(
    *,
    chrome: bool,
    known_email: str | None = None,
    valid_token: str | None = None,
    active: bool = True,
) -> tuple[TestClient, _StubAuthStore]:
    app = FastAPI()
    app.state.fragment_chrome = chrome
    auth_store = _StubAuthStore(
        known_email=known_email,
        valid_token=valid_token,
        active=active,
    )
    app.state.auth_store = auth_store
    app.include_router(create_auth_page_routes(_MIN_SITESPEC, project_root=None))
    app.include_router(create_password_reset_routes())
    return TestClient(app, follow_redirects=False), auth_store


# ───────────────── GET /forgot-password chrome gate ────────────────────


def test_get_forgot_password_chrome_on_renders_typed_view() -> None:
    client, _ = _build_app(chrome=True)
    resp = client.get("/forgot-password")
    assert resp.status_code == 200
    body = resp.text
    assert "<!DOCTYPE html>" in body
    assert "/auth/forgot-password/submit" in body
    assert "Send reset link" in body
    assert 'type="email"' in body
    assert 'type="password"' not in body  # account-recovery, not login


def test_get_forgot_password_chrome_off_now_also_renders_typed_view() -> None:
    """Phase 1.E (v0.67.33): typed-only — chrome flag no longer
    consulted at /forgot-password."""
    client, _ = _build_app(chrome=False)
    resp = client.get("/forgot-password")
    assert resp.status_code == 200
    assert "/auth/forgot-password/submit" in resp.text


# ───────────────── POST /auth/forgot-password/submit ────────────────────


def test_post_forgot_password_known_email_issues_token_and_redirects() -> None:
    client, store = _build_app(chrome=True, known_email="alice@example.com")
    resp = client.post(
        "/auth/forgot-password/submit",
        data={"email": "alice@example.com"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/forgot-password/sent"
    assert store.created_tokens == ["reset-token-for-user-123"]


def test_post_forgot_password_unknown_email_redirects_same_no_token() -> None:
    """Account-enumeration guard: same redirect whether the email
    matches or not. No token issued for unknown email."""
    client, store = _build_app(chrome=True, known_email="alice@example.com")
    resp = client.post(
        "/auth/forgot-password/submit",
        data={"email": "bob@example.com"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/forgot-password/sent"
    assert store.created_tokens == []


def test_post_forgot_password_inactive_user_no_token() -> None:
    """Inactive users are treated like unknown — no token issued."""
    client, store = _build_app(
        chrome=True,
        known_email="alice@example.com",
        active=False,
    )
    resp = client.post(
        "/auth/forgot-password/submit",
        data={"email": "alice@example.com"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/forgot-password/sent"
    assert store.created_tokens == []


def test_post_forgot_password_empty_email_no_token() -> None:
    client, store = _build_app(chrome=True, known_email="alice@example.com")
    resp = client.post("/auth/forgot-password/submit", data={"email": ""})
    assert resp.status_code == 303
    assert resp.headers["location"] == "/forgot-password/sent"
    assert store.created_tokens == []


def test_post_forgot_password_normalises_email_case() -> None:
    client, store = _build_app(chrome=True, known_email="alice@example.com")
    resp = client.post(
        "/auth/forgot-password/submit",
        data={"email": "  ALICE@EXAMPLE.COM  "},
    )
    assert resp.status_code == 303
    assert store.created_tokens == ["reset-token-for-user-123"]


def test_post_forgot_password_logs_reset_link_for_dev_pickup(caplog) -> None:
    """When no real mailer is wired, the default LogMailer emits the
    reset URL at INFO level for dev pickup (mirrors magic-link
    behaviour in Phase 1.A/B)."""
    client, _ = _build_app(chrome=True, known_email="alice@example.com")
    with caplog.at_level(logging.INFO):
        client.post(
            "/auth/forgot-password/submit",
            data={"email": "alice@example.com"},
        )
    log_text = "\n".join(record.message for record in caplog.records)
    assert "/reset-password?token=reset-token-for-user-123" in log_text


# ───────────────── GET /reset-password ────────────────────


def test_get_reset_password_chrome_on_renders_typed_view_with_token() -> None:
    client, _ = _build_app(chrome=True)
    resp = client.get("/reset-password?token=abc123")
    assert resp.status_code == 200
    body = resp.text
    assert "/auth/reset-password/submit" in body
    # Token threaded into hidden field.
    assert 'value="abc123"' in body
    assert body.count('type="password"') == 2


def test_get_reset_password_renders_mismatch_error() -> None:
    client, _ = _build_app(chrome=True)
    resp = client.get("/reset-password?token=abc&error=mismatch")
    assert resp.status_code == 200
    assert "didn" in resp.text and "match" in resp.text


def test_get_reset_password_renders_invalid_token_error() -> None:
    client, _ = _build_app(chrome=True)
    resp = client.get("/reset-password?error=invalid")
    assert resp.status_code == 200
    assert "invalid or expired" in resp.text


def test_get_reset_password_chrome_off_now_also_renders_typed_view() -> None:
    """Phase 1.E (v0.67.33): typed-only — chrome flag no longer
    consulted at /reset-password."""
    client, _ = _build_app(chrome=False)
    resp = client.get("/reset-password")
    assert resp.status_code == 200
    assert "/auth/reset-password/submit" in resp.text


# ───────────────── POST /auth/reset-password/submit ────────────────────


def test_post_reset_password_success_updates_password_and_redirects() -> None:
    client, store = _build_app(chrome=True, valid_token="good-token")
    resp = client.post(
        "/auth/reset-password/submit",
        data={
            "token": "good-token",
            "new_password": "newpass123",
            "confirm_password": "newpass123",
        },
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/reset-password/done"
    assert store.updated_passwords == [("user-123", "newpass123")]
    assert store.consumed_tokens == ["good-token"]
    assert store.deleted_sessions == ["user-123"]


def test_post_reset_password_mismatched_redirects_back_with_error() -> None:
    """Server-side mismatch check — the typed form has no JS, so the
    server is the source of truth for password-field equality."""
    client, store = _build_app(chrome=True, valid_token="good-token")
    resp = client.post(
        "/auth/reset-password/submit",
        data={
            "token": "good-token",
            "new_password": "newpass123",
            "confirm_password": "different",
        },
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/reset-password?token=good-token&error=mismatch"
    assert store.updated_passwords == []
    assert store.consumed_tokens == []


def test_post_reset_password_invalid_token_redirects_with_error() -> None:
    client, store = _build_app(chrome=True, valid_token="good-token")
    resp = client.post(
        "/auth/reset-password/submit",
        data={
            "token": "bad-token",
            "new_password": "newpass123",
            "confirm_password": "newpass123",
        },
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/reset-password?error=invalid"
    assert store.updated_passwords == []
    assert store.consumed_tokens == []


def test_post_reset_password_empty_password_redirects_with_mismatch() -> None:
    """Empty new_password falls into the mismatch branch (both
    sides empty satisfies `==`, but the explicit emptiness check
    rejects it). Defends against a JS-disabled accidental submit."""
    client, store = _build_app(chrome=True, valid_token="good-token")
    resp = client.post(
        "/auth/reset-password/submit",
        data={
            "token": "good-token",
            "new_password": "",
            "confirm_password": "",
        },
    )
    assert resp.status_code == 303
    assert "/reset-password" in resp.headers["location"]
    assert "error=mismatch" in resp.headers["location"]
    assert store.updated_passwords == []


# ───────────────── confirmation pages ────────────────────


def test_get_forgot_password_sent_chrome_on_renders_typed_view() -> None:
    client, _ = _build_app(chrome=True)
    resp = client.get("/forgot-password/sent")
    assert resp.status_code == 200
    body = resp.text
    assert "Check your inbox" in body
    assert "If an account exists" in body  # account-enumeration safe


def test_get_forgot_password_sent_chrome_off_also_renders_typed_view() -> None:
    """Phase 1.E (v0.67.33): minimal HTML fallback gone — typed view
    is the only path."""
    client, _ = _build_app(chrome=False)
    resp = client.get("/forgot-password/sent")
    assert resp.status_code == 200
    body = resp.text
    assert "Check your inbox" in body
    assert "<!DOCTYPE html>" in body


def test_get_reset_password_done_chrome_on_renders_typed_view() -> None:
    client, _ = _build_app(chrome=True)
    resp = client.get("/reset-password/done")
    assert resp.status_code == 200
    body = resp.text
    assert "Password updated" in body
    assert 'href="/login"' in body


def test_get_reset_password_done_chrome_off_also_renders_typed_view() -> None:
    """Phase 1.E (v0.67.33): minimal HTML fallback gone — typed view
    is the only path."""
    client, _ = _build_app(chrome=False)
    resp = client.get("/reset-password/done")
    assert resp.status_code == 200
    body = resp.text
    assert "Password updated" in body
    assert "<!DOCTYPE html>" in body
