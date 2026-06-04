"""FastAPI dependencies for protected routes."""

from collections.abc import Awaitable, Callable

from fastapi import HTTPException
from fastapi import Request as FastAPIRequest

from .models import AuthContext
from .store import AuthStore


def _bind_rls_tenant_id(auth_context: AuthContext) -> None:
    """Bind the RLS tenant id contextvar from the authenticated user (Phase B).

    The shared_schema RLS fence reads ``dazzle.tenant_id`` per transaction
    (``pg_backend.connection()`` sets it from this contextvar at lease time).
    Auth in Dazzle is a per-route FastAPI dependency resolved *before* the
    handler body runs — so the user's tenant only becomes available here, after
    ``TenantMiddleware`` and before any DB query. Setting the contextvar at this
    point therefore guarantees the GUC is bound within the same transaction as
    the fenced query.

    The tenant id is resolved via the same ``current_user.tenant_id`` lookup the
    scope filters use (built-in fields → preferences). A missing / unresolvable
    tenant is left unbound — the fence then denies (fail-closed). The value is
    never empty-string (companion §6.3): ``_resolve_user_attribute`` only returns
    a concrete scalar or the deny sentinel.

    asyncio gives each request task its own contextvar copy, so the binding dies
    with the task — no explicit reset needed (mirrors the audit-context wiring).
    """
    if not auth_context.is_authenticated:
        return
    # Local import: route_generator imports auth at module load, so importing it
    # at top level here would create a circular import.
    from dazzle.back.runtime.route_generator import _resolve_user_attribute
    from dazzle.back.runtime.tenant_isolation import set_current_tenant_id

    tenant_id = _resolve_user_attribute("tenant_id", auth_context)
    # "__RBAC_DENY__" means the attribute was absent — leave unbound (fail-closed).
    if isinstance(tenant_id, str) and tenant_id and tenant_id != "__RBAC_DENY__":
        set_current_tenant_id(tenant_id)


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

    async def get_current_user(request: FastAPIRequest) -> AuthContext:
        """Get current authenticated user."""
        from dazzle.back.runtime.auth.cookie_name import read_session_id

        session_id = read_session_id(request, default=cookie_name)

        if not session_id:
            raise HTTPException(status_code=401, detail="Not authenticated")

        auth_context = auth_store.validate_session(session_id)

        if not auth_context.is_authenticated:
            raise HTTPException(status_code=401, detail="Session expired")

        # #1289 slice 5 wiring: enforce cross-tenant cookie binding.
        # No-op on apps without a `tenant_host:` block.
        from dazzle.back.runtime.tenant.guard_wiring import enforce_cross_tenant

        enforce_cross_tenant(request, auth_context)

        # Check roles if required.
        # Database roles use "role_" prefix; persona IDs don't — normalize.
        if require_roles:
            user_roles = {r.removeprefix("role_") for r in auth_context.roles}
            required = set(require_roles)

            if not required.intersection(user_roles):
                raise HTTPException(
                    status_code=403,
                    detail=f"Required roles: {require_roles}",
                )

        _bind_rls_tenant_id(auth_context)
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

    async def check_deny_roles(request: FastAPIRequest) -> AuthContext:
        """Reject users with denied roles."""
        from dazzle.back.runtime.auth.cookie_name import read_session_id

        session_id = read_session_id(request, default=cookie_name)

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

        # Bind the RLS tenant id here too: if this deny-gate is ever used
        # standalone on a tenant-scoped route the GUC would otherwise be unset.
        # The bind is guarded on is_authenticated and fail-closed, so the
        # empty/unauthenticated early returns above need no equivalent call.
        _bind_rls_tenant_id(auth_context)
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

    async def get_optional_user(request: FastAPIRequest) -> AuthContext:
        """Get current user if authenticated, or empty context."""
        from dazzle.back.runtime.auth.cookie_name import read_session_id

        session_id = read_session_id(request, default=cookie_name)

        if not session_id:
            return AuthContext()

        auth_context = auth_store.validate_session(session_id)
        _bind_rls_tenant_id(auth_context)
        return auth_context

    return get_optional_user
