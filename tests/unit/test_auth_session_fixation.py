"""
Session-fixation defence tests (#1198).

OWASP A07:2021 — on every login-success path the framework regenerates the
session id and invalidates the pre-auth session cookie the client presented,
so an attacker-planted id can't survive into the authenticated state.

These tests pin the regenerate-on-login behaviour at every login-success
call site we care about:

  * `_login` (JSON, non-2FA) in routes.py
  * `_register` in routes.py
  * `_verify_2fa` (final 2FA verification) in routes_2fa.py
  * `submit_login_password` (form-encoded) in password_login_routes.py
  * `submit_signup_password` (form-encoded) in password_login_routes.py
  * `consume_magic_link` in magic_link_routes.py
  * `submit_2fa_verify` (form-encoded) in two_factor_form_routes.py

Each scenario covers:

  1. Pre-auth id is deleted when a different id is minted.
  2. Other devices' sessions for the same user are preserved — distinguishes
     this defence from the rejected `delete_user_sessions(user.id)` variant.
  3. No-op when no pre-auth cookie was sent — never calls delete_session.
"""

import secrets
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle.http.runtime.auth import (
    AuthContext,
    SessionRecord,
    UserRecord,
    create_2fa_routes,
    create_auth_routes,
    hash_password,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


@contextmanager
def _mock_totp_module(verify_return: bool) -> Iterator[MagicMock]:
    """Inject a mock `dazzle.http.runtime.totp` so verify_2fa can run."""
    mock_module = MagicMock()
    mock_module.verify_totp = MagicMock(return_value=verify_return)
    key = "dazzle.http.runtime.totp"
    original = sys.modules.get(key)
    sys.modules[key] = mock_module
    try:
        yield mock_module
    finally:
        if original is None:
            sys.modules.pop(key, None)
        else:
            sys.modules[key] = original


def _make_user(email: str = "user@example.com", **kwargs: Any) -> UserRecord:
    return UserRecord(
        email=email,
        password_hash=hash_password("password"),
        **kwargs,
    )


def _make_session(user: UserRecord, sid: str | None = None, minutes: int = 60) -> SessionRecord:
    return SessionRecord(
        id=sid or secrets.token_urlsafe(32),
        user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(minutes=minutes),
    )


def _make_auth_context(user: UserRecord, session: SessionRecord) -> AuthContext:
    return AuthContext(
        user=user,
        session=session,
        is_authenticated=True,
        roles=user.roles,
    )


def _build_mock_auth_store() -> MagicMock:
    """MagicMock that quacks like AuthStore for route-level tests."""
    store = MagicMock()
    store.authenticate.return_value = None
    store.get_user_by_email.return_value = None
    return store


# ---------------------------------------------------------------------------
# 1. JSON _login (non-2FA) — routes.py
# ---------------------------------------------------------------------------


class TestJsonLoginRegenerate:
    """`/auth/login` regenerates the session id and deletes the pre-auth id."""

    @pytest.fixture
    def setup(self) -> tuple[Any, MagicMock]:
        mock_store = _build_mock_auth_store()
        app = FastAPI()
        app.include_router(create_auth_routes(mock_store))
        return TestClient(app), mock_store

    def test_pre_auth_sid_is_invalidated(self, setup: tuple[Any, MagicMock]) -> None:
        client, mock_store = setup
        user = _make_user("login@example.com")
        new_session = _make_session(user, sid="new-session-B")

        mock_store.authenticate.return_value = user
        mock_store.create_session.return_value = new_session

        # Plant a pre-auth session id in the cookie jar.
        client.cookies.set("dazzle_session", "planted-session-A")

        response = client.post(
            "/auth/login",
            json={"email": "login@example.com", "password": "password"},
        )

        assert response.status_code == 200
        # The pre-auth id was deleted.
        mock_store.delete_session.assert_called_once_with("planted-session-A")
        # The response cookie carries the *new* id, not the planted one.
        assert response.cookies.get("dazzle_session") == "new-session-B"

    def test_other_device_session_preserved(self, setup: tuple[Any, MagicMock]) -> None:
        """Regenerate (not delete_user_sessions) — other devices stay logged in."""
        client, mock_store = setup
        user = _make_user("login@example.com")
        new_session = _make_session(user, sid="new-session-B")

        mock_store.authenticate.return_value = user
        mock_store.create_session.return_value = new_session

        client.cookies.set("dazzle_session", "planted-session-A")
        response = client.post(
            "/auth/login",
            json={"email": "login@example.com", "password": "password"},
        )

        assert response.status_code == 200
        # Only the pre-auth id was deleted — not all user sessions.
        mock_store.delete_user_sessions.assert_not_called()
        # delete_session was called exactly once, for the pre-auth id only.
        mock_store.delete_session.assert_called_once_with("planted-session-A")

    def test_no_pre_auth_cookie_is_noop(self, setup: tuple[Any, MagicMock]) -> None:
        client, mock_store = setup
        user = _make_user("login@example.com")
        new_session = _make_session(user, sid="new-session-B")

        mock_store.authenticate.return_value = user
        mock_store.create_session.return_value = new_session

        # No cookie planted.
        response = client.post(
            "/auth/login",
            json={"email": "login@example.com", "password": "password"},
        )

        assert response.status_code == 200
        mock_store.delete_session.assert_not_called()

    def test_pending_2fa_session_does_not_invalidate_pre_auth(
        self, setup: tuple[Any, MagicMock]
    ) -> None:
        """The pending 2FA session is not a real auth session — pre-auth must
        stay alive until *final* 2FA verification."""
        client, mock_store = setup
        user = _make_user("login@example.com", totp_enabled=True)
        pending = _make_session(user, sid="pending-2fa", minutes=10)

        mock_store.authenticate.return_value = user
        mock_store.create_session.return_value = pending

        client.cookies.set("dazzle_session", "planted-session-A")
        response = client.post(
            "/auth/login",
            json={"email": "login@example.com", "password": "password"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "2fa_required"
        # Crucially: the pre-auth id is NOT deleted at this step.
        mock_store.delete_session.assert_not_called()


# ---------------------------------------------------------------------------
# 2. JSON _register — routes.py
# ---------------------------------------------------------------------------


class TestRegisterRegenerate:
    """`/auth/register` regenerates the session id and deletes the pre-auth id."""

    @pytest.fixture
    def setup(self) -> tuple[Any, MagicMock]:
        mock_store = _build_mock_auth_store()
        app = FastAPI()
        app.include_router(create_auth_routes(mock_store))
        return TestClient(app), mock_store

    def test_pre_auth_sid_invalidated_on_register(self, setup: tuple[Any, MagicMock]) -> None:
        client, mock_store = setup
        user = _make_user("new@example.com")
        new_session = _make_session(user, sid="new-session-B")

        mock_store.get_user_by_email.return_value = None
        mock_store.create_user.return_value = user
        mock_store.create_session.return_value = new_session

        client.cookies.set("dazzle_session", "planted-session-A")
        response = client.post(
            "/auth/register",
            json={
                "email": "new@example.com",
                "password": "password",
                "username": "newuser",
            },
        )

        assert response.status_code == 201
        mock_store.delete_session.assert_called_once_with("planted-session-A")

    def test_no_pre_auth_cookie_register_is_noop(self, setup: tuple[Any, MagicMock]) -> None:
        client, mock_store = setup
        user = _make_user("new@example.com")
        new_session = _make_session(user, sid="new-session-B")

        mock_store.get_user_by_email.return_value = None
        mock_store.create_user.return_value = user
        mock_store.create_session.return_value = new_session

        response = client.post(
            "/auth/register",
            json={
                "email": "new@example.com",
                "password": "password",
                "username": "newuser",
            },
        )

        assert response.status_code == 201
        mock_store.delete_session.assert_not_called()


# ---------------------------------------------------------------------------
# 3. _verify_2fa — routes_2fa.py
# ---------------------------------------------------------------------------


class TestTwoFactorVerifyRegenerate:
    """Final 2FA verification deletes the pending token *and* the pre-auth id."""

    @pytest.fixture
    def setup(self) -> tuple[Any, MagicMock]:
        mock_store = _build_mock_auth_store()
        app = FastAPI()
        app.include_router(create_2fa_routes(mock_store))
        return TestClient(app), mock_store

    def test_pre_auth_sid_invalidated_alongside_pending_token(
        self, setup: tuple[Any, MagicMock]
    ) -> None:
        client, mock_store = setup
        user = _make_user("totp@example.com", totp_enabled=True)
        pending = _make_session(user, sid="pending-2fa", minutes=10)
        full = _make_session(user, sid="full-session-B")

        mock_store.validate_session.return_value = _make_auth_context(user, pending)
        mock_store.get_totp_secret.return_value = "JBSWY3DPEHPK3PXP"
        mock_store.create_session.return_value = full

        client.cookies.set("dazzle_session", "planted-session-A")

        with _mock_totp_module(verify_return=True):
            response = client.post(
                "/auth/2fa/verify",
                json={
                    "code": "123456",
                    "method": "totp",
                    "session_token": "pending-2fa",
                },
            )

        assert response.status_code == 200
        # Both the pending token AND the pre-auth id should be deleted.
        deleted_ids = {call.args[0] for call in mock_store.delete_session.call_args_list}
        assert "pending-2fa" in deleted_ids
        assert "planted-session-A" in deleted_ids
        # Not all user sessions — regenerate, not delete_user_sessions.
        mock_store.delete_user_sessions.assert_not_called()

    def test_no_pre_auth_cookie_only_deletes_pending(self, setup: tuple[Any, MagicMock]) -> None:
        client, mock_store = setup
        user = _make_user("totp@example.com", totp_enabled=True)
        pending = _make_session(user, sid="pending-2fa", minutes=10)
        full = _make_session(user, sid="full-session-B")

        mock_store.validate_session.return_value = _make_auth_context(user, pending)
        mock_store.get_totp_secret.return_value = "JBSWY3DPEHPK3PXP"
        mock_store.create_session.return_value = full

        with _mock_totp_module(verify_return=True):
            response = client.post(
                "/auth/2fa/verify",
                json={
                    "code": "123456",
                    "method": "totp",
                    "session_token": "pending-2fa",
                },
            )

        assert response.status_code == 200
        # Only the pending token is deleted — no pre-auth cookie sent so
        # the regenerate branch is a no-op.
        mock_store.delete_session.assert_called_once_with("pending-2fa")


# ---------------------------------------------------------------------------
# 4. Form-encoded password login + signup — password_login_routes.py
# ---------------------------------------------------------------------------


class TestFormPasswordLoginRegenerate:
    """Form-encoded `/auth/login/password` regenerates the session id."""

    @pytest.fixture
    def setup(self) -> tuple[Any, MagicMock]:
        from dazzle.http.runtime.auth.password_login_routes import (
            create_password_login_routes,
        )

        mock_store = _build_mock_auth_store()
        app = FastAPI()
        app.state.auth_store = mock_store
        app.include_router(create_password_login_routes())
        return TestClient(app, follow_redirects=False), mock_store

    def test_pre_auth_sid_invalidated_on_form_login(self, setup: tuple[Any, MagicMock]) -> None:
        client, mock_store = setup
        user = _make_user("formuser@example.com")
        new_session = _make_session(user, sid="new-session-B")

        mock_store.authenticate.return_value = user
        mock_store.create_session.return_value = new_session

        client.cookies.set("dazzle_session", "planted-session-A")
        response = client.post(
            "/auth/login/password",
            data={"email": "formuser@example.com", "password": "password"},
        )

        assert response.status_code == 303
        mock_store.delete_session.assert_called_once_with("planted-session-A")

    def test_no_pre_auth_cookie_form_login_is_noop(self, setup: tuple[Any, MagicMock]) -> None:
        client, mock_store = setup
        user = _make_user("formuser@example.com")
        new_session = _make_session(user, sid="new-session-B")

        mock_store.authenticate.return_value = user
        mock_store.create_session.return_value = new_session

        response = client.post(
            "/auth/login/password",
            data={"email": "formuser@example.com", "password": "password"},
        )

        assert response.status_code == 303
        mock_store.delete_session.assert_not_called()

    def test_form_signup_regenerates(self, setup: tuple[Any, MagicMock]) -> None:
        client, mock_store = setup
        user = _make_user("newform@example.com")
        new_session = _make_session(user, sid="new-session-B")

        mock_store.get_user_by_email.return_value = None
        mock_store.create_user.return_value = user
        mock_store.create_session.return_value = new_session

        client.cookies.set("dazzle_session", "planted-session-A")
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
        mock_store.delete_session.assert_called_once_with("planted-session-A")


# ---------------------------------------------------------------------------
# 5. Magic-link consumer — magic_link_routes.py
# ---------------------------------------------------------------------------


class TestMagicLinkRegenerate:
    """`GET /auth/magic/{token}` regenerates the session id."""

    @pytest.fixture
    def setup(self) -> tuple[Any, MagicMock]:
        from dazzle.http.runtime.auth.magic_link_routes import (
            create_magic_link_routes,
        )

        mock_store = _build_mock_auth_store()
        app = FastAPI()
        app.state.auth_store = mock_store
        app.include_router(create_magic_link_routes())
        return TestClient(app, follow_redirects=False), mock_store

    def test_pre_auth_sid_invalidated_on_magic_link(self, setup: tuple[Any, MagicMock]) -> None:
        client, mock_store = setup
        user = _make_user("magic@example.com")
        new_session = _make_session(user, sid="new-session-B")

        # Patch the module-level helper instead of inserting into the store.
        from dazzle.http.runtime.auth import magic_link_routes as mlr

        original_validate = mlr.validate_magic_link
        mlr.validate_magic_link = MagicMock(return_value=user.id)
        try:
            mock_store.get_user_by_id.return_value = user
            mock_store.create_session.return_value = new_session

            client.cookies.set("dazzle_session", "planted-session-A")
            response = client.get("/auth/magic/sometoken")
        finally:
            mlr.validate_magic_link = original_validate

        assert response.status_code == 303
        mock_store.delete_session.assert_called_once_with("planted-session-A")

    def test_no_pre_auth_cookie_magic_link_is_noop(self, setup: tuple[Any, MagicMock]) -> None:
        client, mock_store = setup
        user = _make_user("magic@example.com")
        new_session = _make_session(user, sid="new-session-B")

        from dazzle.http.runtime.auth import magic_link_routes as mlr

        original_validate = mlr.validate_magic_link
        mlr.validate_magic_link = MagicMock(return_value=user.id)
        try:
            mock_store.get_user_by_id.return_value = user
            mock_store.create_session.return_value = new_session

            response = client.get("/auth/magic/sometoken")
        finally:
            mlr.validate_magic_link = original_validate

        assert response.status_code == 303
        mock_store.delete_session.assert_not_called()


# ---------------------------------------------------------------------------
# 6. Form-encoded 2FA verify — two_factor_form_routes.py
# ---------------------------------------------------------------------------


class TestForm2faVerifyRegenerate:
    """Form `/auth/2fa/verify/submit` deletes pending token + pre-auth id."""

    @pytest.fixture
    def setup(self) -> tuple[Any, MagicMock]:
        from dazzle.http.runtime.auth.two_factor_form_routes import (
            create_two_factor_form_routes,
        )

        mock_store = _build_mock_auth_store()
        app = FastAPI()
        app.state.auth_store = mock_store
        app.include_router(create_two_factor_form_routes())
        return TestClient(app, follow_redirects=False), mock_store

    def test_pre_auth_sid_invalidated_with_pending(self, setup: tuple[Any, MagicMock]) -> None:
        client, mock_store = setup
        user = _make_user("totpform@example.com", totp_enabled=True)
        pending = _make_session(user, sid="pending-2fa", minutes=10)
        full = _make_session(user, sid="full-session-B")

        mock_store.validate_session.return_value = _make_auth_context(user, pending)
        mock_store.get_totp_secret.return_value = "JBSWY3DPEHPK3PXP"
        mock_store.create_session.return_value = full

        client.cookies.set("dazzle_session", "planted-session-A")

        with _mock_totp_module(verify_return=True):
            response = client.post(
                "/auth/2fa/verify/submit",
                data={
                    "session_token": "pending-2fa",
                    "method": "totp",
                    "code": "123456",
                },
            )

        assert response.status_code == 303
        deleted_ids = {call.args[0] for call in mock_store.delete_session.call_args_list}
        assert "pending-2fa" in deleted_ids
        assert "planted-session-A" in deleted_ids
