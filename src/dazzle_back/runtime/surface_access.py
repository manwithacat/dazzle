"""
Surface access control enforcement for DNR-Back applications.

Enforces access control based on SurfaceAccessSpec:
- Authentication checks
- Persona-based authorization (allow_personas, deny_personas)
- Unauthenticated user handling (401 for API, redirect for UI)

The pure types (SurfaceAccessConfig, SurfaceAccessDenied, check_surface_access)
live in dazzle_ui.runtime.surface_access so the UI package can enforce access
control on page routes without importing dazzle_back.  This module re-exports
those types and adds the FastAPI-specific helpers (middleware factory, exception
handler) that are only needed in the backend.
"""

from collections.abc import Callable
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.responses import Response

from dazzle_ui.runtime.surface_access import (
    SurfaceAccessConfig,
    SurfaceAccessDenied,
    check_surface_access,
)

__all__ = [
    "SurfaceAccessConfig",
    "SurfaceAccessDenied",
    "check_surface_access",
    "get_user_personas_from_membership",
    "create_access_check_handler",
    "create_access_denied_handler",
]


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

        # ph is a DB driver placeholder constant ("?" or "%s"), not user input.
        # Pre-build both query variants to avoid string concatenation at call site.
        _queries = {
            "?": (
                'SELECT "personas" FROM "UserMembership" WHERE "user_id" = ? AND "tenant_id" = ?',
                'SELECT "personas" FROM "UserMembership" WHERE "user_id" = ?',
            ),
            "%s": (
                'SELECT "personas" FROM "UserMembership" WHERE "user_id" = %s AND "tenant_id" = %s',
                'SELECT "personas" FROM "UserMembership" WHERE "user_id" = %s',
            ),
        }
        _q_both, _q_user = _queries.get(ph, _queries["?"])

        with db_manager.connection() as conn:
            if tenant_id:
                cursor = conn.execute(_q_both, (user_id, tenant_id))
            else:
                cursor = conn.execute(_q_user, (user_id,))

            row = cursor.fetchone()
            if row:
                import json

                val = row["personas"] if isinstance(row, dict) else row[0]
                if val:
                    # Personas stored as JSON array
                    personas = json.loads(val) if isinstance(val, str) else val
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

    async def handle_access_denied(
        request: Request,
        exc: SurfaceAccessDenied,
    ) -> Response:
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
