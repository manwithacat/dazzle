"""Issue #1037 Phase 1.A (v0.67.29): integration tests for the
chrome=on magic-link login flow.

End-to-end coverage:
  1. GET /login under chrome=on renders the typed-Fragment view.
  2. GET /login under chrome=off keeps using the legacy Jinja
     template (regression guard against breaking non-flipped
     deployments).
  3. POST /auth/login/magic-link issues a token (logged at INFO
     level) and redirects to /login/sent — same response whether
     the email matches a user or not (account-enumeration guard).
  4. GET /login/sent renders the typed confirmation page.
"""

from __future__ import annotations

import logging
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


class _StubAuthStore:
    """Minimal duck-typed auth store covering `get_user_by_email` +
    `_execute_modify` (the two methods the magic-link issuance path
    consults). Records what was inserted so tests can assert on it."""

    def __init__(self, *, known_email: str | None = None) -> None:
        self._known_email = (known_email or "").strip().lower()
        self.modify_calls: list[tuple[str, tuple]] = []
        self.execute_calls: list[tuple[str, tuple]] = []

    def get_user_by_email(self, email: str) -> object | None:
        if email.strip().lower() == self._known_email:
            user = MagicMock()
            user.id = "user-123"
            return user
        return None

    def get_user_by_id(self, user_id: str) -> object | None:
        return None

    def _execute_modify(self, sql: str, args: tuple) -> None:
        self.modify_calls.append((sql, args))

    def _execute(self, sql: str, args: tuple) -> list:
        self.execute_calls.append((sql, args))
        return []


def _build_app(
    *, chrome: bool, known_email: str | None = None
) -> tuple[TestClient, _StubAuthStore]:
    app = FastAPI()
    app.state.fragment_chrome = chrome
    auth_store = _StubAuthStore(known_email=known_email)
    app.state.auth_store = auth_store
    app.include_router(create_auth_page_routes(_MIN_SITESPEC, project_root=None))
    app.include_router(create_magic_link_routes())
    return TestClient(app, follow_redirects=False), auth_store


# ───────────────── GET /login chrome gate ────────────────────


def test_get_login_chrome_on_renders_typed_view_no_jinja() -> None:
    client, _ = _build_app(chrome=True)
    resp = client.get("/login")
    assert resp.status_code == 200
    body = resp.text
    # Typed view markers.
    assert "<!DOCTYPE html>" in body
    assert "/auth/login/magic-link" in body
    assert "Send sign-in link" in body
    assert "<h1" in body and ">Sign in</h1>" in body


def test_get_login_chrome_off_now_also_renders_typed_view() -> None:
    """Phase 1.E (v0.67.33): `/login` is typed-Fragment ONLY — the
    chrome flag is no longer consulted. This test guards against
    accidental re-introduction of a Jinja fallback."""
    client, _ = _build_app(chrome=False)
    resp = client.get("/login")
    assert resp.status_code == 200
    assert "/auth/login/magic-link" in resp.text


def test_get_login_threads_next_param() -> None:
    """`?next=/app/tasks` is preserved through the typed render so
    the magic-link form posts with the correct return target."""
    client, _ = _build_app(chrome=True)
    resp = client.get("/login?next=/app/tasks")
    assert resp.status_code == 200
    assert "next=/app/tasks" in resp.text


def test_get_login_renders_invalid_magic_link_error() -> None:
    """When the consumer endpoint redirects here with
    ?error=invalid_magic_link (after a stale or already-used
    token), the typed view shows a friendly error message."""
    client, _ = _build_app(chrome=True)
    resp = client.get("/login?error=invalid_magic_link")
    assert resp.status_code == 200
    assert "invalid or expired" in resp.text


# ───────────────── POST /auth/login/magic-link ────────────────────


def test_post_magic_link_known_email_creates_token_and_redirects() -> None:
    client, store = _build_app(chrome=True, known_email="alice@example.com")
    resp = client.post(
        "/auth/login/magic-link",
        data={"email": "alice@example.com"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login/sent"
    # Token created via _execute_modify.
    assert len(store.modify_calls) == 1
    sql, args = store.modify_calls[0]
    assert "INSERT INTO magic_links" in sql
    # user_id placeholder appears in the args.
    assert "user-123" in args


def test_post_magic_link_unknown_email_redirects_same_no_token() -> None:
    """Account-enumeration guard: same response whether the email
    matches a real user or not. No token issued for unknown."""
    client, store = _build_app(chrome=True, known_email="alice@example.com")
    resp = client.post(
        "/auth/login/magic-link",
        data={"email": "bob@example.com"},  # not registered
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login/sent"
    assert store.modify_calls == []  # no token issued


def test_post_magic_link_empty_email_redirects_same_no_token() -> None:
    client, store = _build_app(chrome=True, known_email="alice@example.com")
    resp = client.post("/auth/login/magic-link", data={"email": ""})
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login/sent"
    assert store.modify_calls == []


def test_post_magic_link_threads_next_param_through_redirect() -> None:
    client, _ = _build_app(chrome=True, known_email="alice@example.com")
    resp = client.post(
        "/auth/login/magic-link?next=/app/tasks",
        data={"email": "alice@example.com"},
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login/sent?next=/app/tasks"


def test_post_magic_link_logs_link_url_for_dev_pickup(caplog) -> None:
    """Real email send is a follow-on ship; for now the issuance
    path logs the link URL at INFO level so dev environments can
    copy-paste from the server log."""
    client, _ = _build_app(chrome=True, known_email="alice@example.com")
    with caplog.at_level(logging.INFO):
        client.post(
            "/auth/login/magic-link",
            data={"email": "alice@example.com"},
        )
    # The log message includes the magic-link URL.
    log_text = "\n".join(record.message for record in caplog.records)
    assert "/auth/magic/" in log_text
    assert "alice@example.com" in log_text


def test_post_magic_link_normalises_email_case() -> None:
    """Input is lowercased + stripped before the auth store
    lookup — common-case typo guard."""
    client, store = _build_app(chrome=True, known_email="alice@example.com")
    resp = client.post(
        "/auth/login/magic-link",
        data={"email": "  ALICE@EXAMPLE.COM  "},
    )
    assert resp.status_code == 303
    assert len(store.modify_calls) == 1


def test_post_magic_link_unsafe_next_url_dropped() -> None:
    """`next` validation reuses `_is_safe_redirect_path` — protocol-
    relative or scheme-prefixed values are dropped from the
    /login/sent redirect."""
    client, _ = _build_app(chrome=True, known_email="alice@example.com")
    resp = client.post(
        "/auth/login/magic-link?next=//evil.com/x",
        data={"email": "alice@example.com"},
    )
    assert resp.status_code == 303
    # /login/sent without the unsafe next param.
    assert resp.headers["location"] == "/login/sent"


# ───────────────── GET /login/sent ────────────────────


def test_get_login_sent_chrome_on_renders_typed_view() -> None:
    client, _ = _build_app(chrome=True)
    resp = client.get("/login/sent")
    assert resp.status_code == 200
    body = resp.text
    assert "Check your inbox" in body
    assert "If an account exists" in body  # account-enumeration safe default
    assert 'href="/login"' in body


def test_get_login_sent_chrome_off_also_renders_typed_view() -> None:
    """Phase 1.E (v0.67.33): the minimal HTML fallback is gone —
    the typed view is the only path."""
    client, _ = _build_app(chrome=False)
    resp = client.get("/login/sent")
    assert resp.status_code == 200
    body = resp.text
    assert "Check your inbox" in body
    # Typed-view markers absent from the old minimal-HTML fallback.
    assert "<!DOCTYPE html>" in body
    assert 'href="/login"' in body
