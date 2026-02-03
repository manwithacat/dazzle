"""
Security configuration types for DAZZLE IR.

This module contains security-related IR types for configuring
application security behavior.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class SecurityProfile(StrEnum):
    """
    Application security profile levels.

    Profiles define preset security configurations:
    - BASIC: Internal tools, minimal security, no auth required
    - STANDARD: Default SaaS, session auth, basic headers
    - STRICT: Multi-tenant SaaS, enforced isolation, full security headers
    """

    BASIC = "basic"
    STANDARD = "standard"
    STRICT = "strict"


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
        tenant_isolation: Enable tenant database isolation
    """

    profile: SecurityProfile = SecurityProfile.BASIC
    cors_origins: list[str] | None = None
    enable_hsts: bool = False
    enable_csp: bool = False
    require_auth_by_default: bool = False
    tenant_isolation: bool = False

    model_config = ConfigDict(frozen=True)

    @classmethod
    def from_profile(
        cls,
        profile: SecurityProfile,
        *,
        multi_tenant: bool = False,
        cors_origins: list[str] | None = None,
    ) -> SecurityConfig:
        """
        Create SecurityConfig from a profile with sensible defaults.

        Args:
            profile: The security profile level
            multi_tenant: Whether the app is multi-tenant
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
                tenant_isolation=False,
            )
        elif profile == SecurityProfile.STANDARD:
            return cls(
                profile=profile,
                cors_origins=cors_origins,  # None = same-origin in production
                enable_hsts=True,
                enable_csp=False,  # CSP can break many apps
                require_auth_by_default=True,
                tenant_isolation=False,
            )
        else:  # STRICT
            return cls(
                profile=profile,
                cors_origins=cors_origins,  # None = same-origin only
                enable_hsts=True,
                enable_csp=True,
                require_auth_by_default=True,
                tenant_isolation=multi_tenant,
            )
