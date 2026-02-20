"""Pydantic models for authentication."""

import secrets
from datetime import UTC, datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# Core Models
# =============================================================================


class UserRecord(BaseModel):
    """User record for authentication."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    email: str
    password_hash: str
    username: str | None = None
    is_active: bool = True
    is_superuser: bool = False
    roles: list[str] = Field(default_factory=list)
    totp_secret: str | None = None
    totp_enabled: bool = False
    email_otp_enabled: bool = False
    recovery_codes_generated: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def two_factor_enabled(self) -> bool:
        """Whether any 2FA method is active."""
        return self.totp_enabled or self.email_otp_enabled


class SessionRecord(BaseModel):
    """Session record for authentication."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    user_id: UUID
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime
    ip_address: str | None = None
    user_agent: str | None = None


class AuthContext(BaseModel):
    """Current authentication context."""

    user: UserRecord | None = None
    session: SessionRecord | None = None
    is_authenticated: bool = False
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)

    @property
    def user_id(self) -> UUID | None:
        """Get the authenticated user's ID, or None if not authenticated."""
        return self.user.id if self.user else None


# =============================================================================
# Request Models
# =============================================================================


class LoginRequest(BaseModel):
    """Login request body."""

    email: str
    password: str


class RegisterRequest(BaseModel):
    """Registration request body."""

    email: str
    password: str
    username: str | None = None


class ChangePasswordRequest(BaseModel):
    """Change password request body."""

    current_password: str
    new_password: str


class ForgotPasswordRequest(BaseModel):
    """Forgot password request body."""

    email: str


class ResetPasswordRequest(BaseModel):
    """Reset password request body."""

    token: str
    new_password: str


class TwoFactorVerifyRequest(BaseModel):
    """2FA verification request body."""

    code: str
    method: str = "totp"  # "totp", "email_otp", or "recovery"
    session_token: str = ""


class TwoFactorSetupRequest(BaseModel):
    """2FA TOTP setup verification request body."""

    code: str


class TokenRequest(BaseModel):
    """Token request body (OAuth2 compatible)."""

    username: str  # email
    password: str
    grant_type: str = "password"


class RefreshTokenRequest(BaseModel):
    """Refresh token request body."""

    refresh_token: str


class TokenRevokeRequest(BaseModel):
    """Token revocation request body."""

    refresh_token: str
