"""FastAPI dependencies for protected routes."""

from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException
from fastapi import Request as FastAPIRequest

from dazzle.core.strings import normalize_role
from dazzle.http.runtime.rls_bind import bind_rls_context
from dazzle.http.runtime.tenant_isolation import (
    get_current_tenant_schema,
    set_current_host_tenant_id,
    set_current_tenant_schema,
)

from .models import AuthContext
from .store import AuthStore


def _enforce_cross_tenant(request: FastAPIRequest, auth_context: AuthContext) -> None:
    """Run the cross-tenant cookie guard for an *authenticated* session (#1519).

    Shared post-validation step for every auth dependency factory so the guard
    can't be silently skipped on the deny / optional-auth paths (the #1519 gap:
    only ``create_auth_dependency`` called it, so a cross-tenant ``__Host-`` cookie
    presented on a deny/optional route reached the handler — the RLS fence still
    denied data, but the belt-and-suspenders cookie guard was absent).

    No-op when the context is unauthenticated: an expired or absent session on an
    optional/deny route is *anonymous*, not a violation, so it must fall through
    to the empty-context path rather than 403. Also a no-op for apps without a
    ``tenant_host:`` block (``enforce_cross_tenant`` returns early there). Raises
    ``HTTPException(403)`` on a genuine cross-tenant cookie.
    """
    if not auth_context.is_authenticated:
        return
    # Local import: guard_wiring is cheap but keep the import lazy to match the
    # rest of this module's request-time import style (avoids import cycles).
    from dazzle.http.runtime.tenant.guard_wiring import enforce_cross_tenant

    enforce_cross_tenant(request, auth_context)


def _bind_apex_lens(request: FastAPIRequest, auth_context: AuthContext) -> None:
    """On topology A, membership is the host lens (not the fence).

    Task-isolated (no middleware ``finally``). Leftover topology does not
    invent a lens.
    """
    if not auth_context.is_authenticated:
        return
    membership = auth_context.active_membership
    tenant_id = getattr(membership, "tenant_id", None) if membership is not None else None
    if not tenant_id:
        return
    app = getattr(request, "app", None)
    cfg = getattr(getattr(app, "state", None), "tenant_host", None) if app is not None else None
    if cfg is None or getattr(cfg, "topology", "") != "apex":
        return
    set_current_host_tenant_id(str(tenant_id))


def _bind_schema_from_membership(request: FastAPIRequest, auth_context: AuthContext) -> None:
    """Topology A / no Host slug: membership binds schema isolation search_path."""
    if not auth_context.is_authenticated:
        return
    if get_current_tenant_schema():
        return
    membership = auth_context.active_membership
    tenant_id = getattr(membership, "tenant_id", None) if membership is not None else None
    if not tenant_id:
        return
    registry = getattr(getattr(request, "app", None), "state", None)
    registry = getattr(registry, "tenant_registry", None) if registry is not None else None
    get_by_id = getattr(registry, "get_by_id", None)
    if not callable(get_by_id):
        return
    record = get_by_id(str(tenant_id))
    if record is None or getattr(record, "status", None) == "suspended":
        return
    schema = getattr(record, "schema_name", None)
    if schema:
        set_current_tenant_schema(str(schema))


def _resolve_auth_context(
    request: FastAPIRequest,
    auth_store: AuthStore,
    cookie_name: str,
) -> AuthContext:
    """Cookie if present (do not consult Authorization); else Bearer JWT."""
    from dazzle.http.runtime.auth.cookie_name import read_session_id

    session_id = read_session_id(request, default=cookie_name)
    if session_id:
        return auth_store.validate_session(session_id)

    verifier = getattr(getattr(request, "app", None), "state", None)
    jwt_verifier = getattr(verifier, "jwt_verifier", None) if verifier is not None else None
    get_ctx = getattr(jwt_verifier, "get_auth_context", None)
    if not callable(get_ctx):
        return AuthContext()
    jwt_auth = get_ctx(request)
    if not getattr(jwt_auth, "is_authenticated", False):
        return AuthContext()
    from dazzle.http.runtime.auth.jwt_bind import bind_jwt_tenant_context

    return bind_jwt_tenant_context(request, jwt_auth, auth_store)


def authenticate_request(
    request: FastAPIRequest,
    auth_store: AuthStore,
    cookie_name: str = "dazzle_session",
) -> AuthContext:
    """Resolve the request's ``AuthContext`` and bind its request-scoped tenancy.

    The one resolution point every auth seam shares (#1801): the CRUD auth
    dependencies below and the ``# dazzle:implements`` policy gate
    (``policy.check_entity_op``). Resolves the session cookie (else a Bearer JWT),
    runs the cross-tenant cookie guard (``HTTPException(403)`` on a cross-tenant
    ``__Host-`` cookie), then binds the RLS GUC contextvars (``dazzle.tenant_id`` /
    ``dazzle.user_<attr>``), the apex host lens and the membership schema, so any
    framework repository / service call made afterwards in the same request task
    reads through the caller's fence. Never raises for an anonymous or expired
    session: the context comes back with ``is_authenticated=False`` and nothing
    bound, and the caller decides whether that is a 401.
    """
    auth_context = _resolve_auth_context(request, auth_store, cookie_name)
    _enforce_cross_tenant(request, auth_context)
    bind_rls_context(auth_context)
    _bind_apex_lens(request, auth_context)
    _bind_schema_from_membership(request, auth_context)
    return auth_context


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
        # #1289 slice 5 / #1519: the cross-tenant cookie guard runs inside the shared
        # resolver; it and the RLS binding are no-ops for an unauthenticated context.
        auth_context = authenticate_request(request, auth_store, cookie_name)

        if session_id:
            if not auth_context.is_authenticated:
                raise HTTPException(status_code=401, detail="Session expired")
        elif not auth_context.is_authenticated:
            raise HTTPException(status_code=401, detail="Not authenticated")

        # Check roles if required.
        # Database roles use "role_" prefix; persona IDs don't — normalize.
        # auth Plan 1a: read effective_roles (membership roles when a membership
        # is active, else the legacy user roles) so this gate is correct the
        # moment sessions activate a membership. The Cedar/permit: evaluation in
        # route_generator still sources user.roles — that switchover is Plan 1b.
        if require_roles:
            user_roles = {normalize_role(r) for r in auth_context.effective_roles}
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

    async def check_deny_roles(request: FastAPIRequest) -> AuthContext:
        """Reject users with denied roles."""
        # #1519: the shared resolver 403s a cross-tenant `__Host-` cookie here too and
        # binds the RLS tenant, so a deny-gate used standalone on a tenant-scoped
        # route still reads through the fence.
        auth_context = authenticate_request(request, auth_store, cookie_name)

        if not auth_context.is_authenticated:
            return auth_context

        # Check deny roles (effective_roles — membership-aware; see get_current_user)
        if deny_roles:
            # Both sides normalise. Normalising only the user side (as the
            # require: gate does) made the two gates disagree: a `role_`-prefixed
            # user role never intersected a bare DSL persona name, so `deny:`
            # silently stopped denying (#1713). DB roles may carry the prefix
            # (route_support._normalize_role) and DSL personas are bare.
            user_roles = {normalize_role(r) for r in auth_context.effective_roles}
            denied = {normalize_role(r) for r in deny_roles}
            if user_roles.intersection(denied):
                raise HTTPException(
                    status_code=403,
                    detail=f"Access denied for roles: {sorted(user_roles & denied)}",
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

    async def get_optional_user(request: FastAPIRequest) -> AuthContext:
        """Get current user if authenticated, or empty context."""
        # #1519: an expired/invalid session stays anonymous; a valid cross-tenant
        # cookie 403s inside the shared resolver.
        return authenticate_request(request, auth_store, cookie_name)

    return get_optional_user


# Roles that count as "operator" for the runtime's introspection routes
# (``/_dazzle/*`` debug and services, ``/spec``, ``/db-info``, ``/_diagnostics``,
# the integrations retries explorer). A superuser passes regardless of role.
ADMIN_ROLES: frozenset[str] = frozenset({"super_admin", "trust_admin", "admin"})


def is_admin_context(auth_context: AuthContext | None) -> bool:
    """True when the context is an authenticated superuser or holds an admin role."""
    if auth_context is None or not auth_context.is_authenticated:
        return False
    user = auth_context.user
    if user is not None and getattr(user, "is_superuser", False):
        return True
    roles = {normalize_role(r) for r in auth_context.effective_roles}
    return bool(roles & ADMIN_ROLES)


def create_admin_dependency(
    auth_dep: Callable[..., Awaitable[AuthContext]],
) -> Callable[..., Awaitable[AuthContext]]:
    """Wrap a required-auth dependency so the route also requires an admin.

    ``auth_dep`` (from :func:`create_auth_dependency`) already answers 401 to
    anonymous callers; this adds the 403 for authenticated non-admins. Attach
    with ``dependencies=[Depends(create_admin_dependency(auth_dep))]`` so a
    route handler built with :func:`functools.partial` needs no signature change.
    """

    async def require_admin(auth_context: AuthContext = Depends(auth_dep)) -> AuthContext:
        if not auth_context.is_authenticated:
            raise HTTPException(status_code=401, detail="Not authenticated")
        if not is_admin_context(auth_context):
            raise HTTPException(status_code=403, detail="Admin access required")
        return auth_context

    return require_admin
