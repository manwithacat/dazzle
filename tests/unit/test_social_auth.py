"""Tests for the Social Authentication module."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dazzle_back.runtime.social_auth import (
    SocialAuthConfig,
    SocialAuthError,
    SocialAuthService,
    SocialProfile,
    SocialProvider,
    SocialTokenRequest,
)

# =============================================================================
# Test Data Classes
# =============================================================================


class TestSocialProvider:
    """Tests for SocialProvider enum."""

    def test_provider_values(self) -> None:
        """Test that provider enum has expected values."""
        assert SocialProvider.GOOGLE == "google"
        assert SocialProvider.APPLE == "apple"
        assert SocialProvider.GITHUB == "github"

    def test_provider_from_string(self) -> None:
        """Test creating provider from string."""
        assert SocialProvider("google") == SocialProvider.GOOGLE
        assert SocialProvider("apple") == SocialProvider.APPLE
        assert SocialProvider("github") == SocialProvider.GITHUB


class TestSocialProfile:
    """Tests for SocialProfile dataclass."""

    def test_create_profile(self) -> None:
        """Test creating a social profile."""
        profile = SocialProfile(
            provider=SocialProvider.GOOGLE,
            provider_user_id="123456",
            email="test@example.com",
            email_verified=True,
            name="Test User",
        )

        assert profile.provider == SocialProvider.GOOGLE
        assert profile.provider_user_id == "123456"
        assert profile.email == "test@example.com"
        assert profile.email_verified is True
        assert profile.name == "Test User"

    def test_profile_defaults(self) -> None:
        """Test profile default values."""
        profile = SocialProfile(
            provider=SocialProvider.GOOGLE,
            provider_user_id="123",
            email="test@example.com",
        )

        assert profile.email_verified is True  # Default
        assert profile.name is None
        assert profile.given_name is None
        assert profile.family_name is None
        assert profile.picture_url is None
        assert profile.raw_data is None


class TestSocialAuthConfig:
    """Tests for SocialAuthConfig dataclass."""

    def test_empty_config(self) -> None:
        """Test creating empty config."""
        config = SocialAuthConfig()

        assert config.google_client_id is None
        assert config.apple_team_id is None
        assert config.github_client_id is None

    def test_google_config(self) -> None:
        """Test Google configuration."""
        config = SocialAuthConfig(google_client_id="google-client-123.apps.googleusercontent.com")

        assert config.google_client_id == "google-client-123.apps.googleusercontent.com"

    def test_apple_config(self) -> None:
        """Test Apple configuration."""
        config = SocialAuthConfig(
            apple_team_id="TEAM123",
            apple_key_id="KEY456",
            apple_private_key="mock-apple-private-key-for-testing",
            apple_bundle_id="com.example.app",
        )

        assert config.apple_team_id == "TEAM123"
        assert config.apple_key_id == "KEY456"
        assert config.apple_bundle_id == "com.example.app"

    def test_github_config(self) -> None:
        """Test GitHub configuration."""
        config = SocialAuthConfig(
            github_client_id="gh-client-123",
            github_client_secret="gh-secret-456",
        )

        assert config.github_client_id == "gh-client-123"
        assert config.github_client_secret == "gh-secret-456"


class TestSocialTokenRequest:
    """Tests for SocialTokenRequest model."""

    def test_id_token_request(self) -> None:
        """Test request with id_token."""
        request = SocialTokenRequest(id_token="eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...")

        assert request.id_token is not None
        assert request.access_token is None
        assert request.code is None

    def test_code_request(self) -> None:
        """Test request with OAuth code."""
        request = SocialTokenRequest(
            code="auth-code-123",
            redirect_uri="https://example.com/callback",
        )

        assert request.code == "auth-code-123"
        assert request.redirect_uri == "https://example.com/callback"

    def test_access_token_request(self) -> None:
        """Test request with access_token."""
        request = SocialTokenRequest(access_token="gho_xxxxxxxxxxxx")

        assert request.access_token == "gho_xxxxxxxxxxxx"


# =============================================================================
# Test SocialAuthError
# =============================================================================


class TestSocialAuthError:
    """Tests for SocialAuthError exception."""

    def test_error_creation(self) -> None:
        """Test creating a social auth error."""
        error = SocialAuthError(
            message="Invalid token",
            provider=SocialProvider.GOOGLE,
            code="invalid_token",
        )

        assert error.message == "Invalid token"
        assert error.provider == SocialProvider.GOOGLE
        assert error.code == "invalid_token"

    def test_error_string(self) -> None:
        """Test error string representation."""
        error = SocialAuthError(
            message="Token expired",
            provider=SocialProvider.APPLE,
        )

        assert str(error) == "[apple] Token expired"

    def test_error_default_code(self) -> None:
        """Test default error code."""
        error = SocialAuthError(
            message="Something went wrong",
            provider=SocialProvider.GITHUB,
        )

        assert error.code == "social_auth_error"


# =============================================================================
# Test SocialAuthService
# =============================================================================


@dataclass
class MockUserRecord:
    """Mock user record for testing."""

    id: str
    email: str
    username: str


class TestSocialAuthService:
    """Tests for SocialAuthService."""

    @pytest.fixture
    def mock_auth_store(self) -> MagicMock:
        """Create mock auth store."""
        store = MagicMock()
        store.get_user_by_email = MagicMock(return_value=None)
        store.create_user = MagicMock(
            return_value=MockUserRecord(
                id="user-123",
                email="test@example.com",
                username="testuser",
            )
        )
        return store

    @pytest.fixture
    def mock_jwt_service(self) -> MagicMock:
        """Create mock JWT service."""
        service = MagicMock()

        @dataclass
        class MockTokenPair:
            access_token: str = "access-token-123"
            refresh_token: str = "refresh-token-456"
            token_type: str = "bearer"
            expires_in: int = 3600

        service.create_token_pair = MagicMock(return_value=MockTokenPair())
        return service

    @pytest.fixture
    def mock_token_store(self) -> MagicMock:
        """Create mock token store."""
        store = MagicMock()
        store.create_token = MagicMock()
        return store

    @pytest.fixture
    def google_config(self) -> SocialAuthConfig:
        """Create Google-only config."""
        return SocialAuthConfig(google_client_id="google-client-123.apps.googleusercontent.com")

    @pytest.fixture
    def full_config(self) -> SocialAuthConfig:
        """Create full config with all providers."""
        return SocialAuthConfig(
            google_client_id="google-client-123.apps.googleusercontent.com",
            apple_team_id="TEAM123",
            apple_key_id="KEY456",
            apple_private_key="mock-apple-private-key-for-testing",
            apple_bundle_id="com.example.app",
            github_client_id="gh-client-123",
            github_client_secret="gh-secret-456",
        )

    def test_service_init(
        self,
        mock_auth_store: MagicMock,
        mock_jwt_service: MagicMock,
        mock_token_store: MagicMock,
        google_config: SocialAuthConfig,
    ) -> None:
        """Test service initialization."""
        service = SocialAuthService(
            auth_store=mock_auth_store,
            jwt_service=mock_jwt_service,
            token_store=mock_token_store,
            config=google_config,
        )

        assert service.auth_store is mock_auth_store
        assert service.jwt_service is mock_jwt_service
        assert service.config is google_config

    @pytest.mark.asyncio
    async def test_verify_google_missing_token(
        self,
        mock_auth_store: MagicMock,
        mock_jwt_service: MagicMock,
        mock_token_store: MagicMock,
        google_config: SocialAuthConfig,
    ) -> None:
        """Test Google auth fails without id_token."""
        service = SocialAuthService(
            auth_store=mock_auth_store,
            jwt_service=mock_jwt_service,
            token_store=mock_token_store,
            config=google_config,
        )

        request = SocialTokenRequest()  # No token

        with pytest.raises(SocialAuthError) as exc_info:
            await service._verify_provider_token(SocialProvider.GOOGLE, request)

        assert exc_info.value.code == "missing_token"
        assert exc_info.value.provider == SocialProvider.GOOGLE

    @pytest.mark.asyncio
    async def test_verify_google_not_configured(
        self,
        mock_auth_store: MagicMock,
        mock_jwt_service: MagicMock,
        mock_token_store: MagicMock,
    ) -> None:
        """Test Google auth fails when not configured."""
        config = SocialAuthConfig()  # No Google client ID
        service = SocialAuthService(
            auth_store=mock_auth_store,
            jwt_service=mock_jwt_service,
            token_store=mock_token_store,
            config=config,
        )

        request = SocialTokenRequest(id_token="some-token")

        with pytest.raises(SocialAuthError) as exc_info:
            await service._verify_provider_token(SocialProvider.GOOGLE, request)

        assert exc_info.value.code == "not_configured"

    @pytest.mark.asyncio
    async def test_verify_apple_missing_token(
        self,
        mock_auth_store: MagicMock,
        mock_jwt_service: MagicMock,
        mock_token_store: MagicMock,
        full_config: SocialAuthConfig,
    ) -> None:
        """Test Apple auth fails without id_token."""
        service = SocialAuthService(
            auth_store=mock_auth_store,
            jwt_service=mock_jwt_service,
            token_store=mock_token_store,
            config=full_config,
        )

        request = SocialTokenRequest()  # No token

        with pytest.raises(SocialAuthError) as exc_info:
            await service._verify_provider_token(SocialProvider.APPLE, request)

        assert exc_info.value.code == "missing_token"

    @pytest.mark.asyncio
    async def test_verify_apple_not_configured(
        self,
        mock_auth_store: MagicMock,
        mock_jwt_service: MagicMock,
        mock_token_store: MagicMock,
    ) -> None:
        """Test Apple auth fails when not fully configured."""
        config = SocialAuthConfig(apple_team_id="TEAM123")  # Partial config
        service = SocialAuthService(
            auth_store=mock_auth_store,
            jwt_service=mock_jwt_service,
            token_store=mock_token_store,
            config=config,
        )

        request = SocialTokenRequest(id_token="some-token")

        with pytest.raises(SocialAuthError) as exc_info:
            await service._verify_provider_token(SocialProvider.APPLE, request)

        assert exc_info.value.code == "not_configured"

    @pytest.mark.asyncio
    async def test_verify_github_missing_credentials(
        self,
        mock_auth_store: MagicMock,
        mock_jwt_service: MagicMock,
        mock_token_store: MagicMock,
        full_config: SocialAuthConfig,
    ) -> None:
        """Test GitHub auth fails without code or access_token."""
        service = SocialAuthService(
            auth_store=mock_auth_store,
            jwt_service=mock_jwt_service,
            token_store=mock_token_store,
            config=full_config,
        )

        request = SocialTokenRequest()  # No credentials

        with pytest.raises(SocialAuthError) as exc_info:
            await service._verify_provider_token(SocialProvider.GITHUB, request)

        assert exc_info.value.code == "missing_token"

    @pytest.mark.asyncio
    async def test_verify_github_code_not_configured(
        self,
        mock_auth_store: MagicMock,
        mock_jwt_service: MagicMock,
        mock_token_store: MagicMock,
    ) -> None:
        """Test GitHub code exchange fails when not configured."""
        config = SocialAuthConfig()  # No GitHub config
        service = SocialAuthService(
            auth_store=mock_auth_store,
            jwt_service=mock_jwt_service,
            token_store=mock_token_store,
            config=config,
        )

        request = SocialTokenRequest(code="auth-code")

        with pytest.raises(SocialAuthError) as exc_info:
            await service._verify_provider_token(SocialProvider.GITHUB, request)

        assert exc_info.value.code == "not_configured"

    @pytest.mark.asyncio
    async def test_get_or_create_user_existing(
        self,
        mock_auth_store: MagicMock,
        mock_jwt_service: MagicMock,
        mock_token_store: MagicMock,
        google_config: SocialAuthConfig,
    ) -> None:
        """Test finding existing user by email."""
        existing_user = MockUserRecord(
            id="existing-user-123",
            email="existing@example.com",
            username="existinguser",
        )
        mock_auth_store.get_user_by_email = MagicMock(return_value=existing_user)

        service = SocialAuthService(
            auth_store=mock_auth_store,
            jwt_service=mock_jwt_service,
            token_store=mock_token_store,
            config=google_config,
        )

        profile = SocialProfile(
            provider=SocialProvider.GOOGLE,
            provider_user_id="google-123",
            email="existing@example.com",
        )

        user = await service._get_or_create_user(profile)

        assert user.id == "existing-user-123"
        mock_auth_store.get_user_by_email.assert_called_once_with("existing@example.com")
        mock_auth_store.create_user.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_or_create_user_new(
        self,
        mock_auth_store: MagicMock,
        mock_jwt_service: MagicMock,
        mock_token_store: MagicMock,
        google_config: SocialAuthConfig,
    ) -> None:
        """Test creating new user from social profile."""
        mock_auth_store.get_user_by_email = MagicMock(return_value=None)

        service = SocialAuthService(
            auth_store=mock_auth_store,
            jwt_service=mock_jwt_service,
            token_store=mock_token_store,
            config=google_config,
        )

        profile = SocialProfile(
            provider=SocialProvider.GOOGLE,
            provider_user_id="google-123",
            email="new@example.com",
            name="New User",
        )

        user = await service._get_or_create_user(profile)

        assert user is not None
        mock_auth_store.create_user.assert_called_once()
        # Check call args
        call_kwargs = mock_auth_store.create_user.call_args.kwargs
        assert call_kwargs["email"] == "new@example.com"
        assert call_kwargs["username"] == "New User"

    @pytest.mark.asyncio
    async def test_get_or_create_user_uses_email_prefix_as_username(
        self,
        mock_auth_store: MagicMock,
        mock_jwt_service: MagicMock,
        mock_token_store: MagicMock,
        google_config: SocialAuthConfig,
    ) -> None:
        """Test username defaults to email prefix when name not provided."""
        mock_auth_store.get_user_by_email = MagicMock(return_value=None)

        service = SocialAuthService(
            auth_store=mock_auth_store,
            jwt_service=mock_jwt_service,
            token_store=mock_token_store,
            config=google_config,
        )

        profile = SocialProfile(
            provider=SocialProvider.GOOGLE,
            provider_user_id="google-123",
            email="john.doe@example.com",
            name=None,  # No name provided
        )

        await service._get_or_create_user(profile)

        call_kwargs = mock_auth_store.create_user.call_args.kwargs
        assert call_kwargs["username"] == "john.doe"

    @pytest.mark.asyncio
    async def test_authenticate_success(
        self,
        mock_auth_store: MagicMock,
        mock_jwt_service: MagicMock,
        mock_token_store: MagicMock,
        google_config: SocialAuthConfig,
    ) -> None:
        """Test successful authentication flow."""
        service = SocialAuthService(
            auth_store=mock_auth_store,
            jwt_service=mock_jwt_service,
            token_store=mock_token_store,
            config=google_config,
        )

        # Mock the profile verification
        mock_profile = SocialProfile(
            provider=SocialProvider.GOOGLE,
            provider_user_id="google-123",
            email="test@example.com",
            name="Test User",
        )

        with patch.object(service, "_verify_provider_token", new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = mock_profile

            request = SocialTokenRequest(id_token="valid-token")
            result = await service.authenticate(
                SocialProvider.GOOGLE,
                request,
                ip_address="127.0.0.1",
                user_agent="TestClient/1.0",
            )

        assert "access_token" in result
        assert "refresh_token" in result
        assert result["token_type"] == "bearer"
        assert "user" in result
        assert result["user"]["email"] == "test@example.com"
