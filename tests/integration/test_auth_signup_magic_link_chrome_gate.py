"""Issue #1037 Phase 1.B (v0.67.30): integration tests for the
chrome=on signup magic-link flow + the MagicLinkMailer wiring.

End-to-end coverage:
  1. GET /signup under chrome=on renders the typed-Fragment view
     (zero Jinja Template.render calls).
  2. GET /signup under chrome=off keeps using the legacy Jinja
     template (regression guard).
  3. POST /auth/signup/magic-link creates a passwordless user for
     new emails, treats existing emails as a login attempt
     (account-enumeration friendly UX), and routes the magic link
     through the registered mailer.
  4. Custom-registered MagicLinkMailer wins over the LogMailer
     default for both /login and /signup paths.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

pytest.importorskip("dazzle.http.runtime.site_routes")
from dazzle.http.runtime.auth.magic_link_routes import (  # noqa: E402
    create_magic_link_routes,
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


class _StubMailer:
    """Records every send_magic_link call so tests can assert on
    the exact email / link delivery."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def send_magic_link(self, *, to_email: str, link_url: str) -> None:
        self.calls.append((to_email, link_url))


class _StubAuthStore:
    """Minimal auth store covering the methods both /login and
    /signup magic-link issuance paths consult."""

    def __init__(self, *, known_email: str | None = None) -> None:
        self._known_email = (known_email or "").strip().lower()
        self.modify_calls: list[tuple[str, tuple]] = []
        self.created_users: list[dict] = []

    def get_user_by_email(self, email: str) -> object | None:
        if email.strip().lower() == self._known_email:
            user = MagicMock()
            user.id = "user-existing"
            return user
        return None

    def get_user_by_id(self, user_id: str) -> object | None:
        return None

    def create_user(
        self,
        *,
        email: str,
        password: str,
        username: str | None = None,
        is_superuser: bool = False,
        roles: list[str] | None = None,
    ) -> object:
        self.created_users.append(
            {"email": email, "username": username, "password_len": len(password)}
        )
        user = MagicMock()
        user.id = f"user-new-{len(self.created_users)}"
        return user

    def _execute_modify(self, sql: str, args: tuple) -> None:
        self.modify_calls.append((sql, args))

    def _execute(self, sql: str, args: tuple) -> list:
        return []


def _build_app(
    *,
    chrome: bool,
    known_email: str | None = None,
    mailer: object | None = None,
) -> tuple[TestClient, _StubAuthStore, _StubMailer | None]:
    app = FastAPI()
    app.state.fragment_chrome = chrome
    auth_store = _StubAuthStore(known_email=known_email)
    app.state.auth_store = auth_store
    actual_mailer: _StubMailer | None = None
    if mailer is not None:
        app.state.magic_link_mailer = mailer
        if isinstance(mailer, _StubMailer):
            actual_mailer = mailer
    app.include_router(create_auth_page_routes(_MIN_SITESPEC, project_root=None))
    app.include_router(create_magic_link_routes())
    return TestClient(app, follow_redirects=False), auth_store, actual_mailer


# ───────────────── GET /signup chrome gate ────────────────────


def test_get_signup_chrome_on_renders_typed_view_no_jinja() -> None:
    client, _, _ = _build_app(chrome=True)
    resp = client.get("/signup")
    assert resp.status_code == 200
    body = resp.text
    assert "<!DOCTYPE html>" in body
    assert "/auth/signup/magic-link" in body
    assert 'name="name"' in body
    assert 'name="email"' in body
    assert 'type="password"' not in body  # magic-link mode, no password
    assert "Send sign-up link" in body
    assert ">Sign in</a>" in body  # crosslink to /login


def test_get_signup_chrome_off_now_also_renders_typed_view() -> None:
    """Phase 1.E (v0.67.33): /signup is typed-only — chrome flag
    no longer gates the render."""
    client, _, _ = _build_app(chrome=False)
    resp = client.get("/signup")
    assert resp.status_code == 200
    assert "/auth/signup/magic-link" in resp.text


def test_get_signup_threads_next_param() -> None:
    client, _, _ = _build_app(chrome=True)
    resp = client.get("/signup?next=/onboarding")
    assert resp.status_code == 200
    assert "next=/onboarding" in resp.text


# ───────────────── POST /auth/signup/magic-link ────────────────────


def test_post_signup_new_email_creates_passwordless_user() -> None:
    mailer = _StubMailer()
    client, store, _ = _build_app(chrome=True, mailer=mailer)
    resp = client.post(
        "/auth/signup/magic-link",
        data={"email": "alice@example.com", "name": "Alice Wong"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login/sent"
    # User created with the supplied name + a long random password.
    assert len(store.created_users) == 1
    created = store.created_users[0]
    assert created["email"] == "alice@example.com"
    assert created["username"] == "Alice Wong"
    assert created["password_len"] >= 32  # token_urlsafe(48) ≈ 64 chars
    # Magic link issued + mailer called.
    assert len(store.modify_calls) == 1
    assert len(mailer.calls) == 1
    to_email, link_url = mailer.calls[0]
    assert to_email == "alice@example.com"
    assert "/auth/magic/" in link_url


def test_post_signup_existing_email_treats_as_login() -> None:
    """Friendly UX: existing user gets a sign-in link instead of an
    error. No new user record created."""
    mailer = _StubMailer()
    client, store, _ = _build_app(chrome=True, known_email="existing@example.com", mailer=mailer)
    resp = client.post(
        "/auth/signup/magic-link",
        data={"email": "existing@example.com", "name": "Whatever"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login/sent"
    # No new user — existing one was found.
    assert store.created_users == []
    # Magic link still issued + mailed.
    assert len(store.modify_calls) == 1
    assert len(mailer.calls) == 1
    to_email, link_url = mailer.calls[0]
    assert to_email == "existing@example.com"


def test_post_signup_malformed_email_redirects_no_user_no_mail() -> None:
    """Account-enumeration guard parity: same redirect, no user
    created, no mailer call."""
    mailer = _StubMailer()
    client, store, _ = _build_app(chrome=True, mailer=mailer)
    resp = client.post(
        "/auth/signup/magic-link",
        data={"email": "not-an-email", "name": "Whatever"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login/sent"
    assert store.created_users == []
    assert mailer.calls == []


def test_post_signup_empty_email_redirects_no_user_no_mail() -> None:
    mailer = _StubMailer()
    client, store, _ = _build_app(chrome=True, mailer=mailer)
    resp = client.post(
        "/auth/signup/magic-link",
        data={"email": "", "name": "Whatever"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login/sent"
    assert store.created_users == []
    assert mailer.calls == []


def test_post_signup_threads_next_param_through_redirect() -> None:
    mailer = _StubMailer()
    client, _, _ = _build_app(chrome=True, mailer=mailer)
    resp = client.post(
        "/auth/signup/magic-link?next=/onboarding",
        data={"email": "alice@example.com", "name": "Alice"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login/sent?next=/onboarding"
    # next param also threaded into the magic-link URL.
    assert mailer.calls[0][1].endswith("?next=/onboarding")


def test_post_signup_normalises_email_case() -> None:
    mailer = _StubMailer()
    client, store, _ = _build_app(chrome=True, mailer=mailer)
    resp = client.post(
        "/auth/signup/magic-link",
        data={"email": "  ALICE@EXAMPLE.COM  ", "name": "Alice"},
    )
    assert resp.status_code == 303
    assert store.created_users[0]["email"] == "alice@example.com"


def test_post_signup_create_user_failure_skips_mailer_call() -> None:
    """If the auth store's create_user raises (e.g. unique
    constraint violation in a race), the issuance path swallows
    the exception, logs, and skips the mailer call. The user
    still gets the same /login/sent redirect."""

    class _ExplodingStore(_StubAuthStore):
        def create_user(self, **kwargs) -> object:
            raise RuntimeError("synthetic failure")

    mailer = _StubMailer()
    app = FastAPI()
    app.state.fragment_chrome = True
    app.state.auth_store = _ExplodingStore()
    app.state.magic_link_mailer = mailer
    app.include_router(create_auth_page_routes(_MIN_SITESPEC, project_root=None))
    app.include_router(create_magic_link_routes())
    client = TestClient(app, follow_redirects=False)

    resp = client.post(
        "/auth/signup/magic-link",
        data={"email": "alice@example.com", "name": "Alice"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login/sent"
    assert mailer.calls == []  # mailer skipped — user creation failed


# ───────────────── Mailer wiring on /login + /signup ────────────────────


def test_login_uses_registered_mailer_not_log_default() -> None:
    """/login issuance uses `app.state.magic_link_mailer` when set."""
    mailer = _StubMailer()
    client, _, _ = _build_app(chrome=True, known_email="alice@example.com", mailer=mailer)
    client.post("/auth/login/magic-link", data={"email": "alice@example.com"})
    assert len(mailer.calls) == 1
    assert mailer.calls[0][0] == "alice@example.com"


def test_login_falls_back_to_log_mailer_when_unregistered(caplog) -> None:
    """When `app.state.magic_link_mailer` is unset, LogMailer fires."""
    import logging

    client, _, _ = _build_app(chrome=True, known_email="alice@example.com")
    with caplog.at_level(logging.INFO):
        client.post("/auth/login/magic-link", data={"email": "alice@example.com"})
    log_text = "\n".join(record.message for record in caplog.records)
    assert "Magic-link issued for alice@example.com" in log_text
    assert "/auth/magic/" in log_text
