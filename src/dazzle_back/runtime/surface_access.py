"""
Surface access control enforcement for DNR-Back applications.

Enforces access control based on SurfaceAccessSpec:
- Authentication checks
- Persona-based authorization (allow_personas, deny_personas)
- Unauthenticated user handling (401 for API, redirect for UI)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import Request
    from fastapi.responses import JSONResponse, RedirectResponse


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


async def get_user_personas_from_membership(
    user_id: str,
    tenant_id: str | None,
    db_manager: Any,
) -> list[str]:
    """
    Get user personas from UserMembership entity.

    Queries the membership table to find the user's personas for the given tenant.

    Args:
        user_id: The user's ID
        tenant_id: The tenant ID (for multi-tenant apps)
        db_manager: Database manager for querying

    Returns:
        List of persona IDs the user has
    """
    if db_manager is None:
        return []

    try:
        # Query membership table
        # The membership table stores: user_id, tenant_id (optional), personas (JSON array)
        ph = getattr(db_manager, "placeholder", "?")

        with db_manager.connection() as conn:
            if tenant_id:
                cursor = conn.execute(
                    f'SELECT "personas" FROM "UserMembership" WHERE "user_id" = {ph} AND "tenant_id" = {ph}',
                    (user_id, tenant_id),
                )
            else:
                cursor = conn.execute(
                    f'SELECT "personas" FROM "UserMembership" WHERE "user_id" = {ph}',
                    (user_id,),
                )

            row = cursor.fetchone()
            if row and row[0]:
                import json

                # Personas stored as JSON array
                personas = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                return personas if isinstance(personas, list) else []

        return []
    except Exception:
        # Table doesn't exist or other error - return empty
        return []


# =============================================================================
# Middleware Helper
# =============================================================================


def create_access_check_handler(
    access_config: SurfaceAccessConfig,
    get_user_personas: Callable[[str, str | None], list[str]] | None = None,
    is_api_route: bool = True,
) -> Callable[..., Any]:
    """
    Create a FastAPI dependency that checks surface access.

    Args:
        access_config: Surface access configuration
        get_user_personas: Function to get user personas (user_id, tenant_id) -> personas
        is_api_route: Whether this is an API route

    Returns:
        FastAPI dependency function
    """
    from fastapi import HTTPException

    async def check_access(request: Request) -> None:
        """FastAPI dependency that checks surface access."""
        # Get current user from request state (set by auth middleware)
        user = getattr(request.state, "user", None)
        tenant_id = getattr(request.state, "tenant_id", None)

        # Get user personas if we have a user and a personas getter
        user_personas: list[str] = []
        if user and get_user_personas:
            user_id = user.get("id") or user.get("user_id")
            if user_id:
                user_personas = get_user_personas(user_id, tenant_id)

        try:
            check_surface_access(
                access_config,
                user,
                user_personas,
                is_api_request=is_api_route,
            )
        except SurfaceAccessDenied as e:
            if e.is_auth_required and not is_api_route and e.redirect_url:
                # Redirect for UI routes
                raise HTTPException(
                    status_code=302,
                    headers={"Location": e.redirect_url},
                )
            else:
                # Return JSON error for API routes
                status = 401 if e.is_auth_required else 403
                raise HTTPException(status_code=status, detail=e.reason)

    return check_access


def create_access_denied_handler() -> Callable[..., Any]:
    """
    Create an exception handler for SurfaceAccessDenied.

    Returns:
        FastAPI exception handler function
    """
    from fastapi.responses import JSONResponse, RedirectResponse

    async def handle_access_denied(
        request: Request,
        exc: SurfaceAccessDenied,
    ) -> JSONResponse | RedirectResponse:
        """Handle SurfaceAccessDenied exceptions."""
        # Check if this looks like an API request
        accept = request.headers.get("accept", "")
        is_api = "application/json" in accept or request.url.path.startswith("/api/")

        if exc.is_auth_required and not is_api and exc.redirect_url:
            return RedirectResponse(url=exc.redirect_url, status_code=302)
        else:
            status = 401 if exc.is_auth_required else 403
            return JSONResponse(
                status_code=status,
                content={"detail": exc.reason},
            )

    return handle_access_denied
