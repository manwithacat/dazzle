"""FastAPI dependencies for protected routes."""

from collections.abc import Awaitable, Callable

from fastapi import HTTPException
from fastapi import Request as FastAPIRequest

from .models import AuthContext
from .store import AuthStore


def _bind_rls_tenant_id(auth_context: AuthContext) -> None:
    """Bind the RLS tenant id + scope-attr GUCs from the authenticated user.

    Phase B binds ``dazzle.tenant_id`` (the shared_schema fence discriminator);
    Phase C additionally binds the app-wide set of ``dazzle.user_<attr>`` GUCs
    that the intra-tenant per-verb scope policies read. Both are set on the
    leased connection per transaction (``pg_backend.connection()`` reads the
    contextvars at lease time).

    Auth in Dazzle is a per-route FastAPI dependency resolved *before* the
    handler body runs — so the user's attributes only become available here, after
    ``TenantMiddleware`` and before any DB query. Setting the contextvars at this
    point therefore guarantees the GUCs are bound within the same transaction as
    the fenced/scoped query.

    Each attribute is resolved via the same ``current_user.<attr>`` lookup the
    app-layer scope filters use (built-in fields → preferences). A missing /
    unresolvable attribute (``__RBAC_DENY__``) is left unbound — its GUC stays
    unset so the fence / scope predicate denies (fail-closed). Values are never
    empty-string (companion §6.3): ``_resolve_user_attribute`` only returns a
    concrete scalar or the deny sentinel.

    The app-wide attr set is registered once at startup
    (``register_rls_user_attr_names``); when empty (non-``shared_schema`` / no
    scope rules) this resolves only ``tenant_id`` exactly as Phase B did.

    asyncio gives each request task its own contextvar copy, so the binding dies
    with the task — no explicit reset needed (mirrors the audit-context wiring).
    """
    if not auth_context.is_authenticated:
        return
    # Local import: scope_filters imports auth at module load, so importing it
    # at top level here would create a circular import.
    from dazzle.http.runtime.scope_filters import _resolve_user_attribute
    from dazzle.http.runtime.tenant_isolation import (
        get_rls_user_attr_names,
        set_current_rls_user_attrs,
        set_current_tenant_id,
    )

    # auth Plan 1d: tenant_id is bound ONLY from the active membership (the hard
    # FK source). The legacy preferences/domain-user fallback was removed (clean
    # break) — `_resolve_user_attribute("tenant_id")` is now itself
    # membership-only, so this stays consistent with the scope-filter path. A
    # membership-less session leaves dazzle.tenant_id unbound → the fence denies
    # (fail-closed). Never empty-string (companion §6.3).
    tenant_id = _resolve_user_attribute("tenant_id", auth_context)
    if isinstance(tenant_id, str) and tenant_id and tenant_id != "__RBAC_DENY__":
        set_current_tenant_id(tenant_id)

    # Phase C — resolve every scope-referenced current_user attr into the
    # per-request GUC map, keyed by the bare attr name (the connection layer
    # prefixes it with the shared USER_GUC_PREFIX → dazzle.user_<attr>). An attr
    # that resolves to the deny sentinel, an empty string, or a non-scalar is
    # omitted → its GUC stays unset → its predicate denies (fail-closed;
    # companion §6.3 — an empty-string GUC would also be a hard cast error).
    user_attr_names = get_rls_user_attr_names()
    if user_attr_names:
        resolved: dict[str, str] = {}
        for attr in user_attr_names:
            value = _resolve_user_attribute(attr, auth_context)
            if isinstance(value, str) and value and value != "__RBAC_DENY__":
                resolved[attr] = value
        if resolved:
            set_current_rls_user_attrs(resolved)


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
        from dazzle.http.runtime.auth.cookie_name import read_session_id

        session_id = read_session_id(request, default=cookie_name)

        if not session_id:
            raise HTTPException(status_code=401, detail="Not authenticated")

        auth_context = auth_store.validate_session(session_id)

        if not auth_context.is_authenticated:
            raise HTTPException(status_code=401, detail="Session expired")

        # #1289 slice 5 wiring: enforce cross-tenant cookie binding.
        # No-op on apps without a `tenant_host:` block.
        from dazzle.http.runtime.tenant.guard_wiring import enforce_cross_tenant

        enforce_cross_tenant(request, auth_context)

        # Check roles if required.
        # Database roles use "role_" prefix; persona IDs don't — normalize.
        # auth Plan 1a: read effective_roles (membership roles when a membership
        # is active, else the legacy user roles) so this gate is correct the
        # moment sessions activate a membership. The Cedar/permit: evaluation in
        # route_generator still sources user.roles — that switchover is Plan 1b.
        if require_roles:
            user_roles = {r.removeprefix("role_") for r in auth_context.effective_roles}
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
        from dazzle.http.runtime.auth.cookie_name import read_session_id

        session_id = read_session_id(request, default=cookie_name)

        if not session_id:
            return AuthContext()

        auth_context = auth_store.validate_session(session_id)

        if not auth_context.is_authenticated:
            return auth_context

        # Check deny roles (effective_roles — membership-aware; see get_current_user)
        if deny_roles:
            user_roles = set(auth_context.effective_roles)
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
        from dazzle.http.runtime.auth.cookie_name import read_session_id

        session_id = read_session_id(request, default=cookie_name)

        if not session_id:
            return AuthContext()

        auth_context = auth_store.validate_session(session_id)
        _bind_rls_tenant_id(auth_context)
        return auth_context

    return get_optional_user
