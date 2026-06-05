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
    email_verified: bool = False
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
    # Declarative-CSRF Phase 1: the CSRF token is the session's own secret,
    # minted with the session and rotated only on session lifecycle events
    # (login/logout). See docs/superpowers/specs/2026-06-03-declarative-csrf-design.md.
    csrf_secret: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    # auth Plan 1a: pins the session's active organization (membership). Nullable
    # during the transition — legacy sessions predate memberships.
    active_membership_id: str | None = None


class MembershipRecord(BaseModel):
    """A user's membership in one organization (auth Plan 1a).

    The fenced join between a global ``Identity`` (a ``users`` row) and an
    ``Organization`` (tenant root). ``tenant_id`` is the discriminator value the
    RLS fence reads as ``dazzle.tenant_id``; ``roles`` are the personas this
    identity holds *in this org* (replacing the global ``users.roles`` source).
    """

    model_config = ConfigDict(frozen=True)

    id: str
    tenant_id: str
    identity_id: str
    roles: list[str] = Field(default_factory=list)
    status: str = "active"
    invited_by: str | None = None
    joined_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuthContext(BaseModel):
    """Current authentication context."""

    user: UserRecord | None = None
    session: SessionRecord | None = None
    is_authenticated: bool = False
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    preferences: dict[str, str] = Field(default_factory=dict)
    active_membership: MembershipRecord | None = None  # auth Plan 1a

    @property
    def user_id(self) -> UUID | None:
        """Get the authenticated user's ID, or None if not authenticated."""
        return self.user.id if self.user else None

    @property
    def effective_roles(self) -> list[str]:
        """Roles in effect for this request.

        Sourced from the active membership when present (the new per-org model);
        otherwise the legacy ``roles`` (global user roles) — the transition
        fallback until later slices migrate every app onto memberships.
        """
        if not self.is_authenticated:
            return []
        if self.active_membership is not None:
            return list(self.active_membership.roles)
        return list(self.roles)


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
