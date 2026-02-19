"""
Tests for two-factor authentication (2FA) flow.

Covers:
- TwoFactorConfig IR model defaults and immutability
- UserRecord 2FA-related fields and properties
- TwoFactorMixin store methods (enable/disable TOTP, email OTP, get secret)
- Login flow branching (normal login vs 2FA challenge)
- 2FA verify endpoint (valid TOTP code -> session, invalid code -> 401)
"""

from __future__ import annotations

import secrets
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from pydantic import ValidationError

from dazzle.core.ir.security import TwoFactorConfig, TwoFactorMethod
from dazzle_back.runtime.auth import (
    AuthContext,
    SessionRecord,
    TwoFactorMixin,
    UserRecord,
    create_2fa_routes,
    create_auth_routes,
    hash_password,
)

# FastAPI / httpx are dev-only deps; skip route tests if unavailable.
try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False

try:
    import httpx  # noqa: F401
    import pytest_asyncio  # noqa: F401

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False


# ---------------------------------------------------------------------------
# Helper: mock the dazzle_back.runtime.totp module which may not exist yet
# ---------------------------------------------------------------------------


@contextmanager
def _mock_totp_module(verify_return: bool) -> Iterator[MagicMock]:
    """Temporarily inject a mock ``dazzle_back.runtime.totp`` into sys.modules.

    The ``verify_totp`` callable on the mock is set to return *verify_return*.
    After the context exits the original module state is restored.
    """
    mock_module = MagicMock()
    mock_module.verify_totp = MagicMock(return_value=verify_return)
    key = "dazzle_back.runtime.totp"
    original = sys.modules.get(key)
    sys.modules[key] = mock_module
    try:
        yield mock_module
    finally:
        if original is None:
            sys.modules.pop(key, None)
        else:
            sys.modules[key] = original


# =============================================================================
# 1. TwoFactorConfig IR model
# =============================================================================


class TestTwoFactorConfig:
    """Tests for the TwoFactorConfig Pydantic model in the IR layer."""

    def test_default_values(self) -> None:
        """Default config: disabled, both methods, 6-digit OTP, 300s expiry, 8 codes."""
        cfg = TwoFactorConfig()

        assert cfg.enabled is False
        assert TwoFactorMethod.EMAIL_OTP in cfg.methods
        assert TwoFactorMethod.TOTP in cfg.methods
        assert len(cfg.methods) == 2
        assert cfg.otp_length == 6
        assert cfg.otp_expiry_seconds == 300
        assert cfg.recovery_code_count == 8
        assert cfg.enforce_for_roles == []

    def test_custom_values(self) -> None:
        """Custom values are stored correctly."""
        cfg = TwoFactorConfig(
            enabled=True,
            methods=[TwoFactorMethod.TOTP],
            otp_length=8,
            otp_expiry_seconds=600,
            recovery_code_count=12,
            enforce_for_roles=["admin", "manager"],
        )

        assert cfg.enabled is True
        assert cfg.methods == [TwoFactorMethod.TOTP]
        assert cfg.otp_length == 8
        assert cfg.otp_expiry_seconds == 600
        assert cfg.recovery_code_count == 12
        assert cfg.enforce_for_roles == ["admin", "manager"]

    def test_frozen_model(self) -> None:
        """TwoFactorConfig is immutable (frozen=True)."""
        cfg = TwoFactorConfig()

        with pytest.raises(ValidationError):
            cfg.enabled = True  # type: ignore[misc]


class TestTwoFactorMethod:
    """Tests for the TwoFactorMethod enum."""

    def test_email_otp_value(self) -> None:
        assert TwoFactorMethod.EMAIL_OTP == "email_otp"

    def test_totp_value(self) -> None:
        assert TwoFactorMethod.TOTP == "totp"


# =============================================================================
# 2. UserRecord 2FA fields
# =============================================================================


class TestUserRecord2FA:
    """Tests for 2FA-related fields and properties on UserRecord."""

    def _make_user(self, **overrides: Any) -> UserRecord:
        """Build a UserRecord with sensible defaults, allowing overrides."""
        defaults: dict[str, Any] = {
            "email": "test@example.com",
            "password_hash": hash_password("password"),
        }
        defaults.update(overrides)
        return UserRecord(**defaults)

    def test_two_factor_enabled_when_totp_enabled(self) -> None:
        """two_factor_enabled returns True when totp_enabled is True."""
        user = self._make_user(totp_enabled=True, email_otp_enabled=False)
        assert user.two_factor_enabled is True

    def test_two_factor_enabled_when_email_otp_enabled(self) -> None:
        """two_factor_enabled returns True when email_otp_enabled is True."""
        user = self._make_user(totp_enabled=False, email_otp_enabled=True)
        assert user.two_factor_enabled is True

    def test_two_factor_enabled_when_both_enabled(self) -> None:
        """two_factor_enabled returns True when both methods are enabled."""
        user = self._make_user(totp_enabled=True, email_otp_enabled=True)
        assert user.two_factor_enabled is True

    def test_two_factor_disabled_when_neither_enabled(self) -> None:
        """two_factor_enabled returns False when no 2FA method is active."""
        user = self._make_user(totp_enabled=False, email_otp_enabled=False)
        assert user.two_factor_enabled is False

    def test_new_2fa_fields_default_values(self) -> None:
        """New 2FA fields default to None/False."""
        user = self._make_user()
        assert user.totp_secret is None
        assert user.totp_enabled is False
        assert user.email_otp_enabled is False
        assert user.recovery_codes_generated is False

    def test_totp_secret_stored(self) -> None:
        """totp_secret stores the provided value."""
        user = self._make_user(totp_secret="JBSWY3DPEHPK3PXP")
        assert user.totp_secret == "JBSWY3DPEHPK3PXP"


# =============================================================================
# 3. TwoFactorMixin methods
# =============================================================================


class _FakeStore(TwoFactorMixin):
    """Minimal concrete class that wires TwoFactorMixin to mock DB methods."""

    def __init__(self) -> None:
        self._execute = MagicMock(return_value=[])
        self._execute_one = MagicMock(return_value=None)
        self._execute_modify = MagicMock(return_value=1)
        self.get_user_by_id = MagicMock(return_value=None)


class TestTwoFactorMixin:
    """Tests for TwoFactorMixin store methods."""

    @pytest.fixture
    def store(self) -> _FakeStore:
        return _FakeStore()

    def test_enable_totp(self, store: _FakeStore) -> None:
        """enable_totp issues an UPDATE storing secret and setting totp_enabled=TRUE."""
        uid = uuid4()
        store.enable_totp(uid, "MYSECRET")

        store._execute_modify.assert_called_once()
        args = store._execute_modify.call_args
        query: str = args[0][0]
        params: tuple[Any, ...] = args[0][1]

        assert "totp_secret" in query
        assert "totp_enabled = TRUE" in query
        assert params[0] == "MYSECRET"
        assert str(uid) in params

    def test_disable_totp(self, store: _FakeStore) -> None:
        """disable_totp clears secret (NULL) and sets totp_enabled=FALSE."""
        uid = uuid4()
        store.disable_totp(uid)

        store._execute_modify.assert_called_once()
        query: str = store._execute_modify.call_args[0][0]

        assert "totp_secret = NULL" in query
        assert "totp_enabled = FALSE" in query

    def test_enable_email_otp(self, store: _FakeStore) -> None:
        """enable_email_otp sets email_otp_enabled=TRUE."""
        uid = uuid4()
        store.enable_email_otp(uid)

        store._execute_modify.assert_called_once()
        query: str = store._execute_modify.call_args[0][0]
        assert "email_otp_enabled = TRUE" in query

    def test_disable_email_otp(self, store: _FakeStore) -> None:
        """disable_email_otp sets email_otp_enabled=FALSE."""
        uid = uuid4()
        store.disable_email_otp(uid)

        store._execute_modify.assert_called_once()
        query: str = store._execute_modify.call_args[0][0]
        assert "email_otp_enabled = FALSE" in query

    def test_get_totp_secret_returns_stored_secret(self, store: _FakeStore) -> None:
        """get_totp_secret returns the value from the DB row."""
        store._execute_one.return_value = {"totp_secret": "SECRET123"}

        result = store.get_totp_secret(uuid4())
        assert result == "SECRET123"

    def test_get_totp_secret_returns_none_when_not_found(self, store: _FakeStore) -> None:
        """get_totp_secret returns None when user not found."""
        store._execute_one.return_value = None

        result = store.get_totp_secret(uuid4())
        assert result is None

    def test_set_recovery_codes_generated(self, store: _FakeStore) -> None:
        """set_recovery_codes_generated updates the flag."""
        uid = uuid4()
        store.set_recovery_codes_generated(uid, True)

        store._execute_modify.assert_called_once()
        query: str = store._execute_modify.call_args[0][0]
        assert "recovery_codes_generated" in query


# =============================================================================
# 4. Login flow with 2FA (route-level tests)
# =============================================================================


def _build_mock_auth_store() -> MagicMock:
    """Build a MagicMock that quacks like AuthStore for route tests."""
    store = MagicMock()

    # Default: authenticate returns None (invalid creds)
    store.authenticate.return_value = None
    store.get_user_by_email.return_value = None

    return store


def _make_session(user: UserRecord, minutes: int = 10) -> SessionRecord:
    """Create a SessionRecord for testing."""
    return SessionRecord(
        id=secrets.token_urlsafe(32),
        user_id=user.id,
        expires_at=datetime.now(UTC) + timedelta(minutes=minutes),
    )


def _make_auth_context(user: UserRecord, session: SessionRecord) -> AuthContext:
    """Create an authenticated AuthContext for testing."""
    return AuthContext(
        user=user,
        session=session,
        is_authenticated=True,
        roles=user.roles,
    )


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestLoginFlowWith2FA:
    """Route-level tests for the login endpoint with 2FA branching."""

    @pytest.fixture
    def setup(self) -> tuple[Any, Any, MagicMock]:
        """Create a FastAPI app with mocked AuthStore and TestClient."""
        mock_store = _build_mock_auth_store()

        app = FastAPI()
        router = create_auth_routes(mock_store)
        app.include_router(router)

        client = TestClient(app)
        return app, client, mock_store

    def test_login_without_2fa_returns_session_cookie(
        self, setup: tuple[Any, Any, MagicMock]
    ) -> None:
        """User without 2FA receives a normal login response with session cookie."""
        _, client, mock_store = setup

        user = UserRecord(
            email="normal@example.com",
            password_hash=hash_password("password"),
            totp_enabled=False,
            email_otp_enabled=False,
        )
        session = _make_session(user, minutes=7 * 24 * 60)

        mock_store.authenticate.return_value = user
        mock_store.create_session.return_value = session

        response = client.post(
            "/auth/login",
            json={"email": "normal@example.com", "password": "password"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Login successful"
        assert data["user"]["email"] == "normal@example.com"
        assert "dazzle_session" in response.cookies

    def test_login_with_totp_2fa_returns_challenge(self, setup: tuple[Any, Any, MagicMock]) -> None:
        """User with TOTP enabled gets a 2fa_required response."""
        _, client, mock_store = setup

        user = UserRecord(
            email="totp@example.com",
            password_hash=hash_password("password"),
            totp_enabled=True,
            email_otp_enabled=False,
        )
        pending_session = _make_session(user, minutes=10)

        mock_store.authenticate.return_value = user
        mock_store.create_session.return_value = pending_session

        response = client.post(
            "/auth/login",
            json={"email": "totp@example.com", "password": "password"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "2fa_required"
        assert "totp" in data["methods"]
        assert "email_otp" not in data["methods"]
        assert data["session_token"] == pending_session.id
        assert data["user_id"] == str(user.id)
        # Should NOT set a session cookie (login is incomplete)
        assert "dazzle_session" not in response.cookies

    def test_login_with_email_otp_2fa_returns_challenge(
        self, setup: tuple[Any, Any, MagicMock]
    ) -> None:
        """User with email OTP enabled gets a 2fa_required response."""
        _, client, mock_store = setup

        user = UserRecord(
            email="emailotp@example.com",
            password_hash=hash_password("password"),
            totp_enabled=False,
            email_otp_enabled=True,
        )
        pending_session = _make_session(user, minutes=10)

        mock_store.authenticate.return_value = user
        mock_store.create_session.return_value = pending_session

        response = client.post(
            "/auth/login",
            json={"email": "emailotp@example.com", "password": "password"},
        )

        data = response.json()
        assert data["status"] == "2fa_required"
        assert "email_otp" in data["methods"]
        assert "totp" not in data["methods"]

    def test_login_with_both_2fa_methods(self, setup: tuple[Any, Any, MagicMock]) -> None:
        """User with both TOTP and email OTP gets both methods in the challenge."""
        _, client, mock_store = setup

        user = UserRecord(
            email="both@example.com",
            password_hash=hash_password("password"),
            totp_enabled=True,
            email_otp_enabled=True,
        )
        pending_session = _make_session(user, minutes=10)

        mock_store.authenticate.return_value = user
        mock_store.create_session.return_value = pending_session

        response = client.post(
            "/auth/login",
            json={"email": "both@example.com", "password": "password"},
        )

        data = response.json()
        assert data["status"] == "2fa_required"
        assert "totp" in data["methods"]
        assert "email_otp" in data["methods"]

    def test_login_invalid_credentials(self, setup: tuple[Any, Any, MagicMock]) -> None:
        """Invalid credentials return 401 regardless of 2FA status."""
        _, client, mock_store = setup

        mock_store.authenticate.return_value = None

        response = client.post(
            "/auth/login",
            json={"email": "bad@example.com", "password": "wrong"},
        )

        assert response.status_code == 401


@pytest.mark.skipif(not FASTAPI_AVAILABLE, reason="FastAPI not installed")
class TestTwoFactorVerifyRoute:
    """Route-level tests for the /auth/2fa/verify endpoint."""

    @pytest.fixture
    def setup(self) -> tuple[Any, Any, MagicMock]:
        """Create a FastAPI app with 2FA routes and a mocked AuthStore."""
        mock_store = _build_mock_auth_store()

        app = FastAPI()
        router = create_2fa_routes(mock_store)
        app.include_router(router)

        client = TestClient(app)
        return app, client, mock_store

    def test_verify_valid_totp_creates_session(self, setup: tuple[Any, Any, MagicMock]) -> None:
        """Valid TOTP code completes login: deletes pending session, creates full session."""
        _, client, mock_store = setup

        user = UserRecord(
            email="totp@example.com",
            password_hash=hash_password("password"),
            totp_enabled=True,
        )
        pending_session = _make_session(user, minutes=10)
        full_session = _make_session(user, minutes=7 * 24 * 60)

        # validate_session returns the pending user context
        mock_store.validate_session.return_value = _make_auth_context(user, pending_session)
        mock_store.get_totp_secret.return_value = "JBSWY3DPEHPK3PXP"
        mock_store.delete_session.return_value = True
        mock_store.create_session.return_value = full_session

        with _mock_totp_module(verify_return=True):
            response = client.post(
                "/auth/2fa/verify",
                json={
                    "code": "123456",
                    "method": "totp",
                    "session_token": pending_session.id,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "2FA verification successful"
        assert data["user"]["email"] == "totp@example.com"
        assert "dazzle_session" in response.cookies

        # Pending session should be deleted
        mock_store.delete_session.assert_called_once_with(pending_session.id)
        # Full session should be created
        mock_store.create_session.assert_called_once()

    def test_verify_invalid_totp_returns_401(self, setup: tuple[Any, Any, MagicMock]) -> None:
        """Invalid TOTP code returns 401."""
        _, client, mock_store = setup

        user = UserRecord(
            email="totp@example.com",
            password_hash=hash_password("password"),
            totp_enabled=True,
        )
        pending_session = _make_session(user, minutes=10)

        mock_store.validate_session.return_value = _make_auth_context(user, pending_session)
        mock_store.get_totp_secret.return_value = "JBSWY3DPEHPK3PXP"

        with _mock_totp_module(verify_return=False):
            response = client.post(
                "/auth/2fa/verify",
                json={
                    "code": "000000",
                    "method": "totp",
                    "session_token": pending_session.id,
                },
            )

        assert response.status_code == 401
        assert "Invalid 2FA code" in response.json()["detail"]

    def test_verify_expired_session_token_returns_401(
        self, setup: tuple[Any, Any, MagicMock]
    ) -> None:
        """Expired or invalid session_token returns 401."""
        _, client, mock_store = setup

        mock_store.validate_session.return_value = AuthContext(is_authenticated=False)

        response = client.post(
            "/auth/2fa/verify",
            json={
                "code": "123456",
                "method": "totp",
                "session_token": "invalid_token",
            },
        )

        assert response.status_code == 401
        assert "Invalid session token" in response.json()["detail"]

    def test_verify_totp_with_no_secret_returns_401(
        self, setup: tuple[Any, Any, MagicMock]
    ) -> None:
        """When user has no TOTP secret stored, verification fails."""
        _, client, mock_store = setup

        user = UserRecord(
            email="nosecret@example.com",
            password_hash=hash_password("password"),
            totp_enabled=True,
        )
        pending_session = _make_session(user, minutes=10)

        mock_store.validate_session.return_value = _make_auth_context(user, pending_session)
        mock_store.get_totp_secret.return_value = None

        response = client.post(
            "/auth/2fa/verify",
            json={
                "code": "123456",
                "method": "totp",
                "session_token": pending_session.id,
            },
        )

        assert response.status_code == 401
        assert "Invalid 2FA code" in response.json()["detail"]


# =============================================================================
# Async route tests (pytest-asyncio + httpx)
# =============================================================================


@pytest.mark.skipif(
    not (FASTAPI_AVAILABLE and HTTPX_AVAILABLE),
    reason="FastAPI + httpx + pytest-asyncio required",
)
class TestLoginFlowAsync:
    """Async route tests using httpx.ASGITransport."""

    @pytest.fixture
    def app_and_store(self) -> tuple[Any, MagicMock]:
        mock_store = _build_mock_auth_store()
        app = FastAPI()
        auth_router = create_auth_routes(mock_store)
        tfa_router = create_2fa_routes(mock_store)
        app.include_router(auth_router)
        app.include_router(tfa_router)
        return app, mock_store

    @pytest.mark.asyncio
    async def test_login_no_2fa_async(self, app_and_store: tuple[Any, MagicMock]) -> None:
        """Async: normal login without 2FA returns session cookie."""
        import httpx

        app, mock_store = app_and_store
        user = UserRecord(
            email="async@example.com",
            password_hash=hash_password("pass"),
        )
        session = _make_session(user, minutes=7 * 24 * 60)
        mock_store.authenticate.return_value = user
        mock_store.create_session.return_value = session

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/auth/login",
                json={"email": "async@example.com", "password": "pass"},
            )

        assert response.status_code == 200
        assert response.json()["message"] == "Login successful"

    @pytest.mark.asyncio
    async def test_login_2fa_required_async(self, app_and_store: tuple[Any, MagicMock]) -> None:
        """Async: user with 2FA gets a challenge response."""
        import httpx

        app, mock_store = app_and_store
        user = UserRecord(
            email="async-2fa@example.com",
            password_hash=hash_password("pass"),
            totp_enabled=True,
        )
        pending = _make_session(user, minutes=10)
        mock_store.authenticate.return_value = user
        mock_store.create_session.return_value = pending

        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/auth/login",
                json={"email": "async-2fa@example.com", "password": "pass"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "2fa_required"
        assert "totp" in data["methods"]

    @pytest.mark.asyncio
    async def test_verify_valid_totp_async(self, app_and_store: tuple[Any, MagicMock]) -> None:
        """Async: valid TOTP verification completes login."""
        import httpx

        app, mock_store = app_and_store
        user = UserRecord(
            email="verify-async@example.com",
            password_hash=hash_password("pass"),
            totp_enabled=True,
        )
        pending = _make_session(user, minutes=10)
        full = _make_session(user, minutes=7 * 24 * 60)

        mock_store.validate_session.return_value = _make_auth_context(user, pending)
        mock_store.get_totp_secret.return_value = "SECRET"
        mock_store.delete_session.return_value = True
        mock_store.create_session.return_value = full

        transport = httpx.ASGITransport(app=app)
        with _mock_totp_module(verify_return=True):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.post(
                    "/auth/2fa/verify",
                    json={
                        "code": "123456",
                        "method": "totp",
                        "session_token": pending.id,
                    },
                )

        assert response.status_code == 200
        assert response.json()["message"] == "2FA verification successful"

    @pytest.mark.asyncio
    async def test_verify_invalid_totp_async(self, app_and_store: tuple[Any, MagicMock]) -> None:
        """Async: invalid TOTP code returns 401."""
        import httpx

        app, mock_store = app_and_store
        user = UserRecord(
            email="bad-code@example.com",
            password_hash=hash_password("pass"),
            totp_enabled=True,
        )
        pending = _make_session(user, minutes=10)

        mock_store.validate_session.return_value = _make_auth_context(user, pending)
        mock_store.get_totp_secret.return_value = "SECRET"

        transport = httpx.ASGITransport(app=app)
        with _mock_totp_module(verify_return=False):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.post(
                    "/auth/2fa/verify",
                    json={
                        "code": "000000",
                        "method": "totp",
                        "session_token": pending.id,
                    },
                )

        assert response.status_code == 401
