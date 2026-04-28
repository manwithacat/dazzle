"""Session helpers for project route handlers (#933).

Custom route handlers (declared via `# dazzle:route-override` in a
project) need a way to authenticate the request without re-implementing
the cookie + sessions-table dance. This module exposes thin wrappers
around the framework's existing `AuthStore.validate_session`:

    from dazzle_back.runtime.auth import current_user_id, current_user, require_auth

    async def my_handler(request: Request):
        user_id = current_user_id(request)
        if user_id is None:
            return JSONResponse({"error": "unauthenticated"}, status_code=401)
        ...

    @require_auth(roles=["teacher"])
    async def my_protected_handler(request: Request, auth: AuthContext):
        ...

The active `AuthStore` is registered by the server at startup via
`register_auth_store(...)` — the helpers below close over that
module-level singleton, so they don't need any per-request wiring.

Anti-pattern this replaces: every project hand-rolls
`SELECT user_id FROM sessions WHERE id = %s AND expires_at > now()::text`
and silently gets the expiry handling wrong. The framework already
handles this via `AuthStore.validate_session`; these helpers expose
it to project code.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from .models import AuthContext

# Module-level singleton — set by server startup. None when auth is
# disabled or before the server has wired up its AuthStore.
_AUTH_STORE: Any = None
_COOKIE_NAME = "dazzle_session"


def register_auth_store(store: Any, cookie_name: str = "dazzle_session") -> None:
    """Wire an AuthStore so the helpers below can resolve sessions.

    Called by the server during startup once the AuthStore is created.
    Tests can call this directly to install a stub. Idempotent —
    re-registering replaces the prior reference (useful in tests where
    multiple servers spin up sequentially).
    """
    global _AUTH_STORE, _COOKIE_NAME
    _AUTH_STORE = store
    _COOKIE_NAME = cookie_name


def _resolve_auth(request: Any) -> AuthContext:
    """Read the session cookie and validate against the registered
    AuthStore. Returns an empty `AuthContext` (is_authenticated=False)
    in every failure mode — including auth being disabled — so callers
    can branch on `auth_context.is_authenticated` without surprises."""
    if _AUTH_STORE is None:
        return AuthContext()
    try:
        cookies = request.cookies
    except AttributeError:
        return AuthContext()
    session_id = cookies.get(_COOKIE_NAME) if cookies else None
    if not session_id:
        return AuthContext()
    try:
        result: AuthContext = _AUTH_STORE.validate_session(session_id)
        return result
    except Exception:
        # AuthStore can raise on malformed session tokens or DB errors.
        # The contract for these helpers is "best-effort" — surfacing
        # the exception would force every caller into a try/except,
        # defeating the point. Treat as unauthenticated and let the
        # caller's auth gate (or `require_auth`) return 401.
        return AuthContext()


def current_auth(request: Any) -> AuthContext:
    """Return the request's `AuthContext`. Always returns a context;
    check `.is_authenticated` to discriminate authenticated vs anon."""
    return _resolve_auth(request)


def current_user_id(request: Any) -> str | None:
    """Return the authenticated user's UUID as a string, or None."""
    auth = _resolve_auth(request)
    if not auth.is_authenticated or auth.user is None:
        return None
    return str(auth.user.id)


def current_user(request: Any) -> dict[str, Any] | None:
    """Return a JSON-serialisable dict of the authenticated user, or
    None. Mirrors the AegisMark-style `user` payload most projects want
    (id, email, roles, preferences). Use `current_auth` if you need the
    full pydantic AuthContext."""
    auth = _resolve_auth(request)
    if not auth.is_authenticated or auth.user is None:
        return None
    return {
        "id": str(auth.user.id),
        "email": auth.user.email,
        "roles": list(auth.roles),
        "preferences": dict(auth.preferences),
    }


def require_auth(
    roles: list[str] | None = None,
) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]:
    """Decorator that gates a route handler on session authentication.

    Returns a 401 JSONResponse if no valid session is present.
    Returns a 403 JSONResponse if `roles` is set and the user holds
    none of them. On success, injects an `auth: AuthContext` keyword
    argument into the wrapped handler.

    Example::

        @require_auth(roles=["teacher"])
        async def upload_handler(request: Request, auth: AuthContext):
            user_id = str(auth.user.id)
            ...

    The decorator only depends on the request object having a
    `.cookies` mapping and the wrapped handler being awaitable —
    framework-agnostic enough to drop into any FastAPI / Starlette
    custom route. Returns plain JSONResponse so projects don't need
    to import HTTPException."""
    required: set[str] = {r.removeprefix("role_") for r in (roles or [])}

    def decorator(
        handler: Callable[..., Awaitable[Any]],
    ) -> Callable[..., Awaitable[Any]]:
        @wraps(handler)
        async def wrapper(request: Any, *args: Any, **kwargs: Any) -> Any:
            from starlette.responses import JSONResponse

            auth = _resolve_auth(request)
            if not auth.is_authenticated:
                return JSONResponse(
                    {"error": "unauthenticated"},
                    status_code=401,
                )
            if required:
                user_roles = {r.removeprefix("role_") for r in auth.roles}
                if not required & user_roles:
                    return JSONResponse(
                        {"error": "forbidden", "required_roles": sorted(required)},
                        status_code=403,
                    )
            return await handler(request, *args, auth=auth, **kwargs)

        return wrapper

    return decorator
