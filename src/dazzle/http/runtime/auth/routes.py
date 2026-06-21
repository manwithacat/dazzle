"""Session-based authentication routes (login, logout, register, etc.)."""

import logging
from dataclasses import dataclass
from datetime import timedelta
from functools import partial
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from fastapi import Request as FastAPIRequest
from fastapi.responses import JSONResponse, RedirectResponse

from .cookie_name import names_to_clear, read_session_id, select_write_name
from .crypto import cookie_secure, verify_password
from .events import emit_user_logged_in, emit_user_password_changed, emit_user_registered
from .models import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
)
from .org_activation import (
    Activated,
    HostForbidden,
    activate_session_for_login,
    memberships_required,
)
from .store import AuthStore

logger = logging.getLogger(__name__)


def _json_active_membership_id(auth_store: AuthStore, user: Any, request: Any) -> str | None:
    """Phase-2 activation for the JSON API login paths (auth Plan 1b).

    Returns the membership id to pin when exactly one org resolves (single
    membership or host-pin match); raises 403 when host-pinned to an org the
    identity isn't in. For the picker/no-orgs cases there is no HTML redirect to
    serve, so the session is created membership-less — the RLS fence then denies
    (1a: no active membership → unbound GUC) until the client picks via
    ``POST /auth/switch-org``. Fail-safe: an un-activated session sees nothing.

    #1418: the host-pin 403 applies only when the app gates login on membership.
    An app that declared ``tenant_host: membership_gated: false`` (so
    ``memberships_required`` is off) uses the host for resolution + the
    ``current_tenant`` lens and self-authorizes — proceed membership-less (legacy
    fence) on the JSON API path too, mirroring the HTML login redirect mapper.
    """
    outcome = activate_session_for_login(auth_store, user, request)
    if isinstance(outcome, HostForbidden):
        if memberships_required(request):
            raise HTTPException(status_code=403, detail="no membership for this organization")
        return None  # membership_gated: false — membership-less session, RLS fence applies
    if isinstance(outcome, Activated):
        return outcome.membership_id
    return None


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
    session_id = read_session_id(request, default=deps.cookie_name)
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

    # No 2FA — create full session.
    # Session-fixation defence (#1198): regenerate the session id on login
    # success — invalidate any pre-auth session cookie the client presented
    # so an attacker-planted id can't survive into the authenticated state.
    pre_auth_sid = read_session_id(request, default=deps.cookie_name)
    membership_id = _json_active_membership_id(deps.auth_store, user, request)  # Plan 1b
    session = deps.auth_store.create_session(
        user,
        expires_in=timedelta(days=deps.session_expires_days),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        active_membership_id=membership_id,
    )
    if pre_auth_sid and pre_auth_sid != session.id:
        deps.auth_store.delete_session(pre_auth_sid)

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
        key=select_write_name(request, user_roles=list(user.roles or []), default=deps.cookie_name),
        value=session.id,
        httponly=True,
        secure=cookie_secure(request),
        samesite="lax",
        max_age=deps.session_expires_days * 24 * 60 * 60,
    )

    # Declarative-CSRF Phase 1: bind the CSRF token to this session. httponly=False
    # so htmx/JS can echo it into the X-CSRF-Token header; SameSite=Lax + the
    # session-stable secret means it survives swaps/multi-tab. Rotates on login
    # (new session => new secret). See docs/superpowers/specs/2026-06-03-declarative-csrf-design.md.
    response.set_cookie(
        key="dazzle_csrf",
        value=session.csrf_secret,
        httponly=False,
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
    session_id = read_session_id(request, default=deps.cookie_name)

    # SP-initiated SAML SLO (#1342): resolve the IdP logout redirect BEFORE deleting the
    # session (it needs the session→connection). Local logout below is unconditional and
    # happens regardless — a broken IdP can never keep a session alive.
    slo_url: str | None = None
    if session_id:
        from dazzle.http.runtime.auth.saml_logout import saml_slo_redirect_url

        slo_url = saml_slo_redirect_url(deps.auth_store, request, session_id=session_id)
        deps.auth_store.delete_session(session_id)

    accept = request.headers.get("accept", "")
    is_htmx = request.headers.get("hx-request") == "true"
    is_browser = "text/html" in accept and "application/json" not in accept

    # `slo_url` (when set) is intentionally cross-origin — the operator-configured IdP SLO URL
    # built server-side by initiate_logout, NOT attacker input — so no same-origin guard here.
    response: Response
    if is_htmx:
        # SP-SLO is a browser flow; HTMX callers get the IdP redirect via HX-Redirect.
        response = Response(status_code=200, headers={"HX-Redirect": slo_url or "/"})
    elif is_browser:
        response = RedirectResponse(url=slo_url or "/", status_code=303)
    else:
        # JSON/API callers stay local (no browser to follow the IdP round-trip).
        response = JSONResponse(content={"message": "Logout successful"})
    for name in names_to_clear(request, default=deps.cookie_name):
        response.delete_cookie(name)
    # Declarative-CSRF Phase 1: drop the session-bound CSRF cookie on logout so a
    # stale secret can't linger past the session it was bound to.
    response.delete_cookie("dazzle_csrf")

    return response


async def _register(deps: _AuthDeps, data: RegisterRequest, request: FastAPIRequest) -> Response:
    """Register a new user."""
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

    # Session-fixation defence (#1198): regenerate the session id on
    # registration success — invalidate any pre-auth session cookie the
    # client presented so an attacker-planted id can't survive into the
    # newly-authenticated state.
    pre_auth_sid = read_session_id(request, default=deps.cookie_name)
    membership_id = _json_active_membership_id(deps.auth_store, user, request)  # Plan 1b
    session = deps.auth_store.create_session(
        user,
        expires_in=timedelta(days=deps.session_expires_days),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        active_membership_id=membership_id,
    )
    if pre_auth_sid and pre_auth_sid != session.id:
        deps.auth_store.delete_session(pre_auth_sid)

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
        key=select_write_name(request, user_roles=list(user.roles or []), default=deps.cookie_name),
        value=session.id,
        httponly=True,
        secure=cookie_secure(request),
        samesite="lax",
        max_age=deps.session_expires_days * 24 * 60 * 60,
    )

    # Declarative-CSRF Phase 1: bind the CSRF token to this freshly-created
    # session (registration auto-login). httponly=False so htmx/JS can echo it
    # into the X-CSRF-Token header. See
    # docs/superpowers/specs/2026-06-03-declarative-csrf-design.md.
    response.set_cookie(
        key="dazzle_csrf",
        value=session.csrf_secret,
        httponly=False,
        secure=cookie_secure(request),
        samesite="lax",
        max_age=deps.session_expires_days * 24 * 60 * 60,
    )

    await emit_user_registered(user, session_id=session.id)

    return response


async def _get_me(deps: _AuthDeps, request: FastAPIRequest) -> dict[str, Any]:
    """Get current authenticated user."""
    session_id = read_session_id(request, default=deps.cookie_name)

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
    session_id = read_session_id(request, default=deps.cookie_name)

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

    membership_id = _json_active_membership_id(deps.auth_store, user, request)  # Plan 1b
    session = deps.auth_store.create_session(
        user,
        expires_in=timedelta(days=deps.session_expires_days),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        active_membership_id=membership_id,
    )

    await emit_user_password_changed(user)

    response = JSONResponse(content={"message": "Password changed successfully"})

    response.set_cookie(
        key=select_write_name(request, user_roles=list(user.roles or []), default=deps.cookie_name),
        value=session.id,
        httponly=True,
        secure=cookie_secure(request),
        samesite="lax",
        max_age=deps.session_expires_days * 24 * 60 * 60,
    )

    # Declarative-CSRF Phase 1: re-bind the CSRF token to the new session minted
    # after a password change (old sessions were just invalidated). httponly=False
    # so htmx/JS can echo it. See
    # docs/superpowers/specs/2026-06-03-declarative-csrf-design.md.
    response.set_cookie(
        key="dazzle_csrf",
        value=session.csrf_secret,
        httponly=False,
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

    _logger = logging.getLogger(__name__)

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
    user = deps.auth_store.validate_password_reset_token(data.token)

    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")

    deps.auth_store.update_password(user.id, data.new_password)
    deps.auth_store.consume_password_reset_token(data.token)
    deps.auth_store.delete_user_sessions(user.id)

    membership_id = _json_active_membership_id(deps.auth_store, user, request)  # Plan 1b
    session = deps.auth_store.create_session(
        user,
        expires_in=timedelta(days=deps.session_expires_days),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        active_membership_id=membership_id,
    )

    response = JSONResponse(content={"message": "Password reset successful"})

    response.set_cookie(
        key=select_write_name(request, user_roles=list(user.roles or []), default=deps.cookie_name),
        value=session.id,
        httponly=True,
        secure=cookie_secure(request),
        samesite="lax",
        max_age=deps.session_expires_days * 24 * 60 * 60,
    )

    # Declarative-CSRF Phase 1: bind the CSRF token to the new session minted
    # by the reset-password auto-login. httponly=False so htmx/JS can echo it.
    # See docs/superpowers/specs/2026-06-03-declarative-csrf-design.md.
    response.set_cookie(
        key="dazzle_csrf",
        value=session.csrf_secret,
        httponly=False,
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
    import dazzle.http.runtime.rate_limit as _rl

    router = APIRouter(prefix="/auth", tags=["Authentication"])

    deps = _AuthDeps(
        auth_store=auth_store,
        cookie_name=cookie_name,
        session_expires_days=session_expires_days,
        persona_routes=persona_routes,
        default_signup_roles=default_signup_roles,
    )

    # Login — #1251: safe_limit handles the partial → __name__ introspection
    # incompatibility with slowapi's real Limiter (only bites when
    # security_profile != basic, i.e. when _NoOpLimiter isn't in play).
    login_handler = partial(_login, deps)
    login_handler = _rl.safe_limit(_rl.limits.auth_limit)(login_handler)
    router.post("/login", include_in_schema=False)(login_handler)

    # Logout
    router.post("/logout", include_in_schema=False)(partial(_logout, deps))

    # Register
    register_handler = partial(_register, deps)
    register_handler = _rl.safe_limit(_rl.limits.auth_limit)(register_handler)
    router.post("/register", status_code=201, include_in_schema=False)(register_handler)

    # Get Current User
    router.get("/me")(partial(_get_me, deps))

    # Change Password
    router.post("/change-password", include_in_schema=False)(partial(_change_password, deps))

    # Forgot Password
    forgot_handler = partial(_forgot_password, deps)
    forgot_handler = _rl.safe_limit(_rl.limits.auth_limit)(forgot_handler)
    router.post("/forgot-password", include_in_schema=False)(forgot_handler)

    # Reset Password
    reset_handler = partial(_reset_password, deps)
    reset_handler = _rl.safe_limit(_rl.limits.auth_limit)(reset_handler)
    router.post("/reset-password", include_in_schema=False)(reset_handler)

    # Preferences
    router.get("/preferences")(partial(_get_preferences, deps))
    router.put("/preferences")(partial(_set_preferences, deps))
    router.put("/preferences/{key:path}")(partial(_set_preference, deps))
    router.delete("/preferences/{key:path}")(partial(_delete_preference, deps))

    return router
