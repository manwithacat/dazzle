"""FastAPI dependencies for protected routes."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from .models import AuthContext
from .store import AuthStore

# FastAPI is optional - import for type hints and runtime
try:
    from fastapi import Request as FastAPIRequest

    FASTAPI_AVAILABLE = True
except ImportError:
    FastAPIRequest = None  # type: ignore[assignment,misc]
    FASTAPI_AVAILABLE = False


def create_auth_dependency(
    auth_store: AuthStore,
    cookie_name: str = "dazzle_session",
    require_roles: list[str] | None = None,
) -> Callable[[FastAPIRequest], Awaitable[AuthContext]]:
    """
    Create a FastAPI dependency for authentication.

    Use as a dependency in route functions to require authentication.

    Args:
        auth_store: Auth store instance
        cookie_name: Session cookie name
        require_roles: Required roles (if any)

    Returns:
        Dependency function

    Example:
        ```python
        get_current_user = create_auth_dependency(auth_store)

        @app.get("/protected")
        async def protected_route(user: AuthContext = Depends(get_current_user)):
            return {"user": user.user.email}
        ```
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is required for auth dependencies")

    from fastapi import HTTPException

    async def get_current_user(request: FastAPIRequest) -> AuthContext:
        """Get current authenticated user."""
        session_id = request.cookies.get(cookie_name)

        if not session_id:
            raise HTTPException(status_code=401, detail="Not authenticated")

        auth_context = auth_store.validate_session(session_id)

        if not auth_context.is_authenticated:
            raise HTTPException(status_code=401, detail="Session expired")

        # Check roles if required
        if require_roles:
            user_roles = set(auth_context.roles)
            required = set(require_roles)

            if not required.intersection(user_roles):
                raise HTTPException(
                    status_code=403,
                    detail=f"Required roles: {require_roles}",
                )

        return auth_context

    return get_current_user


def create_deny_dependency(
    auth_store: AuthStore,
    cookie_name: str = "dazzle_session",
    deny_roles: list[str] | None = None,
) -> Callable[[FastAPIRequest], Awaitable[AuthContext]]:
    """
    Create a FastAPI dependency that denies access for specific roles.

    Returns 403 if the authenticated user has any of the denied roles.

    Args:
        auth_store: Auth store instance
        cookie_name: Session cookie name
        deny_roles: Roles to deny (if user has any, returns 403)

    Returns:
        Dependency function
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is required for auth dependencies")

    from fastapi import HTTPException

    async def check_deny_roles(request: FastAPIRequest) -> AuthContext:
        """Reject users with denied roles."""
        session_id = request.cookies.get(cookie_name)

        if not session_id:
            return AuthContext()

        auth_context = auth_store.validate_session(session_id)

        if not auth_context.is_authenticated:
            return auth_context

        # Check deny roles
        if deny_roles:
            user_roles = set(auth_context.roles)
            denied = set(deny_roles)
            if user_roles.intersection(denied):
                raise HTTPException(
                    status_code=403,
                    detail=f"Access denied for roles: {list(user_roles & denied)}",
                )

        return auth_context

    return check_deny_roles


def create_optional_auth_dependency(
    auth_store: AuthStore,
    cookie_name: str = "dazzle_session",
) -> Callable[[FastAPIRequest], Awaitable[AuthContext]]:
    """
    Create a FastAPI dependency for optional authentication.

    Returns AuthContext even if not authenticated (is_authenticated=False).

    Args:
        auth_store: Auth store instance
        cookie_name: Session cookie name

    Returns:
        Dependency function
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is required for auth dependencies")

    async def get_optional_user(request: FastAPIRequest) -> AuthContext:
        """Get current user if authenticated, or empty context."""
        session_id = request.cookies.get(cookie_name)

        if not session_id:
            return AuthContext()

        return auth_store.validate_session(session_id)

    return get_optional_user
