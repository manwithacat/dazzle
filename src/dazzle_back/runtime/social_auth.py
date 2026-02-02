"""
OAuth2 Social Login for mobile clients.

Supports Google, Apple, and GitHub authentication via ID tokens or OAuth codes.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

# FastAPI imports - needed at module level for proper dependency injection
try:
    from fastapi import APIRouter, HTTPException, Request

    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    APIRouter = None  # type: ignore
    HTTPException = None  # type: ignore
    Request = None  # type: ignore

if TYPE_CHECKING:
    from dazzle_back.runtime.auth import AuthStore, UserRecord
    from dazzle_back.runtime.jwt_auth import JWTService
    from dazzle_back.runtime.token_store import TokenStore


# =============================================================================
# Social Provider Types
# =============================================================================


class SocialProvider(str, Enum):
    """Supported social login providers."""

    GOOGLE = "google"
    APPLE = "apple"
    GITHUB = "github"


@dataclass
class SocialProfile:
    """
    Profile information from social provider.

    Normalized profile data extracted from provider tokens.
    """

    provider: SocialProvider
    provider_user_id: str
    email: str
    email_verified: bool = True
    name: str | None = None
    given_name: str | None = None
    family_name: str | None = None
    picture_url: str | None = None
    raw_data: dict[str, Any] | None = None


@dataclass
class SocialAuthConfig:
    """
    Social authentication configuration.

    Configure providers with their client IDs and secrets.
    """

    # Google
    google_client_id: str | None = None

    # Apple
    apple_team_id: str | None = None
    apple_key_id: str | None = None
    apple_private_key: str | None = None  # PEM-encoded .p8 key
    apple_bundle_id: str | None = None

    # GitHub
    github_client_id: str | None = None
    github_client_secret: str | None = None


# =============================================================================
# Request/Response Models
# =============================================================================


class SocialTokenRequest(BaseModel):
    """Request body for social login."""

    id_token: str | None = Field(default=None, description="ID token from provider SDK")
    access_token: str | None = Field(default=None, description="Access token (for GitHub)")
    code: str | None = Field(default=None, description="OAuth authorization code")
    redirect_uri: str | None = Field(default=None, description="Redirect URI for code exchange")


# =============================================================================
# Provider Verifiers
# =============================================================================


async def verify_google_token(id_token: str, client_id: str) -> SocialProfile:
    """
    Verify Google ID token and extract profile.

    Uses google-auth library for token verification.

    Args:
        id_token: Google ID token from mobile SDK
        client_id: Google OAuth client ID

    Returns:
        Verified social profile

    Raises:
        SocialAuthError: If token is invalid
    """
    try:
        from google.auth.transport import requests
        from google.oauth2 import id_token as google_id_token
    except ImportError:
        raise SocialAuthError(
            "google-auth not installed. Install with: pip install google-auth",
            provider=SocialProvider.GOOGLE,
            code="missing_dependency",
        )

    try:
        # Verify the token
        idinfo = google_id_token.verify_oauth2_token(
            id_token,
            requests.Request(),
            client_id,
        )

        # Extract profile
        return SocialProfile(
            provider=SocialProvider.GOOGLE,
            provider_user_id=idinfo["sub"],
            email=idinfo["email"],
            email_verified=idinfo.get("email_verified", False),
            name=idinfo.get("name"),
            given_name=idinfo.get("given_name"),
            family_name=idinfo.get("family_name"),
            picture_url=idinfo.get("picture"),
            raw_data=dict(idinfo),
        )

    except ValueError as e:
        raise SocialAuthError(
            f"Invalid Google token: {e}",
            provider=SocialProvider.GOOGLE,
            code="invalid_token",
        )


async def verify_apple_token(
    id_token: str,
    *,
    team_id: str,
    key_id: str,
    bundle_id: str,
) -> SocialProfile:
    """
    Verify Apple ID token and extract profile.

    Apple tokens are JWTs signed with Apple's public keys.

    Args:
        id_token: Apple ID token from mobile SDK
        team_id: Apple Developer Team ID
        key_id: Apple Sign In Key ID
        bundle_id: App bundle ID

    Returns:
        Verified social profile

    Raises:
        SocialAuthError: If token is invalid
    """
    try:
        import jwt
        from jwt import PyJWKClient
    except ImportError:
        raise SocialAuthError(
            "PyJWT not installed. Install with: pip install PyJWT",
            provider=SocialProvider.APPLE,
            code="missing_dependency",
        )

    try:
        # Fetch Apple's public keys
        jwks_client = PyJWKClient("https://appleid.apple.com/auth/keys")
        signing_key = jwks_client.get_signing_key_from_jwt(id_token)

        # Verify and decode
        payload = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=bundle_id,
            issuer="https://appleid.apple.com",
        )

        return SocialProfile(
            provider=SocialProvider.APPLE,
            provider_user_id=payload["sub"],
            email=payload.get("email", ""),
            email_verified=payload.get("email_verified", False),
            name=None,  # Apple only provides name on first login
            raw_data=payload,
        )

    except jwt.InvalidTokenError as e:
        raise SocialAuthError(
            f"Invalid Apple token: {e}",
            provider=SocialProvider.APPLE,
            code="invalid_token",
        )


async def exchange_github_code(
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str | None = None,
) -> SocialProfile:
    """
    Exchange GitHub OAuth code for user profile.

    Args:
        code: OAuth authorization code
        client_id: GitHub OAuth App client ID
        client_secret: GitHub OAuth App client secret
        redirect_uri: Redirect URI used in authorization

    Returns:
        Verified social profile

    Raises:
        SocialAuthError: If code exchange fails
    """
    try:
        import httpx
    except ImportError:
        raise SocialAuthError(
            "httpx not installed. Install with: pip install httpx",
            provider=SocialProvider.GITHUB,
            code="missing_dependency",
        )

    async with httpx.AsyncClient() as client:
        # Exchange code for access token
        token_response = await client.post(
            "https://github.com/login/oauth/access_token",
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
        )

        if token_response.status_code != 200:
            raise SocialAuthError(
                "Failed to exchange GitHub code",
                provider=SocialProvider.GITHUB,
                code="token_exchange_failed",
            )

        token_data = token_response.json()
        if "error" in token_data:
            raise SocialAuthError(
                f"GitHub OAuth error: {token_data.get('error_description', token_data['error'])}",
                provider=SocialProvider.GITHUB,
                code="oauth_error",
            )

        access_token = token_data["access_token"]

        # Fetch user profile
        user_response = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )

        if user_response.status_code != 200:
            raise SocialAuthError(
                "Failed to fetch GitHub user profile",
                provider=SocialProvider.GITHUB,
                code="profile_fetch_failed",
            )

        user_data = user_response.json()

        # Fetch primary email
        email = user_data.get("email")
        if not email:
            emails_response = await client.get(
                "https://api.github.com/user/emails",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            if emails_response.status_code == 200:
                emails = emails_response.json()
                for email_data in emails:
                    if email_data.get("primary"):
                        email = email_data["email"]
                        break

        if not email:
            raise SocialAuthError(
                "No email found in GitHub profile",
                provider=SocialProvider.GITHUB,
                code="missing_email",
            )

        return SocialProfile(
            provider=SocialProvider.GITHUB,
            provider_user_id=str(user_data["id"]),
            email=email,
            email_verified=True,  # GitHub emails are verified
            name=user_data.get("name"),
            picture_url=user_data.get("avatar_url"),
            raw_data=user_data,
        )


async def verify_github_token(access_token: str) -> SocialProfile:
    """
    Verify GitHub access token and fetch user profile.

    For mobile apps that already have an access token.

    Args:
        access_token: GitHub access token

    Returns:
        Verified social profile
    """
    try:
        import httpx
    except ImportError:
        raise SocialAuthError(
            "httpx not installed. Install with: pip install httpx",
            provider=SocialProvider.GITHUB,
            code="missing_dependency",
        )

    async with httpx.AsyncClient() as client:
        # Fetch user profile
        user_response = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
        )

        if user_response.status_code != 200:
            raise SocialAuthError(
                "Invalid GitHub access token",
                provider=SocialProvider.GITHUB,
                code="invalid_token",
            )

        user_data = user_response.json()

        # Fetch primary email
        email = user_data.get("email")
        if not email:
            emails_response = await client.get(
                "https://api.github.com/user/emails",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            if emails_response.status_code == 200:
                emails = emails_response.json()
                for email_data in emails:
                    if email_data.get("primary"):
                        email = email_data["email"]
                        break

        if not email:
            raise SocialAuthError(
                "No email found in GitHub profile",
                provider=SocialProvider.GITHUB,
                code="missing_email",
            )

        return SocialProfile(
            provider=SocialProvider.GITHUB,
            provider_user_id=str(user_data["id"]),
            email=email,
            email_verified=True,
            name=user_data.get("name"),
            picture_url=user_data.get("avatar_url"),
            raw_data=user_data,
        )


# =============================================================================
# Social Auth Service
# =============================================================================


class SocialAuthService:
    """
    Social authentication service.

    Handles social login flow and user account linking.
    """

    def __init__(
        self,
        auth_store: AuthStore,
        jwt_service: JWTService,
        token_store: TokenStore,
        config: SocialAuthConfig,
    ):
        """
        Initialize social auth service.

        Args:
            auth_store: Auth store for user management
            jwt_service: JWT service for token creation
            token_store: Token store for refresh tokens
            config: Social provider configuration
        """
        self.auth_store = auth_store
        self.jwt_service = jwt_service
        self.token_store = token_store
        self.config = config

    async def authenticate(
        self,
        provider: SocialProvider,
        request: SocialTokenRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        """
        Authenticate with social provider.

        Verifies the token, creates/links user account, and returns JWT tokens.

        Args:
            provider: Social provider
            request: Token/code from provider
            ip_address: Client IP address
            user_agent: Client user agent

        Returns:
            Token response with access_token and refresh_token
        """
        # Verify token with provider
        profile = await self._verify_provider_token(provider, request)

        # Find or create user
        user = await self._get_or_create_user(profile)

        # Create tokens
        token_pair = self.jwt_service.create_token_pair(user)

        # Store refresh token
        self.token_store.create_token(
            user,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        return {
            "access_token": token_pair.access_token,
            "refresh_token": token_pair.refresh_token,
            "token_type": token_pair.token_type,
            "expires_in": token_pair.expires_in,
            "user": {
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
            },
        }

    async def _verify_provider_token(
        self,
        provider: SocialProvider,
        request: SocialTokenRequest,
    ) -> SocialProfile:
        """Verify token with the appropriate provider."""
        if provider == SocialProvider.GOOGLE:
            if not request.id_token:
                raise SocialAuthError(
                    "id_token required for Google login",
                    provider=provider,
                    code="missing_token",
                )
            if not self.config.google_client_id:
                raise SocialAuthError(
                    "Google client ID not configured",
                    provider=provider,
                    code="not_configured",
                )
            return await verify_google_token(
                request.id_token,
                self.config.google_client_id,
            )

        elif provider == SocialProvider.APPLE:
            if not request.id_token:
                raise SocialAuthError(
                    "id_token required for Apple login",
                    provider=provider,
                    code="missing_token",
                )
            if not all(
                [
                    self.config.apple_team_id,
                    self.config.apple_key_id,
                    self.config.apple_bundle_id,
                ]
            ):
                raise SocialAuthError(
                    "Apple Sign In not fully configured",
                    provider=provider,
                    code="not_configured",
                )
            return await verify_apple_token(
                request.id_token,
                team_id=self.config.apple_team_id,
                key_id=self.config.apple_key_id,
                bundle_id=self.config.apple_bundle_id,
            )

        elif provider == SocialProvider.GITHUB:
            if request.code:
                if not all(
                    [
                        self.config.github_client_id,
                        self.config.github_client_secret,
                    ]
                ):
                    raise SocialAuthError(
                        "GitHub OAuth not configured",
                        provider=provider,
                        code="not_configured",
                    )
                return await exchange_github_code(
                    request.code,
                    self.config.github_client_id,
                    self.config.github_client_secret,
                    request.redirect_uri,
                )
            elif request.access_token:
                return await verify_github_token(request.access_token)
            else:
                raise SocialAuthError(
                    "code or access_token required for GitHub login",
                    provider=provider,
                    code="missing_token",
                )

        raise SocialAuthError(
            f"Unsupported provider: {provider}",
            provider=provider,
            code="unsupported_provider",
        )

    async def _get_or_create_user(self, profile: SocialProfile) -> UserRecord:
        """
        Get existing user or create new one from social profile.

        Links accounts by email address.
        """
        # Try to find existing user by email
        user = self.auth_store.get_user_by_email(profile.email)

        if user:
            return user

        # Create new user with random password (social-only account)
        random_password = secrets.token_urlsafe(32)
        user = self.auth_store.create_user(
            email=profile.email,
            password=random_password,
            username=profile.name or profile.email.split("@")[0],
        )

        return user


# =============================================================================
# Routes
# =============================================================================


def create_social_auth_routes(
    social_service: SocialAuthService,
) -> APIRouter:
    """
    Create social authentication routes.

    Args:
        social_service: Social auth service instance

    Returns:
        FastAPI router with social auth endpoints
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is required for social auth routes")

    router = APIRouter(prefix="/auth/social", tags=["Social Authentication"])

    @router.post("/{provider}")
    async def social_login(
        provider: str,
        request_data: SocialTokenRequest,
        request: Request,
    ):
        """
        Authenticate with social provider.

        - Google: Send `id_token` from Google Sign-In SDK
        - Apple: Send `id_token` from Sign in with Apple
        - GitHub: Send `code` from OAuth flow or `access_token`
        """
        try:
            provider_enum = SocialProvider(provider.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported provider: {provider}. Supported: google, apple, github",
            )

        try:
            result = await social_service.authenticate(
                provider_enum,
                request_data,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
            return result
        except SocialAuthError as e:
            raise HTTPException(status_code=401, detail=str(e))

    return router


# =============================================================================
# Exceptions
# =============================================================================


class SocialAuthError(Exception):
    """Social authentication error."""

    def __init__(
        self,
        message: str,
        provider: SocialProvider,
        code: str = "social_auth_error",
    ):
        super().__init__(message)
        self.message = message
        self.provider = provider
        self.code = code

    def __str__(self) -> str:
        return f"[{self.provider.value}] {self.message}"
