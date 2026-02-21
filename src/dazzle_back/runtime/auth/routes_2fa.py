"""Two-factor authentication routes."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from .crypto import cookie_secure
from .models import TwoFactorSetupRequest, TwoFactorVerifyRequest, UserRecord
from .store import AuthStore

# FastAPI is optional - import for type hints and runtime
try:
    from fastapi import APIRouter
    from fastapi import Request as FastAPIRequest
    from fastapi.responses import JSONResponse

    FASTAPI_AVAILABLE = True
except ImportError:
    APIRouter = None  # type: ignore[assignment,misc]
    FastAPIRequest = None  # type: ignore[assignment,misc]
    JSONResponse = None  # type: ignore[assignment,misc]
    FASTAPI_AVAILABLE = False


def create_2fa_routes(
    auth_store: AuthStore,
    cookie_name: str = "dazzle_session",
    session_expires_days: int = 7,
    database_url: str | None = None,
) -> APIRouter:
    """Create two-factor authentication routes.

    Args:
        auth_store: Authentication store instance
        cookie_name: Session cookie name
        session_expires_days: Session cookie lifetime in days
        database_url: PostgreSQL URL for OTP/recovery stores
    """
    if not FASTAPI_AVAILABLE:
        raise RuntimeError("FastAPI is required for 2FA routes")

    from fastapi import HTTPException

    router = APIRouter(prefix="/auth/2fa", tags=["Two-Factor Authentication"])

    # Lazy initialization of stores
    _stores: dict[str, Any] = {}

    def _get_otp_store() -> Any:
        if "otp" not in _stores and database_url:
            from dazzle_back.runtime.otp_store import OTPStore

            store = OTPStore(database_url)
            store.init_db()
            _stores["otp"] = store
        return _stores.get("otp")

    def _get_recovery_store() -> Any:
        if "recovery" not in _stores and database_url:
            from dazzle_back.runtime.recovery_codes import RecoveryCodeStore

            store = RecoveryCodeStore(database_url)
            store.init_db()
            _stores["recovery"] = store
        return _stores.get("recovery")

    def _get_current_user(request: FastAPIRequest) -> UserRecord:
        """Get authenticated user from session cookie."""
        session_id = request.cookies.get(cookie_name)
        if not session_id:
            raise HTTPException(status_code=401, detail="Not authenticated")
        auth_context = auth_store.validate_session(session_id)
        if not auth_context.is_authenticated or not auth_context.user:
            raise HTTPException(status_code=401, detail="Session expired")
        return auth_context.user

    # =========================================================================
    # TOTP Setup
    # =========================================================================

    @router.post("/setup/totp")
    async def setup_totp(request: FastAPIRequest) -> dict[str, str]:
        """Start TOTP setup — returns secret and QR code URI."""
        from dazzle_back.runtime.totp import generate_totp_secret, get_totp_uri

        user = _get_current_user(request)

        if user.totp_enabled:
            raise HTTPException(status_code=400, detail="TOTP is already enabled")

        secret = generate_totp_secret()
        uri = get_totp_uri(secret, user.email)

        # Temporarily store the secret (not enabled yet)
        auth_store.enable_totp(user.id, secret)
        # Mark as not yet enabled — we store the secret but set totp_enabled=False
        # until verification succeeds
        auth_store._execute_modify(
            "UPDATE users SET totp_enabled = FALSE WHERE id = %s",
            (str(user.id),),
        )

        return {"secret": secret, "uri": uri}

    @router.post("/verify/totp")
    async def verify_totp_setup(
        data: TwoFactorSetupRequest, request: FastAPIRequest
    ) -> dict[str, Any]:
        """Verify TOTP code to complete setup."""
        from dazzle_back.runtime.totp import verify_totp

        user = _get_current_user(request)
        secret = auth_store.get_totp_secret(user.id)

        if not secret:
            raise HTTPException(status_code=400, detail="TOTP setup not started")

        if not verify_totp(secret, data.code):
            raise HTTPException(status_code=400, detail="Invalid TOTP code")

        # Enable TOTP
        auth_store.enable_totp(user.id, secret)

        # Generate recovery codes if not already generated
        recovery_codes = None
        recovery_store = _get_recovery_store()
        if recovery_store and not user.recovery_codes_generated:
            from dazzle_back.runtime.recovery_codes import generate_recovery_codes

            codes = generate_recovery_codes()
            recovery_store.store_codes(user.id, codes)
            auth_store.set_recovery_codes_generated(user.id, True)
            recovery_codes = codes

        result: dict[str, Any] = {"message": "TOTP enabled successfully"}
        if recovery_codes:
            result["recovery_codes"] = recovery_codes
        return result

    # =========================================================================
    # Email OTP Setup
    # =========================================================================

    @router.post("/setup/email-otp")
    async def setup_email_otp(request: FastAPIRequest) -> dict[str, str]:
        """Enable email OTP method."""
        user = _get_current_user(request)
        auth_store.enable_email_otp(user.id)

        # Generate recovery codes if not already generated
        recovery_store = _get_recovery_store()
        if recovery_store and not user.recovery_codes_generated:
            from dazzle_back.runtime.recovery_codes import generate_recovery_codes

            codes = generate_recovery_codes()
            recovery_store.store_codes(user.id, codes)
            auth_store.set_recovery_codes_generated(user.id, True)

        return {"message": "Email OTP enabled"}

    # =========================================================================
    # 2FA Challenge (during login)
    # =========================================================================

    @router.post("/challenge")
    async def challenge_2fa(data: TwoFactorVerifyRequest) -> dict[str, str]:
        """Send 2FA challenge (email OTP) during login.

        The session_token comes from the login response when 2FA is required.
        """
        # Validate the pending session
        auth_context = auth_store.validate_session(data.session_token)
        if not auth_context.is_authenticated or not auth_context.user:
            raise HTTPException(status_code=401, detail="Invalid session token")

        user = auth_context.user

        if data.method == "email_otp":
            otp_store = _get_otp_store()
            if not otp_store:
                raise HTTPException(status_code=500, detail="OTP store not configured")

            code = otp_store.create_otp(user.id, method="email_otp")

            # Log the code (actual email delivery depends on channel integration)
            import logging

            log = logging.getLogger("dazzle.auth.2fa")
            log.info("2FA OTP code for %s: %s", user.email, code)

            return {"message": "OTP code sent to your email"}

        return {"message": "Enter your authenticator code"}

    # =========================================================================
    # 2FA Verify (during login)
    # =========================================================================

    @router.post("/verify")
    async def verify_2fa(data: TwoFactorVerifyRequest, request: FastAPIRequest) -> JSONResponse:
        """Verify 2FA code and complete login.

        Accepts TOTP codes, email OTP codes, or recovery codes.
        """
        # Validate the pending session
        auth_context = auth_store.validate_session(data.session_token)
        if not auth_context.is_authenticated or not auth_context.user:
            raise HTTPException(status_code=401, detail="Invalid session token")

        user = auth_context.user
        verified = False

        if data.method == "totp":
            from dazzle_back.runtime.totp import verify_totp

            secret = auth_store.get_totp_secret(user.id)
            if secret:
                verified = verify_totp(secret, data.code)

        elif data.method == "email_otp":
            otp_store = _get_otp_store()
            if otp_store:
                verified = otp_store.verify_otp(user.id, data.code, method="email_otp")

        elif data.method == "recovery":
            recovery_store = _get_recovery_store()
            if recovery_store:
                verified = recovery_store.verify_code(user.id, data.code)

        if not verified:
            raise HTTPException(status_code=401, detail="Invalid 2FA code")

        # Delete the pending session
        auth_store.delete_session(data.session_token)

        # Create a full session
        session = auth_store.create_session(
            user,
            expires_in=timedelta(days=session_expires_days),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        response = JSONResponse(
            content={
                "user": {
                    "id": str(user.id),
                    "email": user.email,
                    "username": user.username,
                    "roles": user.roles,
                },
                "message": "2FA verification successful",
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
    # Recovery codes
    # =========================================================================

    @router.post("/recovery")
    async def use_recovery_code(
        data: TwoFactorVerifyRequest, request: FastAPIRequest
    ) -> JSONResponse:
        """Use a recovery code to complete 2FA login."""
        data.method = "recovery"
        return await verify_2fa(data, request)

    @router.post("/recovery/regenerate")
    async def regenerate_recovery_codes(request: FastAPIRequest) -> dict[str, Any]:
        """Generate new recovery codes (invalidates old ones)."""
        from dazzle_back.runtime.recovery_codes import generate_recovery_codes

        user = _get_current_user(request)
        recovery_store = _get_recovery_store()
        if not recovery_store:
            raise HTTPException(status_code=500, detail="Recovery store not configured")

        codes = generate_recovery_codes()
        recovery_store.store_codes(user.id, codes)
        auth_store.set_recovery_codes_generated(user.id, True)

        return {"recovery_codes": codes, "count": len(codes)}

    # =========================================================================
    # 2FA Status & Disable
    # =========================================================================

    @router.get("/status")
    async def get_2fa_status(request: FastAPIRequest) -> dict[str, Any]:
        """Get current 2FA status for the authenticated user."""
        user = _get_current_user(request)

        result: dict[str, Any] = {
            "two_factor_enabled": user.two_factor_enabled,
            "totp_enabled": user.totp_enabled,
            "email_otp_enabled": user.email_otp_enabled,
            "recovery_codes_generated": user.recovery_codes_generated,
        }

        recovery_store = _get_recovery_store()
        if recovery_store and user.recovery_codes_generated:
            result["recovery_codes_remaining"] = recovery_store.remaining_count(user.id)

        return result

    @router.delete("/totp")
    async def disable_totp(request: FastAPIRequest) -> dict[str, str]:
        """Disable TOTP for the current user."""
        user = _get_current_user(request)
        if not user.totp_enabled:
            raise HTTPException(status_code=400, detail="TOTP is not enabled")
        auth_store.disable_totp(user.id)
        return {"message": "TOTP disabled"}

    @router.delete("/email-otp")
    async def disable_email_otp(request: FastAPIRequest) -> dict[str, str]:
        """Disable email OTP for the current user."""
        user = _get_current_user(request)
        if not user.email_otp_enabled:
            raise HTTPException(status_code=400, detail="Email OTP is not enabled")
        auth_store.disable_email_otp(user.id)
        return {"message": "Email OTP disabled"}

    return router
