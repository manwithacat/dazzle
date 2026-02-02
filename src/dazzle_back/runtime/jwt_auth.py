"""
JWT Authentication for mobile clients.

Provides JWT token creation, validation, and refresh for mobile app authentication.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from dazzle_back.runtime.auth import UserRecord

# =============================================================================
# JWT Configuration
# =============================================================================


# Security: Allowed algorithms whitelist (blocklist "none" and weak algorithms)
ALLOWED_ALGORITHMS = frozenset(
    {"HS256", "HS384", "HS512", "RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}
)
BLOCKED_ALGORITHMS = frozenset({"none", "None", "NONE", "nOnE"})  # Case variations of "none"

# Minimum secret key length for HMAC algorithms (256 bits = 32 bytes)
MIN_HMAC_SECRET_LENGTH = 32

# Maximum token length to prevent DoS attacks (16KB is generous)
MAX_TOKEN_LENGTH = 16 * 1024


@dataclass
class JWTConfig:
    """
    JWT configuration settings.

    Attributes:
        algorithm: JWT signing algorithm (HS256 or RS256)
        secret_key: Secret key for HS256 (auto-generated if not provided)
        private_key: PEM-encoded private key for RS256
        public_key: PEM-encoded public key for RS256
        access_token_expire_minutes: Access token lifetime
        refresh_token_expire_days: Refresh token lifetime
        issuer: Token issuer claim
        audience: Token audience claim (optional)
        verify_iat: Whether to verify issued-at claim
        leeway_seconds: Clock skew tolerance in seconds
    """

    algorithm: str = "HS256"
    secret_key: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    private_key: str | None = None
    public_key: str | None = None
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    issuer: str = "dazzle-app"
    audience: str | None = None
    verify_iat: bool = True
    leeway_seconds: int = 30  # Allow 30 seconds clock skew


# =============================================================================
# Token Models
# =============================================================================


class JWTClaims(BaseModel):
    """
    JWT token claims.

    Contains all claims encoded in the access token.
    """

    model_config = ConfigDict(frozen=True)

    sub: str = Field(description="Subject (user ID)")
    email: str = Field(description="User email")
    roles: list[str] = Field(default_factory=list, description="User roles")
    tenant_id: str | None = Field(default=None, description="Tenant ID for multi-tenancy")
    exp: int = Field(description="Expiration timestamp")
    iat: int = Field(description="Issued at timestamp")
    jti: str = Field(description="JWT ID for revocation tracking")
    iss: str = Field(description="Issuer")
    aud: str | None = Field(default=None, description="Audience")

    @property
    def user_id(self) -> UUID:
        """Get user ID as UUID."""
        return UUID(self.sub)

    @property
    def is_expired(self) -> bool:
        """Check if token is expired."""
        return datetime.now(UTC).timestamp() > self.exp


class TokenPair(BaseModel):
    """
    Access and refresh token pair.

    Returned after successful authentication.
    """

    model_config = ConfigDict(frozen=True)

    access_token: str = Field(description="JWT access token")
    refresh_token: str = Field(description="Opaque refresh token")
    token_type: str = Field(default="Bearer", description="Token type")
    expires_in: int = Field(description="Access token lifetime in seconds")


class TokenResponse(BaseModel):
    """
    Token response for API endpoints.

    OAuth2-compatible token response.
    """

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


# =============================================================================
# JWT Service
# =============================================================================


class JWTService:
    """
    JWT token service.

    Handles token creation, validation, and refresh.
    """

    def __init__(self, config: JWTConfig | None = None):
        """
        Initialize JWT service.

        Args:
            config: JWT configuration (uses defaults if not provided)
        """
        self.config = config or JWTConfig()
        self._validate_config()

    def _validate_config(self) -> None:
        """Validate JWT configuration for security."""
        # Check algorithm is allowed
        if self.config.algorithm in BLOCKED_ALGORITHMS:
            raise ValueError(f"Algorithm '{self.config.algorithm}' is blocked for security reasons")

        if self.config.algorithm not in ALLOWED_ALGORITHMS:
            raise ValueError(
                f"Algorithm '{self.config.algorithm}' is not allowed. "
                f"Allowed: {', '.join(sorted(ALLOWED_ALGORITHMS))}"
            )

        # RS256/RS384/RS512 require key pair
        if self.config.algorithm.startswith("RS") or self.config.algorithm.startswith("ES"):
            if not self.config.private_key or not self.config.public_key:
                raise ValueError(
                    f"{self.config.algorithm} requires both private_key and public_key"
                )

        # HMAC algorithms require sufficient secret key length
        if self.config.algorithm.startswith("HS"):
            if len(self.config.secret_key) < MIN_HMAC_SECRET_LENGTH:
                raise ValueError(
                    f"Secret key must be at least {MIN_HMAC_SECRET_LENGTH} bytes for HMAC algorithms. "
                    f"Got {len(self.config.secret_key)} bytes."
                )

    def _get_signing_key(self) -> str | bytes:
        """Get the key for signing tokens."""
        if self.config.algorithm == "RS256":
            return self.config.private_key or ""
        return self.config.secret_key

    def _get_verification_key(self) -> str | bytes:
        """Get the key for verifying tokens."""
        if self.config.algorithm == "RS256":
            return self.config.public_key or ""
        return self.config.secret_key

    def create_access_token(
        self,
        user_id: str | UUID,
        email: str,
        roles: list[str] | None = None,
        tenant_id: str | None = None,
    ) -> tuple[str, JWTClaims]:
        """
        Create a new access token.

        Args:
            user_id: User ID
            email: User email
            roles: User roles
            tenant_id: Tenant ID for multi-tenancy

        Returns:
            Tuple of (token string, claims)
        """
        try:
            import jwt
        except ImportError:
            raise RuntimeError("PyJWT is not installed. Install with: pip install PyJWT")

        now = datetime.now(UTC)
        exp = now + timedelta(minutes=self.config.access_token_expire_minutes)

        claims = JWTClaims(
            sub=str(user_id),
            email=email,
            roles=roles or [],
            tenant_id=tenant_id,
            exp=int(exp.timestamp()),
            iat=int(now.timestamp()),
            jti=secrets.token_urlsafe(16),
            iss=self.config.issuer,
            aud=self.config.audience,
        )

        # Build payload
        payload: dict[str, Any] = {
            "sub": claims.sub,
            "email": claims.email,
            "roles": claims.roles,
            "exp": claims.exp,
            "iat": claims.iat,
            "jti": claims.jti,
            "iss": claims.iss,
        }

        if claims.tenant_id:
            payload["tenant_id"] = claims.tenant_id
        if claims.aud:
            payload["aud"] = claims.aud

        token = jwt.encode(payload, self._get_signing_key(), algorithm=self.config.algorithm)

        return token, claims

    def verify_access_token(self, token: str) -> JWTClaims:
        """
        Verify and decode an access token.

        Args:
            token: JWT token string

        Returns:
            Decoded claims

        Raises:
            JWTError: If token is invalid or expired
        """
        # Security: Check token length to prevent DoS
        if len(token) > MAX_TOKEN_LENGTH:
            raise JWTError(
                f"Token exceeds maximum length ({MAX_TOKEN_LENGTH} bytes)",
                code="token_too_large",
            )

        try:
            import jwt
        except ImportError:
            raise RuntimeError("PyJWT is not installed. Install with: pip install PyJWT")

        # Security: Pre-check algorithm in header before full decode
        try:
            unverified_header = jwt.get_unverified_header(token)
            header_alg = unverified_header.get("alg", "")

            if header_alg in BLOCKED_ALGORITHMS:
                raise JWTError(
                    f"Algorithm '{header_alg}' is not allowed",
                    code="blocked_algorithm",
                )

            if header_alg not in ALLOWED_ALGORITHMS:
                raise JWTError(
                    f"Algorithm '{header_alg}' is not allowed",
                    code="invalid_algorithm",
                )
        except jwt.exceptions.DecodeError:
            raise JWTError("Malformed token header", code="invalid_token")

        try:
            # Decode and verify with explicit algorithm (prevents algorithm confusion)
            options: dict[str, Any] = {"require": ["sub", "email", "exp", "iat", "jti", "iss"]}
            if self.config.audience:
                options["require"].append("aud")

            payload = jwt.decode(
                token,
                self._get_verification_key(),
                algorithms=[
                    self.config.algorithm
                ],  # Explicit single algorithm - critical for security
                issuer=self.config.issuer,
                audience=self.config.audience,
                leeway=timedelta(seconds=self.config.leeway_seconds),
                options=options,
            )

            return JWTClaims(
                sub=payload["sub"],
                email=payload["email"],
                roles=payload.get("roles", []),
                tenant_id=payload.get("tenant_id"),
                exp=payload["exp"],
                iat=payload["iat"],
                jti=payload["jti"],
                iss=payload["iss"],
                aud=payload.get("aud"),
            )

        except jwt.ExpiredSignatureError:
            raise JWTError("Token has expired", code="token_expired")
        except jwt.InvalidTokenError as e:
            raise JWTError(f"Invalid token: {e}", code="invalid_token")

    def create_token_pair(
        self,
        user: UserRecord,
        tenant_id: str | None = None,
    ) -> TokenPair:
        """
        Create an access/refresh token pair.

        Args:
            user: User record
            tenant_id: Tenant ID for multi-tenancy

        Returns:
            Token pair with access and refresh tokens
        """
        # Create access token
        access_token, _ = self.create_access_token(
            user_id=user.id,
            email=user.email,
            roles=user.roles,
            tenant_id=tenant_id,
        )

        # Create refresh token (opaque)
        refresh_token = secrets.token_urlsafe(32)

        return TokenPair(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="Bearer",  # nosec B106 - OAuth2 token type, not a password
            expires_in=self.config.access_token_expire_minutes * 60,
        )

    def decode_token_unverified(self, token: str) -> dict[str, Any]:
        """
        Decode a token without verification.

        Useful for extracting claims from expired tokens during refresh.
        Still performs security checks on token structure.

        Args:
            token: JWT token string

        Returns:
            Token payload

        Raises:
            JWTError: If token structure is invalid
        """
        # Security: Check token length even for unverified decode
        if len(token) > MAX_TOKEN_LENGTH:
            raise JWTError(
                f"Token exceeds maximum length ({MAX_TOKEN_LENGTH} bytes)",
                code="token_too_large",
            )

        try:
            import jwt
        except ImportError:
            raise RuntimeError("PyJWT is not installed. Install with: pip install PyJWT")

        # Security: Check algorithm in header
        try:
            unverified_header = jwt.get_unverified_header(token)
            header_alg = unverified_header.get("alg", "")

            if header_alg in BLOCKED_ALGORITHMS:
                raise JWTError(
                    f"Algorithm '{header_alg}' is not allowed",
                    code="blocked_algorithm",
                )
        except jwt.exceptions.DecodeError:
            raise JWTError("Malformed token header", code="invalid_token")

        return jwt.decode(token, options={"verify_signature": False})


# =============================================================================
# Exceptions
# =============================================================================


class JWTError(Exception):
    """JWT authentication error."""

    def __init__(self, message: str, code: str = "jwt_error"):
        super().__init__(message)
        self.message = message
        self.code = code


# =============================================================================
# Factory Functions
# =============================================================================


def create_jwt_service(
    secret_key: str | None = None,
    algorithm: str = "HS256",
    access_token_expire_minutes: int = 15,
    refresh_token_expire_days: int = 7,
    issuer: str = "dazzle-app",
) -> JWTService:
    """
    Create a JWT service with the given configuration.

    Args:
        secret_key: Secret key for HS256 (auto-generated if not provided)
        algorithm: JWT algorithm (HS256 or RS256)
        access_token_expire_minutes: Access token lifetime
        refresh_token_expire_days: Refresh token lifetime
        issuer: Token issuer

    Returns:
        Configured JWT service
    """
    config = JWTConfig(
        algorithm=algorithm,
        secret_key=secret_key or secrets.token_urlsafe(32),
        access_token_expire_minutes=access_token_expire_minutes,
        refresh_token_expire_days=refresh_token_expire_days,
        issuer=issuer,
    )
    return JWTService(config)
