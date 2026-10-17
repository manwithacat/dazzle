"""
Security configuration types for DAZZLE IR.

This module contains security-related IR types for configuring
application security behavior.
"""

from __future__ import annotations  # required: forward self-reference in class definitions

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class SecurityProfile(StrEnum):
    """
    Application security profile levels.

    All profiles include authentication and an admin workspace.
    The profile controls *how much* security infrastructure is generated,
    not whether auth exists.

    Profiles:
        BASIC: Prototyping and internal tools. Auth enabled but not required
            by default on surfaces. CORS allows all origins. Admin workspace
            includes: users, health, deploys, metrics.
        STANDARD: Production SaaS. Auth required by default, HSTS enabled,
            same-origin CORS. Admin workspace adds: sessions, processes.
        STRICT: Regulated / multi-tenant SaaS. Everything in STANDARD plus
            CSP headers.
    """

    BASIC = "basic"
    STANDARD = "standard"
    STRICT = "strict"


class TwoFactorMethod(StrEnum):
    """A second factor a user can enrol (DD-014). Recovery codes are always issued."""

    TOTP = "totp"
    EMAIL_OTP = "email_otp"


class TwoFactorConfig(BaseModel):
    """Two-factor sign-in policy, declared in ``dazzle.toml`` ``[auth.two_factor]`` (DD-014).

    Attributes:
        enabled: Whether users can enrol a second factor and sign-in challenges for it.
        methods: The factors a user may enrol.
        recovery_code_count: Single-use recovery codes minted at first enrolment.
        enforce_for_roles: A user holding any of these roles must complete a second
            factor at every sign-in; one with no factor enrolled can only reach enrolment.
    """

    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    methods: tuple[TwoFactorMethod, ...] = (TwoFactorMethod.TOTP,)
    recovery_code_count: int = 8
    enforce_for_roles: tuple[str, ...] = ()


class SecurityConfig(BaseModel):
    """
    Security configuration for the application.

    Derived from the security_profile setting and app configuration.

    Attributes:
        profile: The security profile level
        cors_origins: Allowed CORS origins (None = default based on profile)
        enable_hsts: Enable HTTP Strict Transport Security header
        enable_csp: Enable Content Security Policy header
        require_auth_by_default: Whether surfaces require auth unless opt-out
        two_factor: Two-factor sign-in policy (DD-014)
    """

    profile: SecurityProfile = SecurityProfile.BASIC
    cors_origins: list[str] | None = None
    enable_hsts: bool = False
    enable_csp: bool = False
    require_auth_by_default: bool = False
    # DD-014: set from dazzle.toml ``[auth.two_factor]`` by ``build_appspec``.
    two_factor: TwoFactorConfig = TwoFactorConfig()

    model_config = ConfigDict(frozen=True)

    @classmethod
    def from_profile(
        cls,
        profile: SecurityProfile,
        *,
        cors_origins: list[str] | None = None,
    ) -> SecurityConfig:
        """
        Create SecurityConfig from a profile with sensible defaults.

        Args:
            profile: The security profile level
            cors_origins: Custom CORS origins (overrides profile default)

        Returns:
            SecurityConfig with profile-based defaults
        """
        if profile == SecurityProfile.BASIC:
            return cls(
                profile=profile,
                cors_origins=cors_origins or ["*"],
                enable_hsts=False,
                enable_csp=False,
                require_auth_by_default=False,
            )
        elif profile == SecurityProfile.STANDARD:
            # Post-#833: CSP is enabled at the IR level for `standard`.
            # The runtime middleware emits the header in Report-Only mode
            # so violations surface without blocking — graduate to strict
            # to switch to enforcement.
            return cls(
                profile=profile,
                cors_origins=cors_origins,  # None = same-origin in production
                enable_hsts=True,
                enable_csp=True,
                require_auth_by_default=True,
            )
        else:  # STRICT
            return cls(
                profile=profile,
                cors_origins=cors_origins,  # None = same-origin only
                enable_hsts=True,
                enable_csp=True,
                require_auth_by_default=True,
            )
