"""Pydantic models for authentication."""

import secrets
from datetime import UTC, datetime
from typing import Any
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
    # The IdP's stable user id for this membership (Entra = user objectId GUID),
    # captured from SCIM `externalId`. Lets a re-push under a changed email update
    # this membership instead of forking a duplicate identity (#1342 gap 1).
    external_id: str | None = None
    joined_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OrganizationRecord(BaseModel):
    """A framework-owned Organization — the tenant root in the shared-schema
    model (auth Plan 1c).

    ``id`` is the value the RLS fence reads as ``dazzle.tenant_id`` (and the
    ``tenant_id`` a ``MembershipRecord`` carries). Lives in the auth store
    alongside ``users``/``sessions``/``memberships`` (framework owns
    Identity/Org/Membership/Session), not the IR-entity pipeline. ``slug`` is
    unique; single-org apps use the fixed slug ``"default"`` so lazy
    provisioning is race-safe.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    slug: str
    name: str
    status: str = "active"
    is_test: bool = False
    settings: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ScimGroupRecord(BaseModel):
    """A SCIM 2.0 Group, connection-scoped (#1342).

    Members are tracked separately in ``scim_group_members`` and fetched on
    demand; this record carries only the group's own fields.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    connection_id: str
    display_name: str
    external_id: str | None = None  # the IdP's stable group id (Entra objectId GUID) — #1342
    created_at: str
    updated_at: str


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


def effective_roles_of(auth_context: object) -> list[str]:
    """Membership-first effective roles for an ``AuthContext``-shaped object.

    The duck-typed twin of :attr:`AuthContext.effective_roles` (auth Plan 1b),
    used by the runtime authorization sites (route_generator / policy) that take
    a loosely-typed ``auth_context``. Identical semantics to the property for a
    real ``AuthContext``: unauthenticated → ``[]``; an active membership wins
    (even an empty role list — so a membership with no roles does *not* leak the
    global ``user.roles``); otherwise the top-level ``roles``. It additionally
    falls back to the nested ``user.roles`` when no top-level ``roles`` is set,
    which only matters for partial/legacy auth-context shapes (the runtime always
    sets ``roles = user.roles`` at ``validate_session``).
    """
    if auth_context is None or not getattr(auth_context, "is_authenticated", False):
        return []
    membership = getattr(auth_context, "active_membership", None)
    if membership is not None:
        m_roles = getattr(membership, "roles", None)
        # A real MembershipRecord.roles is always a list (default_factory=list).
        # The isinstance guard also makes this robust to MagicMock auth-context
        # doubles, whose auto-created `active_membership` is truthy but has a
        # non-sequence `roles` — those fall through to the legacy roles below
        # instead of silently resolving to an empty role set (the same MagicMock
        # trap that requires `active_membership=None` in _bind_rls_tenant_id).
        if isinstance(m_roles, (list, tuple)):
            return list(m_roles)
    roles = getattr(auth_context, "roles", None)
    if isinstance(roles, (list, tuple)) and roles:
        return list(roles)
    user = getattr(auth_context, "user", None)
    user_roles = getattr(user, "roles", None)
    return list(user_roles) if isinstance(user_roles, (list, tuple)) else []


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
