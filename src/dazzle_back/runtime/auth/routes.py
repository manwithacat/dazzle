"""Session-based authentication routes (login, logout, register, etc.)."""

import logging
from dataclasses import dataclass
from datetime import timedelta
from functools import partial
from typing import Any

from dazzle_back.runtime._fastapi_compat import (
    FASTAPI_AVAILABLE,
    APIRouter,
    FastAPIRequest,
    JSONResponse,
    Response,
)

from .crypto import cookie_secure, verify_password
from .events import emit_user_logged_in, emit_user_password_changed, emit_user_registered
from .models import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
)
from .store import AuthStore

logger = logging.getLogger(__name__)


# =============================================================================
# Dependencies Container
# =============================================================================


@dataclass
class _AuthDeps:
    auth_store: AuthStore
    cookie_name: str
    session_expires_days: int
    persona_routes: dict[str, str] | None
    default_signup_roles: list[str] | None


# =============================================================================
# Helpers
# =============================================================================


def _require_auth(deps: _AuthDeps, request: FastAPIRequest) -> Any:
    """Extract and validate session, return auth context or raise 401."""
    from fastapi import HTTPException

    session_id = request.cookies.get(deps.cookie_name)
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    ctx = deps.auth_store.validate_session(session_id)
    if not ctx.is_authenticated or not ctx.user:
        raise HTTPException(status_code=401, detail="Session expired")
    return ctx


def _resolve_redirect(persona_routes: dict[str, str] | None, roles: list[str] | None) -> str:
    """Resolve persona landing page from user roles."""
    if persona_routes and roles:
        for role in roles:
            route = persona_routes.get(role.removeprefix("role_"))
            if route:
                return route
    return "/app"


# =============================================================================
# Module-level handler functions
# =============================================================================


async def _login(deps: _AuthDeps, credentials: LoginRequest, request: FastAPIRequest) -> Response:
    """Login with email and password.

    Returns session cookie on success, or 2FA challenge if enabled.
    """
    from fastapi import HTTPException

    user = deps.auth_store.authenticate(credentials.email, credentials.password)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Check if 2FA is enabled for this user
    if user.two_factor_enabled:
        # Create a short-lived pending session for 2FA verification
        pending_session = deps.auth_store.create_session(
            user,
            expires_in=timedelta(minutes=10),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
        methods = []
        if user.totp_enabled:
            methods.append("totp")
        if user.email_otp_enabled:
            methods.append("email_otp")

        return JSONResponse(
            content={
                "status": "2fa_required",
                "methods": methods,
                "session_token": pending_session.id,
                "user_id": str(user.id),
            },
            status_code=200,
        )

    # No 2FA — create full session
    session = deps.auth_store.create_session(
        user,
        expires_in=timedelta(days=deps.session_expires_days),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    redirect_url = _resolve_redirect(deps.persona_routes, user.roles)

    response = JSONResponse(
        content={
            "user": {
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
                "roles": user.roles,
            },
            "redirect_url": redirect_url,
            "message": "Login successful",
        }
    )

    response.set_cookie(
        key=deps.cookie_name,
        value=session.id,
        httponly=True,
        secure=cookie_secure(request),
        samesite="lax",
        max_age=deps.session_expires_days * 24 * 60 * 60,
    )

    await emit_user_logged_in(user, session_id=session.id)

    return response


async def _logout(deps: _AuthDeps, request: FastAPIRequest) -> Response:
    """Logout and delete session.

    HTML form submissions (no JSON accept header) are redirected to /login.
    API callers receive a JSON response.
    """
    from fastapi.responses import RedirectResponse

    session_id = request.cookies.get(deps.cookie_name)

    if session_id:
        deps.auth_store.delete_session(session_id)

    accept = request.headers.get("accept", "")
    is_htmx = request.headers.get("hx-request") == "true"
    is_browser = "text/html" in accept and "application/json" not in accept

    response: Response
    if is_htmx:
        response = Response(status_code=200, headers={"HX-Redirect": "/"})
    elif is_browser:
        response = RedirectResponse(url="/", status_code=303)
    else:
        response = JSONResponse(content={"message": "Logout successful"})
    response.delete_cookie(deps.cookie_name)

    return response


async def _register(deps: _AuthDeps, data: RegisterRequest, request: FastAPIRequest) -> Response:
    """Register a new user."""
    from fastapi import HTTPException

    if deps.auth_store.get_user_by_email(data.email):
        raise HTTPException(status_code=400, detail="Email already registered")

    try:
        user = deps.auth_store.create_user(
            email=data.email,
            password=data.password,
            username=data.username,
            roles=list(deps.default_signup_roles) if deps.default_signup_roles else None,
        )
    except Exception as e:
        logger.error("User registration failed: %s", e)
        raise HTTPException(status_code=400, detail="Registration failed")

    session = deps.auth_store.create_session(
        user,
        expires_in=timedelta(days=deps.session_expires_days),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    redirect_url = _resolve_redirect(deps.persona_routes, user.roles)

    response = JSONResponse(
        content={
            "user": {
                "id": str(user.id),
                "email": user.email,
                "username": user.username,
                "roles": user.roles,
            },
            "redirect_url": redirect_url,
            "message": "Registration successful",
        },
        status_code=201,
    )

    response.set_cookie(
        key=deps.cookie_name,
        value=session.id,
        httponly=True,
        secure=cookie_secure(request),
        samesite="lax",
        max_age=deps.session_expires_days * 24 * 60 * 60,
    )

    await emit_user_registered(user, session_id=session.id)

    return response


async def _get_me(deps: _AuthDeps, request: FastAPIRequest) -> dict[str, Any]:
    """Get current authenticated user."""
    from fastapi import HTTPException

    session_id = request.cookies.get(deps.cookie_name)

    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    auth_context = deps.auth_store.validate_session(session_id)

    if not auth_context.is_authenticated:
        raise HTTPException(status_code=401, detail="Session expired")

    user = auth_context.user
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    return {
        "id": str(user.id),
        "email": user.email,
        "username": user.username,
        "roles": user.roles,
        "is_superuser": user.is_superuser,
    }


async def _change_password(
    deps: _AuthDeps, data: ChangePasswordRequest, request: FastAPIRequest
) -> Response:
    """Change current user's password."""
    from fastapi import HTTPException

    session_id = request.cookies.get(deps.cookie_name)

    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    auth_context = deps.auth_store.validate_session(session_id)

    if not auth_context.is_authenticated:
        raise HTTPException(status_code=401, detail="Session expired")

    user = auth_context.user
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    deps.auth_store.update_password(user.id, data.new_password)
    deps.auth_store.delete_user_sessions(user.id)

    session = deps.auth_store.create_session(
        user,
        expires_in=timedelta(days=deps.session_expires_days),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    await emit_user_password_changed(user)

    response = JSONResponse(content={"message": "Password changed successfully"})

    response.set_cookie(
        key=deps.cookie_name,
        value=session.id,
        httponly=True,
        secure=cookie_secure(request),
        samesite="lax",
        max_age=deps.session_expires_days * 24 * 60 * 60,
    )

    return response


async def _forgot_password(
    deps: _AuthDeps, data: ForgotPasswordRequest, request: FastAPIRequest
) -> Response:
    """Request a password reset.

    Always returns 200 to avoid user enumeration. If the email exists,
    a reset token is created and logged (email delivery is integration-dependent).
    """
    import logging

    _logger = logging.getLogger("dazzle.auth")

    user = deps.auth_store.get_user_by_email(data.email)

    if user and user.is_active:
        token = deps.auth_store.create_password_reset_token(user.id)
        _logger.info(  # nosemgrep
            "Password reset requested for %s — token: %s "  # nosemgrep
            "(deliver via /auth/reset-password?token=%s)",
            data.email,
            token,
            token,
        )

    return JSONResponse(
        content={
            "message": (
                "If an account with that email exists, a password reset link has been sent."
            )
        }
    )


async def _reset_password(
    deps: _AuthDeps, data: ResetPasswordRequest, request: FastAPIRequest
) -> Response:
    """Reset password using a valid reset token.

    Validates the token, updates the password, invalidates existing sessions,
    and auto-logs the user in.
    """
    from fastapi import HTTPException

    user = deps.auth_store.validate_password_reset_token(data.token)

    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    deps.auth_store.update_password(user.id, data.new_password)
    deps.auth_store.consume_password_reset_token(data.token)
    deps.auth_store.delete_user_sessions(user.id)

    session = deps.auth_store.create_session(
        user,
        expires_in=timedelta(days=deps.session_expires_days),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    response = JSONResponse(content={"message": "Password reset successful"})

    response.set_cookie(
        key=deps.cookie_name,
        value=session.id,
        httponly=True,
        secure=cookie_secure(request),
        samesite="lax",
        max_age=deps.session_expires_days * 24 * 60 * 60,
    )

    return response


async def _get_preferences(deps: _AuthDeps, request: FastAPIRequest) -> dict[str, Any]:
    """Get all preferences for the current user."""
    ctx = _require_auth(deps, request)
    return {"preferences": ctx.preferences}


async def _set_preferences(deps: _AuthDeps, request: FastAPIRequest) -> dict[str, Any]:
    """Bulk set preferences. Body: {"preferences": {"key": "value", ...}}."""
    from fastapi import HTTPException

    ctx = _require_auth(deps, request)
    body = await request.json()
    prefs = body.get("preferences", {})
    if not isinstance(prefs, dict):
        raise HTTPException(status_code=400, detail="preferences must be an object")
    str_prefs = {str(k): str(v) for k, v in prefs.items()}
    assert ctx.user is not None
    deps.auth_store.set_preferences(ctx.user.id, str_prefs)
    return {"updated": len(str_prefs)}


async def _set_preference(deps: _AuthDeps, key: str, request: FastAPIRequest) -> dict[str, Any]:
    """Set a single preference. Body: {"value": "..."}."""
    ctx = _require_auth(deps, request)
    assert ctx.user is not None
    body = await request.json()
    value = body.get("value", "")
    deps.auth_store.set_preference(ctx.user.id, key, str(value))
    return {"key": key, "value": str(value)}


async def _delete_preference(deps: _AuthDeps, key: str, request: FastAPIRequest) -> Response:
    """Delete a single preference. Idempotent — 204 whether the key existed
    or not, per RFC 7231 §4.3.5 (#971)."""
    ctx = _require_auth(deps, request)
    assert ctx.user is not None
    deps.auth_store.delete_preference(ctx.user.id, key)
    return Response(status_code=204)


# =============================================================================
# Factory
# =============================================================================


def create_auth_routes(
    auth_store: AuthStore,
    cookie_name: str = "dazzle_session",
    session_expires_days: int = 7,
    persona_routes: dict[str, str] | None = None,
    default_signup_roles: list[str] | None = None,
) -> APIRouter:
    """Create authentication routes for FastAPI.

    Returns a router with login, logout, register, and me endpoints.

    Args:
        auth_store: Authentication store instance.
        cookie_name: Name of the session cookie.
        session_expires_days: Session cookie lifetime in days.
        persona_routes: Mapping of persona/role ID to default route URL.
            Used to include ``redirect_url`` in the login response so the
            client can navigate to the persona's landing page.
        default_signup_roles: Roles to assign to newly registered users.
            Typically the first persona ID (e.g. ``["customer"]``).
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is required for auth routes")

    import dazzle_back.runtime.rate_limit as _rl

    router = APIRouter(prefix="/auth", tags=["Authentication"])

    deps = _AuthDeps(
        auth_store=auth_store,
        cookie_name=cookie_name,
        session_expires_days=session_expires_days,
        persona_routes=persona_routes,
        default_signup_roles=default_signup_roles,
    )

    # Login
    login_handler = partial(_login, deps)
    login_handler = _rl.limits.limiter.limit(_rl.limits.auth_limit)(login_handler)  # type: ignore[misc,untyped-decorator,unused-ignore]
    router.post("/login", include_in_schema=False)(login_handler)

    # Logout
    router.post("/logout", include_in_schema=False)(partial(_logout, deps))

    # Register
    register_handler = partial(_register, deps)
    register_handler = _rl.limits.limiter.limit(_rl.limits.auth_limit)(register_handler)  # type: ignore[misc,untyped-decorator,unused-ignore]
    router.post("/register", status_code=201, include_in_schema=False)(register_handler)

    # Get Current User
    router.get("/me")(partial(_get_me, deps))

    # Change Password
    router.post("/change-password", include_in_schema=False)(partial(_change_password, deps))

    # Forgot Password
    forgot_handler = partial(_forgot_password, deps)
    forgot_handler = _rl.limits.limiter.limit(_rl.limits.auth_limit)(forgot_handler)  # type: ignore[misc,untyped-decorator,unused-ignore]
    router.post("/forgot-password", include_in_schema=False)(forgot_handler)

    # Reset Password
    reset_handler = partial(_reset_password, deps)
    reset_handler = _rl.limits.limiter.limit(_rl.limits.auth_limit)(reset_handler)  # type: ignore[misc,untyped-decorator,unused-ignore]
    router.post("/reset-password", include_in_schema=False)(reset_handler)

    # Preferences
    router.get("/preferences")(partial(_get_preferences, deps))
    router.put("/preferences")(partial(_set_preferences, deps))
    router.put("/preferences/{key:path}")(partial(_set_preference, deps))
    router.delete("/preferences/{key:path}")(partial(_delete_preference, deps))

    return router
