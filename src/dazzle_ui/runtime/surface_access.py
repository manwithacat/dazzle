"""
Surface access control types for Dazzle UI page routes.

Pure Python types and check function — no FastAPI dependency.
These are used by page_routes.py to enforce access control on
server-rendered pages.

The dazzle_back package imports the FastAPI-specific helpers
(middleware factory, exception handler) from its own surface_access
module, which may delegate to these types.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# =============================================================================
# Access Control Exceptions
# =============================================================================


class SurfaceAccessDenied(Exception):
    """
    Exception raised when access to a surface is denied.

    Attributes:
        reason: Human-readable reason for denial
        redirect_url: URL to redirect to (for UI surfaces)
        is_auth_required: Whether the denial is due to missing authentication
    """

    def __init__(
        self,
        reason: str,
        *,
        redirect_url: str | None = None,
        is_auth_required: bool = False,
    ):
        super().__init__(reason)
        self.reason = reason
        self.redirect_url = redirect_url
        self.is_auth_required = is_auth_required


# =============================================================================
# Access Spec Data Class
# =============================================================================


@dataclass
class SurfaceAccessConfig:
    """
    Runtime access configuration for a surface.

    Derived from SurfaceAccessSpec IR type.
    """

    require_auth: bool = False
    allow_personas: list[str] | None = None  # None = all authenticated users allowed
    deny_personas: list[str] | None = None
    redirect_unauthenticated: str = "/"

    @classmethod
    def from_spec(cls, spec: Any) -> SurfaceAccessConfig:
        """
        Create from SurfaceAccessSpec.

        Args:
            spec: SurfaceAccessSpec object

        Returns:
            SurfaceAccessConfig instance
        """
        if spec is None:
            return cls()

        return cls(
            require_auth=spec.require_auth,
            allow_personas=spec.allow_personas if spec.allow_personas else None,
            deny_personas=spec.deny_personas if spec.deny_personas else None,
            redirect_unauthenticated=spec.redirect_unauthenticated or "/",
        )


# =============================================================================
# Access Check Functions
# =============================================================================


def check_surface_access(
    access_config: SurfaceAccessConfig,
    user: dict[str, Any] | None,
    user_personas: list[str] | None = None,
    is_api_request: bool = True,
) -> None:
    """
    Check if a user can access a surface.

    Args:
        access_config: Surface access configuration
        user: Current user dict (from auth middleware) or None
        user_personas: List of persona IDs the user has (from membership)
        is_api_request: Whether this is an API request (vs UI route)

    Raises:
        SurfaceAccessDenied: If access is denied
    """
    # No auth required - allow all
    if not access_config.require_auth:
        return

    # Auth required but no user
    if user is None:
        raise SurfaceAccessDenied(
            "Authentication required",
            redirect_url=access_config.redirect_unauthenticated if not is_api_request else None,
            is_auth_required=True,
        )

    # User is authenticated - check personas
    user_personas = user_personas or []

    # Check deny list first (explicit denials take precedence)
    if access_config.deny_personas:
        for denied in access_config.deny_personas:
            if denied in user_personas:
                raise SurfaceAccessDenied(
                    f"Access denied for persona '{denied}'",
                    is_auth_required=False,
                )

    # Check allow list (if specified)
    if access_config.allow_personas:
        # User must have at least one of the allowed personas
        has_allowed_persona = any(p in user_personas for p in access_config.allow_personas)
        if not has_allowed_persona:
            raise SurfaceAccessDenied(
                f"Requires one of personas: {access_config.allow_personas}",
                is_auth_required=False,
            )

    # All checks passed
