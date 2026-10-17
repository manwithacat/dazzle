"""Phase 1 of the declarative-CSRF spec: the token is session-bound."""

import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from dazzle.http.runtime.auth.models import SessionRecord


def _session() -> SessionRecord:
    return SessionRecord(
        user_id=uuid4(),
        expires_at=datetime.now(UTC) + timedelta(days=7),
    )


class TestSessionRecordCsrfSecret:
    def test_session_record_has_csrf_secret(self) -> None:
        s = _session()
        assert isinstance(s.csrf_secret, str) and len(s.csrf_secret) >= 32

    def test_csrf_secret_is_unique_per_session(self) -> None:
        assert _session().csrf_secret != _session().csrf_secret


class TestLoginCsrfCookie:
    """The PRIMARY JSON /auth/login handler binds the dazzle_csrf cookie to the
    session secret, and /auth/logout clears it (declarative-CSRF Phase 1, Task 4).

    Driven through the DB-free MagicMock auth-store harness (routes.py takes an
    injected auth_store via _AuthDeps), so these central assertions RUN in the
    fast unit lane — they previously skipped in every CI job because no lane
    provided DATABASE_URL, leaving the core login/logout cookie behavior inert.
    """

    @pytest.fixture
    def setup(self) -> tuple[Any, MagicMock]:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from dazzle.http.runtime.auth import create_auth_routes

        store = _mock_store()
        app = FastAPI()
        app.include_router(create_auth_routes(store))
        return TestClient(app), store

    def _login(self, client: Any, store: MagicMock) -> tuple[Any, Any]:
        """POST /auth/login with valid creds; returns (response, session)."""
        user = _make_user("login@example.com")
        session = _make_session(user, sid="login-session-B")
        store.authenticate.return_value = user
        store.create_session.return_value = session
        response = client.post(
            "/auth/login",
            json={"email": "login@example.com", "password": "password"},
        )
        return response, session

    def test_login_sets_dazzle_csrf_cookie(self, setup: tuple[Any, MagicMock]) -> None:
        """(a) login sets a non-empty dazzle_csrf cookie (>=32 chars)."""
        client, store = setup
        response, _session = self._login(client, store)

        assert response.status_code == 200
        token = response.cookies.get("dazzle_csrf")
        assert isinstance(token, str) and len(token) >= 32

    def test_dazzle_csrf_equals_session_secret(self, setup: tuple[Any, MagicMock]) -> None:
        """(b) the cookie value equals the created session's csrf_secret, not httponly."""
        client, store = setup
        response, session = self._login(client, store)

        header = _csrf_set_cookie(response)
        assert header is not None, "no dazzle_csrf cookie set on JSON login"
        assert f"dazzle_csrf={session.csrf_secret}" in header
        assert "httponly" not in header.lower()
        assert response.cookies.get("dazzle_csrf") == session.csrf_secret

    def test_logout_clears_dazzle_csrf_cookie(self, setup: tuple[Any, MagicMock]) -> None:
        """(c) logout clears the dazzle_csrf cookie."""
        client, store = setup
        login, _session = self._login(client, store)
        assert "dazzle_csrf" in login.cookies

        logout = client.post("/auth/logout")

        # A delete_cookie emits a Set-Cookie with an empty value + past expiry.
        set_cookie_headers = logout.headers.get_list("set-cookie")
        csrf_clears = [h for h in set_cookie_headers if h.startswith("dazzle_csrf=")]
        assert csrf_clears, f"no dazzle_csrf clear header in {set_cookie_headers!r}"
        cleared = csrf_clears[0]
        assert 'dazzle_csrf=""' in cleared or "dazzle_csrf=;" in cleared
        assert "expires=" in cleared.lower() or "max-age=0" in cleared.lower()

    # ---- logout redirect targets (SAML SLO parked in DD-013) ----

    def test_logout_browser_redirects_home(self, setup: tuple[Any, MagicMock]) -> None:
        client, store = setup
        self._login(client, store)
        logout = client.post(
            "/auth/logout", headers={"accept": "text/html"}, follow_redirects=False
        )
        assert logout.status_code == 303
        assert logout.headers["location"] == "/"
        store.delete_session.assert_called_once()

    def test_logout_htmx_uses_hx_redirect_home(self, setup: tuple[Any, MagicMock]) -> None:
        client, store = setup
        self._login(client, store)
        logout = client.post("/auth/logout", headers={"hx-request": "true"})
        assert logout.headers["HX-Redirect"] == "/"


# ---------------------------------------------------------------------------
# Task 4 follow-up: the dazzle_csrf cookie is bound at the form-login,
# magic-link and SSO session sites too (password_login_routes.py et al.). These reuse the MagicMock auth-store harness from
# test_auth_session_fixation.py — no DATABASE_URL needed, and a SessionRecord
# already carries a real csrf_secret via its default_factory.
# ---------------------------------------------------------------------------


def _make_user(email: str = "user@example.com", **kwargs: Any) -> Any:
    from dazzle.http.runtime.auth import UserRecord, hash_password

    return UserRecord(email=email, password_hash=hash_password("password"), **kwargs)


def _make_session(user: Any, sid: str | None = None) -> Any:
    return SessionRecord(
        id=sid or secrets.token_urlsafe(32),
        user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(minutes=60),
    )


def _mock_store() -> MagicMock:
    store = MagicMock()
    store.authenticate.return_value = None
    store.get_user_by_email.return_value = None
    return store


def _csrf_set_cookie(response: Any) -> str | None:
    """Return the dazzle_csrf Set-Cookie header value, or None if absent.

    Reads raw Set-Cookie headers so cookies on a 303 RedirectResponse (which
    httpx does not surface via response.cookies after a non-followed redirect)
    are still observable.
    """
    for header in response.headers.get_list("set-cookie"):
        if header.startswith("dazzle_csrf="):
            return header
    return None


class TestCsrfCookieAtSiblingSites:
    """dazzle_csrf is bound at the form-login fresh-session cookie sites."""

    def _app(self, router: Any, store: MagicMock) -> Any:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        app.state.auth_store = store
        app.include_router(router)
        return TestClient(app, follow_redirects=False)

    # --- password_login_routes.py: form login + signup (303) -------------

    def test_form_login_sets_csrf_from_session(self) -> None:
        from dazzle.http.runtime.auth.password_login_routes import (
            create_password_login_routes,
        )

        store = _mock_store()
        client = self._app(create_password_login_routes(), store)

        user = _make_user("formuser@example.com")
        session = _make_session(user, sid="new-session-B")
        store.authenticate.return_value = user
        store.create_session.return_value = session

        response = client.post(
            "/auth/login/password",
            data={"email": "formuser@example.com", "password": "password"},
        )

        assert response.status_code == 303
        header = _csrf_set_cookie(response)
        assert header is not None, "no dazzle_csrf cookie set on form login"
        assert f"dazzle_csrf={session.csrf_secret}" in header
        assert "httponly" not in header.lower()

    def test_form_signup_sets_csrf_from_session(self) -> None:
        from dazzle.http.runtime.auth.password_login_routes import (
            create_password_login_routes,
        )

        store = _mock_store()
        client = self._app(create_password_login_routes(), store)

        user = _make_user("newform@example.com")
        session = _make_session(user, sid="new-session-B")
        store.get_user_by_email.return_value = None
        store.create_user.return_value = user
        store.create_session.return_value = session

        response = client.post(
            "/auth/signup/password",
            data={
                "email": "newform@example.com",
                "name": "New Form User",
                "password": "password",
                "confirm_password": "password",
            },
        )

        assert response.status_code == 303
        header = _csrf_set_cookie(response)
        assert header is not None, "no dazzle_csrf cookie set on form signup"
        assert f"dazzle_csrf={session.csrf_secret}" in header
        assert "httponly" not in header.lower()

    # --- magic_link_routes.py: magic-link consumption (303) --------------

    def test_magic_link_consume_sets_csrf_from_session(self) -> None:
        from dazzle.http.runtime.auth import magic_link_routes as mlr
        from dazzle.http.runtime.auth.magic_link_routes import (
            create_magic_link_routes,
        )

        store = _mock_store()
        client = self._app(create_magic_link_routes(), store)

        user = _make_user("magic@example.com")
        session = _make_session(user, sid="magic-session-B")
        store.get_user_by_id.return_value = user
        store.create_session.return_value = session

        original_validate = mlr.validate_magic_link
        mlr.validate_magic_link = MagicMock(return_value=user.id)
        try:
            response = client.get("/auth/magic/" + ("A" * 43))
        finally:
            mlr.validate_magic_link = original_validate

        assert response.status_code == 303
        header = _csrf_set_cookie(response)
        assert header is not None, "no dazzle_csrf cookie set on magic-link consume"
        assert f"dazzle_csrf={session.csrf_secret}" in header
        assert "httponly" not in header.lower()

    # --- sso_routes.py: OAuth callback (303) -----------------------------

    def test_sso_callback_sets_csrf_from_session(self) -> None:
        """Drive the SSO callback with a fake OAuth client whose create_session
        returns a real SessionRecord (so .csrf_secret exists). Mirrors the
        proven fake harness in tests/integration/test_sso_routes.py."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from starlette.middleware.sessions import SessionMiddleware

        from dazzle.http.runtime.auth.sso_config import SsoProviderConfig
        from dazzle.http.runtime.auth.sso_routes import create_sso_routes

        user = _make_user("sso@example.com")
        session = _make_session(user, sid="sso-session-B")

        class _SsoStore:
            def get_user_by_email(self, email: str) -> Any:
                return user

            def get_memberships_for_identity(self, identity_id: str) -> list:
                return []  # auth Plan 1b

            def create_session(self, u: Any, **_kwargs: Any) -> Any:
                return session

            def delete_session(self, sid: str) -> None:  # pragma: no cover - unused here
                pass

        class _FakeClient:
            async def authorize_access_token(self, request: Any) -> dict[str, Any]:
                return {"userinfo": {"email": "sso@example.com", "email_verified": True}}

        provider = SsoProviderConfig(
            name="google",
            display_name="Google",
            client_id="id",
            client_secret="secret",
            discovery_url="https://accounts.google.com/.well-known/openid-configuration",
            scopes="openid email profile",
        )

        app = FastAPI()
        app.add_middleware(SessionMiddleware, secret_key="test-secret")
        app.state.sso_providers = (provider,)
        app.state.auth_store = _SsoStore()
        app.state._sso_clients = {"google": _FakeClient()}
        app.include_router(create_sso_routes())
        client = TestClient(app, follow_redirects=False)

        response = client.get("/auth/sso/google/callback?code=" + ("A" * 32))

        assert response.status_code == 303
        header = _csrf_set_cookie(response)
        assert header is not None, "no dazzle_csrf cookie set on SSO callback"
        assert f"dazzle_csrf={session.csrf_secret}" in header
        assert "httponly" not in header.lower()


class TestEverySessionSiteSetsCsrfCookie:
    """Guard: any auth module that writes an auth session cookie (value=session.id)
    MUST also set the session-bound dazzle_csrf cookie. Prevents a new login path
    from silently shipping without CSRF wiring (the #1336/#1337 failure class)."""

    def test_all_browser_session_modules_set_dazzle_csrf(self) -> None:
        import re

        auth_dir = Path(__file__).resolve().parents[2] / "src/dazzle/http/runtime/auth"
        offenders = []
        for py in sorted(auth_dir.glob("*.py")):
            src = py.read_text(encoding="utf-8")
            # A module that sets an auth session cookie from a session id...
            sets_auth_cookie = bool(re.search(r"value=session\.id|value=session_id", src))
            if sets_auth_cookie and "dazzle_csrf" not in src:
                offenders.append(py.name)
        assert not offenders, (
            "These auth modules set an auth session cookie but no session-bound "
            f"dazzle_csrf cookie — CSRF wiring gap: {offenders}"
        )
