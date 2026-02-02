"""
Unit tests for JWT authentication.

Tests for jwt_auth.py, jwt_middleware.py, and token_store.py.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

# =============================================================================
# JWT Auth Tests
# =============================================================================


class TestJWTConfig:
    """Test JWTConfig dataclass."""

    def test_default_config(self) -> None:
        """Should create config with sensible defaults."""
        from dazzle_back.runtime.jwt_auth import JWTConfig

        config = JWTConfig()

        assert config.algorithm == "HS256"
        assert config.access_token_expire_minutes == 15
        assert config.refresh_token_expire_days == 7
        assert config.issuer == "dazzle-app"
        assert config.secret_key  # Should be auto-generated

    def test_custom_config(self) -> None:
        """Should allow custom configuration."""
        from dazzle_back.runtime.jwt_auth import JWTConfig

        config = JWTConfig(
            algorithm="RS256",
            access_token_expire_minutes=30,
            refresh_token_expire_days=14,
            issuer="my-app",
        )

        assert config.algorithm == "RS256"
        assert config.access_token_expire_minutes == 30
        assert config.refresh_token_expire_days == 14
        assert config.issuer == "my-app"


class TestJWTService:
    """Test JWTService class."""

    @pytest.fixture
    def jwt_service(self):
        """Create JWT service with test config."""
        from dazzle_back.runtime.jwt_auth import JWTConfig, JWTService

        config = JWTConfig(secret_key="test-secret-key-for-unit-tests-32bytes")
        return JWTService(config)

    def test_create_access_token(self, jwt_service) -> None:
        """Should create valid access token."""
        pytest.importorskip("jwt")

        user_id = uuid4()
        email = "test@example.com"
        roles = ["user", "admin"]

        token, claims = jwt_service.create_access_token(
            user_id=user_id,
            email=email,
            roles=roles,
        )

        assert token
        assert isinstance(token, str)
        assert claims.sub == str(user_id)
        assert claims.email == email
        assert claims.roles == roles
        assert claims.iss == "dazzle-app"
        assert claims.exp > claims.iat

    def test_verify_access_token(self, jwt_service) -> None:
        """Should verify and decode valid token."""
        pytest.importorskip("jwt")

        user_id = uuid4()
        email = "test@example.com"

        token, original_claims = jwt_service.create_access_token(
            user_id=user_id,
            email=email,
            roles=["user"],
        )

        verified_claims = jwt_service.verify_access_token(token)

        assert verified_claims.sub == str(user_id)
        assert verified_claims.email == email
        assert verified_claims.roles == ["user"]
        assert verified_claims.jti == original_claims.jti

    def test_verify_expired_token(self, jwt_service) -> None:
        """Should reject expired token."""
        jwt_module = pytest.importorskip("jwt")
        from dazzle_back.runtime.jwt_auth import JWTError

        # Create token with past expiration
        now = datetime.now(UTC)
        payload = {
            "sub": str(uuid4()),
            "email": "test@example.com",
            "roles": [],
            "exp": int((now - timedelta(hours=1)).timestamp()),
            "iat": int((now - timedelta(hours=2)).timestamp()),
            "jti": "test-jti",
            "iss": "dazzle-app",
        }
        token = jwt_module.encode(
            payload, "test-secret-key-for-unit-tests-32bytes", algorithm="HS256"
        )

        with pytest.raises(JWTError) as exc_info:
            jwt_service.verify_access_token(token)

        assert exc_info.value.code == "token_expired"

    def test_verify_invalid_token(self, jwt_service) -> None:
        """Should reject invalid token."""
        pytest.importorskip("jwt")
        from dazzle_back.runtime.jwt_auth import JWTError

        with pytest.raises(JWTError) as exc_info:
            jwt_service.verify_access_token("invalid.token.here")

        assert exc_info.value.code == "invalid_token"

    def test_create_token_pair(self, jwt_service) -> None:
        """Should create access and refresh token pair."""
        pytest.importorskip("jwt")
        from dazzle_back.runtime.auth import UserRecord

        user = UserRecord(
            id=uuid4(),
            email="test@example.com",
            password_hash="fake-hash",
            roles=["user"],
        )

        token_pair = jwt_service.create_token_pair(user)

        assert token_pair.access_token
        assert token_pair.refresh_token
        assert token_pair.token_type == "Bearer"
        assert token_pair.expires_in == 15 * 60  # 15 minutes in seconds


# =============================================================================
# Token Store Tests
# =============================================================================


class TestTokenStore:
    """Test TokenStore class."""

    @pytest.fixture
    def token_store(self, tmp_path: Path):
        """Create token store with temp database."""
        from dazzle_back.runtime.token_store import TokenStore

        return TokenStore(db_path=tmp_path / "tokens.db")

    @pytest.fixture
    def user(self):
        """Create test user."""
        from dazzle_back.runtime.auth import UserRecord

        return UserRecord(
            id=uuid4(),
            email="test@example.com",
            password_hash="fake-hash",
            roles=["user"],
        )

    def test_create_token(self, token_store, user) -> None:
        """Should create refresh token."""
        token = token_store.create_token(user)

        assert token
        assert isinstance(token, str)
        assert len(token) > 20  # Should be a reasonable length

    def test_validate_token(self, token_store, user) -> None:
        """Should validate valid token."""
        token = token_store.create_token(user)

        record = token_store.validate_token(token)

        assert record is not None
        assert record.user_id == user.id
        assert not record.is_expired
        assert not record.is_revoked

    def test_validate_invalid_token(self, token_store) -> None:
        """Should return None for invalid token."""
        record = token_store.validate_token("invalid-token")

        assert record is None

    def test_revoke_token(self, token_store, user) -> None:
        """Should revoke token."""
        token = token_store.create_token(user)

        # Validate before revoke
        record = token_store.validate_token(token)
        assert record is not None

        # Revoke
        revoked = token_store.revoke_token(token)
        assert revoked is True

        # Validate after revoke
        record = token_store.validate_token(token)
        assert record is None

    def test_rotate_token(self, token_store, user) -> None:
        """Should rotate token (revoke old, create new)."""
        old_token = token_store.create_token(user)

        new_token = token_store.rotate_token(old_token, user)

        assert new_token is not None
        assert new_token != old_token

        # Old token should be invalid
        old_record = token_store.validate_token(old_token)
        assert old_record is None

        # New token should be valid
        new_record = token_store.validate_token(new_token)
        assert new_record is not None

    def test_revoke_user_tokens(self, token_store, user) -> None:
        """Should revoke all tokens for a user."""
        # Create multiple tokens
        token1 = token_store.create_token(user)
        token2 = token_store.create_token(user, device_id="device-2")
        token3 = token_store.create_token(user, device_id="device-3")

        # Revoke all
        count = token_store.revoke_user_tokens(user.id)
        assert count == 3

        # All should be invalid
        assert token_store.validate_token(token1) is None
        assert token_store.validate_token(token2) is None
        assert token_store.validate_token(token3) is None

    def test_get_user_tokens(self, token_store, user) -> None:
        """Should list all active tokens for user."""
        token_store.create_token(user, device_id="device-1")
        token_store.create_token(user, device_id="device-2")

        tokens = token_store.get_user_tokens(user.id)

        assert len(tokens) == 2
        device_ids = {t.device_id for t in tokens}
        assert "device-1" in device_ids
        assert "device-2" in device_ids


# =============================================================================
# JWT Middleware Tests
# =============================================================================


class TestJWTMiddleware:
    """Test JWTMiddleware class."""

    @pytest.fixture
    def jwt_service(self):
        """Create JWT service."""
        from dazzle_back.runtime.jwt_auth import JWTConfig, JWTService

        config = JWTConfig(secret_key="test-secret-key-for-unit-tests-32bytes")
        return JWTService(config)

    @pytest.fixture
    def middleware(self, jwt_service):
        """Create JWT middleware."""
        from dazzle_back.runtime.jwt_middleware import JWTMiddleware

        return JWTMiddleware(jwt_service)

    def test_extract_token_from_header(self, middleware) -> None:
        """Should extract token from Authorization header."""
        pytest.importorskip("fastapi")
        from unittest.mock import MagicMock

        request = MagicMock()
        request.headers = {"Authorization": "Bearer test-token"}

        token = middleware._extract_token(request)

        assert token == "test-token"

    def test_extract_token_missing_header(self, middleware) -> None:
        """Should return None when header is missing."""
        pytest.importorskip("fastapi")
        from unittest.mock import MagicMock

        request = MagicMock()
        request.headers = {}

        token = middleware._extract_token(request)

        assert token is None

    def test_extract_token_invalid_format(self, middleware) -> None:
        """Should return None for invalid header format."""
        pytest.importorskip("fastapi")
        from unittest.mock import MagicMock

        request = MagicMock()
        request.headers = {"Authorization": "Basic invalid"}

        token = middleware._extract_token(request)

        assert token is None

    def test_get_auth_context_valid_token(self, middleware, jwt_service) -> None:
        """Should return authenticated context for valid token."""
        pytest.importorskip("jwt")
        from unittest.mock import MagicMock

        user_id = uuid4()
        token, _ = jwt_service.create_access_token(
            user_id=user_id,
            email="test@example.com",
            roles=["user"],
        )

        request = MagicMock()
        request.headers = {"Authorization": f"Bearer {token}"}
        request.url.path = "/api/test"

        context = middleware.get_auth_context(request)

        assert context.is_authenticated
        assert context.user_id == str(user_id)
        assert context.email == "test@example.com"

    def test_get_auth_context_excluded_path(self, middleware) -> None:
        """Should return unauthenticated context for excluded paths."""
        pytest.importorskip("fastapi")
        from unittest.mock import MagicMock

        request = MagicMock()
        request.headers = {}
        request.url.path = "/health"

        context = middleware.get_auth_context(request)

        assert not context.is_authenticated
        assert context.error is None  # No error for excluded paths


# =============================================================================
# Device Registry Tests
# =============================================================================


class TestDeviceRegistry:
    """Test DeviceRegistry class."""

    @pytest.fixture
    def registry(self, tmp_path: Path):
        """Create device registry with temp database."""
        from dazzle_back.runtime.device_registry import DeviceRegistry

        return DeviceRegistry(db_path=tmp_path / "devices.db")

    def test_register_device(self, registry) -> None:
        """Should register a device."""
        from dazzle_back.runtime.device_registry import DevicePlatform

        user_id = uuid4()
        device = registry.register_device(
            user_id=user_id,
            platform=DevicePlatform.IOS,
            push_token="test-push-token",
            device_name="iPhone 15",
        )

        assert device.id
        assert device.user_id == user_id
        assert device.platform == DevicePlatform.IOS
        assert device.push_token == "test-push-token"
        assert device.device_name == "iPhone 15"
        assert device.is_active

    def test_get_user_devices(self, registry) -> None:
        """Should list user's devices."""
        from dazzle_back.runtime.device_registry import DevicePlatform

        user_id = uuid4()
        registry.register_device(user_id, DevicePlatform.IOS, "token-1")
        registry.register_device(user_id, DevicePlatform.ANDROID, "token-2")

        devices = registry.get_user_devices(user_id)

        assert len(devices) == 2
        platforms = {d.platform for d in devices}
        assert DevicePlatform.IOS in platforms
        assert DevicePlatform.ANDROID in platforms

    def test_unregister_device(self, registry) -> None:
        """Should unregister (deactivate) a device."""
        from dazzle_back.runtime.device_registry import DevicePlatform

        user_id = uuid4()
        device = registry.register_device(user_id, DevicePlatform.IOS, "token")

        success = registry.unregister_device(device.id, user_id)
        assert success

        # Should not appear in active devices
        devices = registry.get_user_devices(user_id, active_only=True)
        assert len(devices) == 0

    def test_duplicate_token_updates(self, registry) -> None:
        """Should update existing device when re-registering same token."""
        from dazzle_back.runtime.device_registry import DevicePlatform

        user_id = uuid4()
        push_token = "same-token"

        device1 = registry.register_device(
            user_id, DevicePlatform.IOS, push_token, device_name="Old Name"
        )
        device2 = registry.register_device(
            user_id, DevicePlatform.IOS, push_token, device_name="New Name"
        )

        # Should be the same device
        assert device1.id == device2.id

        # User should only have 1 device
        devices = registry.get_user_devices(user_id)
        assert len(devices) == 1
