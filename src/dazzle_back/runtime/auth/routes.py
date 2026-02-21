"""Session-based authentication routes (login, logout, register, etc.)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from .crypto import cookie_secure, verify_password
from .models import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RegisterRequest,
    ResetPasswordRequest,
)
from .store import AuthStore

# FastAPI is optional - import for type hints and runtime
try:
    from fastapi import APIRouter
    from fastapi import Request as FastAPIRequest
    from fastapi.responses import JSONResponse
    from starlette.responses import Response

    FASTAPI_AVAILABLE = True
except ImportError:
    APIRouter = None  # type: ignore[assignment,misc]
    FastAPIRequest = None  # type: ignore[assignment,misc]
    JSONResponse = None  # type: ignore[assignment,misc]
    Response = None  # type: ignore[assignment,misc]
    FASTAPI_AVAILABLE = False


def create_auth_routes(
    auth_store: AuthStore,
    cookie_name: str = "dazzle_session",
    session_expires_days: int = 7,
    persona_routes: dict[str, str] | None = None,
    default_signup_roles: list[str] | None = None,
) -> APIRouter:
    """
    Create authentication routes for FastAPI.

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

    from fastapi import HTTPException

    router = APIRouter(prefix="/auth", tags=["Authentication"])

    # =========================================================================
    # Login
    # =========================================================================

    # Rate limiting — the module-level limiter is set by apply_rate_limiting()
    # which runs in _create_app() before routes are mounted.
    import dazzle_back.runtime.rate_limit as _rl

    @router.post("/login")
    @_rl.limiter.limit(_rl.auth_limit)  # type: ignore[misc]
    async def login(credentials: LoginRequest, request: FastAPIRequest) -> JSONResponse:
        """
        Login with email and password.

        Returns session cookie on success, or 2FA challenge if enabled.
        """
        user = auth_store.authenticate(credentials.email, credentials.password)

        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # Check if 2FA is enabled for this user
        if user.two_factor_enabled:
            # Create a short-lived pending session for 2FA verification
            pending_session = auth_store.create_session(
                user,
                expires_in=timedelta(minutes=10),
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
            # Store a mapping: use session id with a 2fa_pending prefix
            # The session is valid but marked as pending via response
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
        session = auth_store.create_session(
            user,
            expires_in=timedelta(days=session_expires_days),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        # Resolve persona landing page from user roles
        redirect_url = "/app"
        if persona_routes and user.roles:
            for role in user.roles:
                route = persona_routes.get(role)
                if route:
                    redirect_url = route
                    break

        # Return response with cookie
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
            key=cookie_name,
            value=session.id,
            httponly=True,
            secure=cookie_secure(request),
            samesite="lax",
            max_age=session_expires_days * 24 * 60 * 60,
        )

        return response

    # =========================================================================
    # Logout
    # =========================================================================

    @router.post("/logout")
    async def logout(request: FastAPIRequest) -> Response:
        """
        Logout and delete session.

        HTML form submissions (no JSON accept header) are redirected to /login.
        API callers receive a JSON response.
        """
        from fastapi.responses import RedirectResponse

        session_id = request.cookies.get(cookie_name)

        if session_id:
            auth_store.delete_session(session_id)

        # Detect request type: htmx (boosted form), browser, or API
        accept = request.headers.get("accept", "")
        is_htmx = request.headers.get("hx-request") == "true"
        is_browser = "text/html" in accept and "application/json" not in accept

        response: Response
        if is_htmx:
            # htmx: use HX-Redirect for full-page navigation (clears client state)
            response = Response(status_code=200, headers={"HX-Redirect": "/"})
        elif is_browser:
            response = RedirectResponse(url="/", status_code=303)
        else:
            response = JSONResponse(content={"message": "Logout successful"})
        response.delete_cookie(cookie_name)

        return response

    # =========================================================================
    # Register
    # =========================================================================

    @router.post("/register", status_code=201)
    @_rl.limiter.limit(_rl.auth_limit)  # type: ignore[misc]
    async def register(data: RegisterRequest, request: FastAPIRequest) -> JSONResponse:
        """
        Register a new user.
        """
        # Check if user exists
        if auth_store.get_user_by_email(data.email):
            raise HTTPException(status_code=400, detail="Email already registered")

        # Create user with default signup roles
        try:
            user = auth_store.create_user(
                email=data.email,
                password=data.password,
                username=data.username,
                roles=list(default_signup_roles) if default_signup_roles else None,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

        # Auto-login after registration
        session = auth_store.create_session(
            user,
            expires_in=timedelta(days=session_expires_days),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        # Resolve persona landing page from assigned roles
        redirect_url = "/app"
        if persona_routes and user.roles:
            for role in user.roles:
                route = persona_routes.get(role)
                if route:
                    redirect_url = route
                    break

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
            key=cookie_name,
            value=session.id,
            httponly=True,
            secure=cookie_secure(request),
            samesite="lax",
            max_age=session_expires_days * 24 * 60 * 60,
        )

        return response

    # =========================================================================
    # Get Current User
    # =========================================================================

    @router.get("/me")
    async def get_me(request: FastAPIRequest) -> dict[str, Any]:
        """
        Get current authenticated user.
        """
        session_id = request.cookies.get(cookie_name)

        if not session_id:
            raise HTTPException(status_code=401, detail="Not authenticated")

        auth_context = auth_store.validate_session(session_id)

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

    # =========================================================================
    # Change Password
    # =========================================================================

    @router.post("/change-password")
    async def change_password(data: ChangePasswordRequest, request: FastAPIRequest) -> JSONResponse:
        """
        Change current user's password.
        """
        session_id = request.cookies.get(cookie_name)

        if not session_id:
            raise HTTPException(status_code=401, detail="Not authenticated")

        auth_context = auth_store.validate_session(session_id)

        if not auth_context.is_authenticated:
            raise HTTPException(status_code=401, detail="Session expired")

        user = auth_context.user
        if user is None:
            raise HTTPException(status_code=401, detail="User not found")

        # Verify current password
        if not verify_password(data.current_password, user.password_hash):
            raise HTTPException(status_code=400, detail="Current password is incorrect")

        # Update password
        auth_store.update_password(user.id, data.new_password)

        # Invalidate all other sessions
        auth_store.delete_user_sessions(user.id)

        # Create new session
        session = auth_store.create_session(
            user,
            expires_in=timedelta(days=session_expires_days),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        response = JSONResponse(content={"message": "Password changed successfully"})

        response.set_cookie(
            key=cookie_name,
            value=session.id,
            httponly=True,
            secure=cookie_secure(request),
            samesite="lax",
            max_age=session_expires_days * 24 * 60 * 60,
        )

        return response

    # =========================================================================
    # Forgot Password (request reset)
    # =========================================================================

    @router.post("/forgot-password")
    @_rl.limiter.limit(_rl.auth_limit)  # type: ignore[misc]
    async def forgot_password(data: ForgotPasswordRequest, request: FastAPIRequest) -> JSONResponse:
        """
        Request a password reset.

        Always returns 200 to avoid user enumeration. If the email exists,
        a reset token is created and logged (email delivery is integration-dependent).
        """
        import logging

        logger = logging.getLogger("dazzle.auth")

        user = auth_store.get_user_by_email(data.email)

        if user and user.is_active:
            token = auth_store.create_password_reset_token(user.id)
            # Log the reset link — actual email delivery requires an integration
            logger.info(
                "Password reset requested for %s — token: %s "
                "(deliver via /auth/reset-password?token=%s)",
                data.email,
                token,
                token,
            )

        # Always return success to prevent user enumeration
        return JSONResponse(
            content={
                "message": (
                    "If an account with that email exists, a password reset link has been sent."
                )
            }
        )

    # =========================================================================
    # Reset Password (consume token + set new password)
    # =========================================================================

    @router.post("/reset-password")
    @_rl.limiter.limit(_rl.auth_limit)  # type: ignore[misc]
    async def reset_password(data: ResetPasswordRequest, request: FastAPIRequest) -> JSONResponse:
        """
        Reset password using a valid reset token.

        Validates the token, updates the password, invalidates existing sessions,
        and auto-logs the user in.
        """
        user = auth_store.validate_password_reset_token(data.token)

        if not user:
            raise HTTPException(status_code=400, detail="Invalid or expired reset token")

        # Update password and consume token
        auth_store.update_password(user.id, data.new_password)
        auth_store.consume_password_reset_token(data.token)

        # Invalidate all existing sessions
        auth_store.delete_user_sessions(user.id)

        # Auto-login with new session
        session = auth_store.create_session(
            user,
            expires_in=timedelta(days=session_expires_days),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        response = JSONResponse(content={"message": "Password reset successful"})

        response.set_cookie(
            key=cookie_name,
            value=session.id,
            httponly=True,
            secure=cookie_secure(request),
            samesite="lax",
            max_age=session_expires_days * 24 * 60 * 60,
        )

        return response

    return router
