"""Magic-link sign-in and sign-up pages and issuance (#1037 Phase 1.A/1.B).

``/login``, ``/signup`` and ``/login/sent`` are typed-Fragment only since
Phase 1.E (v0.67.33): the ``fragment_chrome`` flag is no longer consulted, so
every page case runs with chrome both on and off. ``POST
/auth/{login,signup}/magic-link`` issues a token, mails it through the
registered ``MagicLinkMailer`` (``LogMailer`` when none is registered) and
always lands on ``/login/sent`` (account-enumeration guard).
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

KNOWN_EMAIL = "alice@example.com"


class _StubMailer:
    """Records every ``send_magic_link`` call."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def send_magic_link(self, *, to_email: str, link_url: str) -> None:
        self.calls.append((to_email, link_url))


class _StubAuthStore:
    """Duck-typed auth store covering what both issuance paths consult."""

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


class _ExplodingStore(_StubAuthStore):
    def create_user(self, **kwargs: object) -> object:
        raise RuntimeError("synthetic failure")


def _build_app(
    *,
    chrome: bool = True,
    known_email: str | None = None,
    mailer: _StubMailer | None = None,
    store: _StubAuthStore | None = None,
) -> tuple[TestClient, _StubAuthStore]:
    app = FastAPI()
    app.state.fragment_chrome = chrome
    auth_store = store if store is not None else _StubAuthStore(known_email=known_email)
    app.state.auth_store = auth_store
    if mailer is not None:
        app.state.magic_link_mailer = mailer
    app.include_router(create_auth_page_routes(_MIN_SITESPEC, project_root=None))
    app.include_router(create_magic_link_routes())
    return TestClient(app, follow_redirects=False), auth_store


# Form body per issuance path; signup also carries the display name.
_FORMS = {
    "login": lambda email: {"email": email},
    "signup": lambda email: {"email": email, "name": "Alice"},
}


# ───────────────── GET pages ────────────────────


@pytest.mark.parametrize("chrome", [True, False], ids=["chrome-on", "chrome-off"])
@pytest.mark.parametrize(
    ("path", "fragments"),
    [
        pytest.param(
            "/login",
            ["<!DOCTYPE html>", "/auth/login/magic-link", "Send sign-in link", ">Sign in</h1>"],
            id="login",
        ),
        pytest.param(
            "/signup",
            [
                "<!DOCTYPE html>",
                "/auth/signup/magic-link",
                'name="name"',
                'name="email"',
                "Send sign-up link",
                ">Sign in</a>",  # crosslink to /login
            ],
            id="signup",
        ),
        pytest.param(
            "/login/sent",
            # "If an account exists" is the account-enumeration-safe default copy.
            ["<!DOCTYPE html>", "Check your inbox", "If an account exists", 'href="/login"'],
            id="login-sent",
        ),
    ],
)
def test_page_renders_typed_view_whatever_the_chrome_flag(
    path: str, fragments: list[str], chrome: bool
) -> None:
    client, _ = _build_app(chrome=chrome)
    resp = client.get(path)
    assert resp.status_code == 200
    for fragment in fragments:
        assert fragment in resp.text


def test_signup_page_has_no_password_field() -> None:
    client, _ = _build_app()
    assert 'type="password"' not in client.get("/signup").text


@pytest.mark.parametrize("path", ["/login", "/signup"])
def test_page_threads_next_param_into_form(path: str) -> None:
    client, _ = _build_app()
    resp = client.get(f"{path}?next=/app/tasks")
    assert resp.status_code == 200
    assert "next=/app/tasks" in resp.text


def test_login_page_renders_invalid_magic_link_error() -> None:
    """A stale or used token redirects to ``?error=invalid_magic_link``."""
    client, _ = _build_app()
    resp = client.get("/login?error=invalid_magic_link")
    assert resp.status_code == 200
    assert "invalid or expired" in resp.text


# ───────────────── POST issuance: shared contract ────────────────────


@pytest.mark.parametrize("flow", ["login", "signup"])
def test_issuance_threads_next_through_redirect_and_link(flow: str) -> None:
    mailer = _StubMailer()
    client, _ = _build_app(known_email=KNOWN_EMAIL, mailer=mailer)
    resp = client.post(f"/auth/{flow}/magic-link?next=/app/tasks", data=_FORMS[flow](KNOWN_EMAIL))
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login/sent?next=/app/tasks"
    assert mailer.calls[0][1].endswith("?next=/app/tasks")


@pytest.mark.parametrize("flow", ["login", "signup"])
@pytest.mark.parametrize(
    "unsafe_next", ["//evil.com/x", "https://evil.com/x"], ids=["protocol-relative", "absolute"]
)
def test_issuance_drops_unsafe_next_from_redirect(flow: str, unsafe_next: str) -> None:
    """Open-redirect guard: an off-site ``next`` never reaches /login/sent."""
    client, _ = _build_app(known_email=KNOWN_EMAIL)
    resp = client.post(
        f"/auth/{flow}/magic-link", params={"next": unsafe_next}, data=_FORMS[flow](KNOWN_EMAIL)
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login/sent"


@pytest.mark.parametrize("flow", ["login", "signup"])
def test_issuance_normalises_email_case_and_whitespace(flow: str) -> None:
    mailer = _StubMailer()
    client, store = _build_app(mailer=mailer, known_email=KNOWN_EMAIL if flow == "login" else None)
    resp = client.post(f"/auth/{flow}/magic-link", data=_FORMS[flow]("  ALICE@EXAMPLE.COM  "))
    assert resp.status_code == 303
    assert len(store.modify_calls) == 1
    assert mailer.calls[0][0] == KNOWN_EMAIL
    if flow == "signup":
        assert store.created_users[0]["email"] == KNOWN_EMAIL


@pytest.mark.parametrize("flow", ["login", "signup"])
def test_issuance_with_empty_email_redirects_without_token_or_mail(flow: str) -> None:
    mailer = _StubMailer()
    client, store = _build_app(known_email=KNOWN_EMAIL, mailer=mailer)
    resp = client.post(f"/auth/{flow}/magic-link", data=_FORMS[flow](""))
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login/sent"
    assert store.modify_calls == []
    assert store.created_users == []
    assert mailer.calls == []


# ───────────────── POST /auth/login/magic-link ────────────────────


def test_login_known_email_inserts_token_and_mails_link() -> None:
    mailer = _StubMailer()
    client, store = _build_app(known_email=KNOWN_EMAIL, mailer=mailer)
    resp = client.post("/auth/login/magic-link", data={"email": KNOWN_EMAIL})
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login/sent"
    [(sql, args)] = store.modify_calls
    assert "INSERT INTO magic_links" in sql
    assert "user-existing" in args
    [(to_email, link_url)] = mailer.calls
    assert to_email == KNOWN_EMAIL
    assert "/auth/magic/" in link_url


def test_login_unknown_email_redirects_identically_without_token() -> None:
    """Account-enumeration guard: same response, no token issued."""
    mailer = _StubMailer()
    client, store = _build_app(known_email=KNOWN_EMAIL, mailer=mailer)
    resp = client.post("/auth/login/magic-link", data={"email": "bob@example.com"})
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login/sent"
    assert store.modify_calls == []
    assert mailer.calls == []


def test_login_falls_back_to_log_mailer_when_none_registered(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, _ = _build_app(known_email=KNOWN_EMAIL)
    with caplog.at_level(logging.INFO):
        client.post("/auth/login/magic-link", data={"email": KNOWN_EMAIL})
    log_text = "\n".join(record.message for record in caplog.records)
    assert f"Magic-link issued for {KNOWN_EMAIL}" in log_text
    assert "/auth/magic/" in log_text


# ───────────────── POST /auth/signup/magic-link ────────────────────


def test_signup_new_email_creates_passwordless_user_and_mails_link() -> None:
    mailer = _StubMailer()
    client, store = _build_app(mailer=mailer)
    resp = client.post("/auth/signup/magic-link", data={"email": KNOWN_EMAIL, "name": "Alice Wong"})
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login/sent"
    [created] = store.created_users
    assert created["email"] == KNOWN_EMAIL
    assert created["username"] == "Alice Wong"
    assert created["password_len"] >= 32  # token_urlsafe(48), never typed by the user
    assert len(store.modify_calls) == 1
    [(to_email, link_url)] = mailer.calls
    assert to_email == KNOWN_EMAIL
    assert "/auth/magic/" in link_url


def test_signup_existing_email_is_treated_as_login() -> None:
    mailer = _StubMailer()
    client, store = _build_app(known_email="existing@example.com", mailer=mailer)
    resp = client.post(
        "/auth/signup/magic-link", data={"email": "existing@example.com", "name": "Whatever"}
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login/sent"
    assert store.created_users == []
    assert len(store.modify_calls) == 1
    assert [call[0] for call in mailer.calls] == ["existing@example.com"]


def test_signup_malformed_email_stays_on_form_without_user_or_mail() -> None:
    """No ``/login/sent`` theater for a malformed address (cycle 2233 / oral #105)."""
    mailer = _StubMailer()
    client, store = _build_app(mailer=mailer)
    resp = client.post(
        "/auth/signup/magic-link", data={"email": "not-an-email", "name": "Whatever"}
    )
    assert resp.status_code == 400
    assert "Invalid email" in resp.text
    assert store.created_users == []
    assert mailer.calls == []


def test_signup_create_user_failure_skips_mail_but_redirects_identically() -> None:
    """A create_user race (e.g. unique violation) is swallowed and logged."""
    mailer = _StubMailer()
    client, _ = _build_app(mailer=mailer, store=_ExplodingStore())
    resp = client.post("/auth/signup/magic-link", data={"email": KNOWN_EMAIL, "name": "Alice"})
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login/sent"
    assert mailer.calls == []
