"""Two-factor authentication routes."""

from dataclasses import dataclass, field
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

from .crypto import cookie_secure
from .events import emit_user_logged_in
from .models import TwoFactorSetupRequest, TwoFactorVerifyRequest, UserRecord
from .store import AuthStore

# =============================================================================
# Dependencies Container
# =============================================================================


@dataclass
class _TwoFaDeps:
    auth_store: AuthStore
    cookie_name: str
    session_expires_days: int
    database_url: str | None
    stores: dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Helpers
# =============================================================================


def _get_otp_store(deps: _TwoFaDeps) -> Any:
    if "otp" not in deps.stores and deps.database_url:
        from dazzle_back.runtime.otp_store import OTPStore

        store = OTPStore(deps.database_url)
        store.init_db()
        deps.stores["otp"] = store
    return deps.stores.get("otp")


def _get_recovery_store(deps: _TwoFaDeps) -> Any:
    if "recovery" not in deps.stores and deps.database_url:
        from dazzle_back.runtime.recovery_codes import RecoveryCodeStore

        store = RecoveryCodeStore(deps.database_url)
        store.init_db()
        deps.stores["recovery"] = store
    return deps.stores.get("recovery")


def _get_current_user(deps: _TwoFaDeps, request: FastAPIRequest) -> UserRecord:
    """Get authenticated user from session cookie."""
    from fastapi import HTTPException

    session_id = request.cookies.get(deps.cookie_name)
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    auth_context = deps.auth_store.validate_session(session_id)
    if not auth_context.is_authenticated or not auth_context.user:
        raise HTTPException(status_code=401, detail="Session expired")
    return auth_context.user


# =============================================================================
# Module-level handler functions
# =============================================================================


async def _setup_totp(deps: _TwoFaDeps, request: FastAPIRequest) -> dict[str, str]:
    """Start TOTP setup — returns secret and QR code URI."""
    from fastapi import HTTPException

    from dazzle_back.runtime.totp import generate_totp_secret, get_totp_uri

    user = _get_current_user(deps, request)

    if user.totp_enabled:
        raise HTTPException(status_code=400, detail="TOTP is already enabled")

    secret = generate_totp_secret()
    uri = get_totp_uri(secret, user.email)

    # Temporarily store the secret without enabling TOTP — it will be enabled
    # after the user verifies their first code in _verify_totp_setup.
    deps.auth_store.store_totp_secret_pending(user.id, secret)

    return {"secret": secret, "uri": uri}


async def _verify_totp_setup(
    deps: _TwoFaDeps, data: TwoFactorSetupRequest, request: FastAPIRequest
) -> dict[str, Any]:
    """Verify TOTP code to complete setup."""
    from fastapi import HTTPException

    from dazzle_back.runtime.totp import verify_totp

    user = _get_current_user(deps, request)
    secret = deps.auth_store.get_totp_secret(user.id)

    if not secret:
        raise HTTPException(status_code=400, detail="TOTP setup not started")

    if not verify_totp(secret, data.code):
        raise HTTPException(status_code=400, detail="Invalid TOTP code")

    # Enable TOTP
    deps.auth_store.enable_totp(user.id, secret)

    # Generate recovery codes if not already generated
    recovery_codes = None
    recovery_store = _get_recovery_store(deps)
    if recovery_store and not user.recovery_codes_generated:
        from dazzle_back.runtime.recovery_codes import generate_recovery_codes

        codes = generate_recovery_codes()
        recovery_store.store_codes(user.id, codes)
        deps.auth_store.set_recovery_codes_generated(user.id, True)
        recovery_codes = codes

    result: dict[str, Any] = {"message": "TOTP enabled successfully"}
    if recovery_codes:
        result["recovery_codes"] = recovery_codes
    return result


async def _setup_email_otp(deps: _TwoFaDeps, request: FastAPIRequest) -> dict[str, str]:
    """Enable email OTP method."""
    user = _get_current_user(deps, request)
    deps.auth_store.enable_email_otp(user.id)

    # Generate recovery codes if not already generated
    recovery_store = _get_recovery_store(deps)
    if recovery_store and not user.recovery_codes_generated:
        from dazzle_back.runtime.recovery_codes import generate_recovery_codes

        codes = generate_recovery_codes()
        recovery_store.store_codes(user.id, codes)
        deps.auth_store.set_recovery_codes_generated(user.id, True)

    return {"message": "Email OTP enabled"}


async def _challenge_2fa(deps: _TwoFaDeps, data: TwoFactorVerifyRequest) -> dict[str, str]:
    """Send 2FA challenge (email OTP) during login.

    The session_token comes from the login response when 2FA is required.
    """
    from fastapi import HTTPException

    # Validate the pending session
    auth_context = deps.auth_store.validate_session(data.session_token)
    if not auth_context.is_authenticated or not auth_context.user:
        raise HTTPException(status_code=401, detail="Invalid session token")

    user = auth_context.user

    if data.method == "email_otp":
        otp_store = _get_otp_store(deps)
        if not otp_store:
            raise HTTPException(status_code=500, detail="OTP store not configured")

        code = otp_store.create_otp(user.id, method="email_otp")

        # Log the code (actual email delivery depends on channel integration)
        import logging

        log = logging.getLogger("dazzle.auth.2fa")
        log.info("2FA OTP code for %s: %s", user.email, code)

        return {"message": "OTP code sent to your email"}

    return {"message": "Enter your authenticator code"}


async def _verify_2fa(
    deps: _TwoFaDeps, data: TwoFactorVerifyRequest, request: FastAPIRequest
) -> Response:
    """Verify 2FA code and complete login.

    Accepts TOTP codes, email OTP codes, or recovery codes.
    """
    from fastapi import HTTPException

    # Validate the pending session
    auth_context = deps.auth_store.validate_session(data.session_token)
    if not auth_context.is_authenticated or not auth_context.user:
        raise HTTPException(status_code=401, detail="Invalid session token")

    user = auth_context.user
    verified = False

    if data.method == "totp":
        from dazzle_back.runtime.totp import verify_totp

        secret = deps.auth_store.get_totp_secret(user.id)
        if secret:
            verified = verify_totp(secret, data.code)

    elif data.method == "email_otp":
        otp_store = _get_otp_store(deps)
        if otp_store:
            verified = otp_store.verify_otp(user.id, data.code, method="email_otp")

    elif data.method == "recovery":
        recovery_store = _get_recovery_store(deps)
        if recovery_store:
            verified = recovery_store.verify_code(user.id, data.code)

    if not verified:
        raise HTTPException(status_code=401, detail="Invalid 2FA code")

    # Delete the pending session
    deps.auth_store.delete_session(data.session_token)

    # Create a full session
    session = deps.auth_store.create_session(
        user,
        expires_in=timedelta(days=deps.session_expires_days),
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
        key=deps.cookie_name,
        value=session.id,
        httponly=True,
        secure=cookie_secure(request),
        samesite="lax",
        max_age=deps.session_expires_days * 24 * 60 * 60,
    )

    await emit_user_logged_in(user, session_id=session.id, method="2fa")

    return response


async def _use_recovery_code(
    deps: _TwoFaDeps, data: TwoFactorVerifyRequest, request: FastAPIRequest
) -> Response:
    """Use a recovery code to complete 2FA login."""
    data.method = "recovery"
    return await _verify_2fa(deps, data, request)


async def _regenerate_recovery_codes(deps: _TwoFaDeps, request: FastAPIRequest) -> dict[str, Any]:
    """Generate new recovery codes (invalidates old ones)."""
    from fastapi import HTTPException

    from dazzle_back.runtime.recovery_codes import generate_recovery_codes

    user = _get_current_user(deps, request)
    recovery_store = _get_recovery_store(deps)
    if not recovery_store:
        raise HTTPException(status_code=500, detail="Recovery store not configured")

    codes = generate_recovery_codes()
    recovery_store.store_codes(user.id, codes)
    deps.auth_store.set_recovery_codes_generated(user.id, True)

    return {"recovery_codes": codes, "count": len(codes)}


async def _get_2fa_status(deps: _TwoFaDeps, request: FastAPIRequest) -> dict[str, Any]:
    """Get current 2FA status for the authenticated user."""
    user = _get_current_user(deps, request)

    result: dict[str, Any] = {
        "two_factor_enabled": user.two_factor_enabled,
        "totp_enabled": user.totp_enabled,
        "email_otp_enabled": user.email_otp_enabled,
        "recovery_codes_generated": user.recovery_codes_generated,
    }

    recovery_store = _get_recovery_store(deps)
    if recovery_store and user.recovery_codes_generated:
        result["recovery_codes_remaining"] = recovery_store.remaining_count(user.id)

    return result


async def _disable_totp(deps: _TwoFaDeps, request: FastAPIRequest) -> dict[str, str]:
    """Disable TOTP for the current user."""
    from fastapi import HTTPException

    user = _get_current_user(deps, request)
    if not user.totp_enabled:
        raise HTTPException(status_code=400, detail="TOTP is not enabled")
    deps.auth_store.disable_totp(user.id)
    return {"message": "TOTP disabled"}


async def _disable_email_otp(deps: _TwoFaDeps, request: FastAPIRequest) -> dict[str, str]:
    """Disable email OTP for the current user."""
    from fastapi import HTTPException

    user = _get_current_user(deps, request)
    if not user.email_otp_enabled:
        raise HTTPException(status_code=400, detail="Email OTP is not enabled")
    deps.auth_store.disable_email_otp(user.id)
    return {"message": "Email OTP disabled"}


# =============================================================================
# Factory
# =============================================================================


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

    import dazzle_back.runtime.rate_limit as _rl

    router = APIRouter(prefix="/auth/2fa", tags=["Two-Factor Authentication"])

    deps = _TwoFaDeps(
        auth_store=auth_store,
        cookie_name=cookie_name,
        session_expires_days=session_expires_days,
        database_url=database_url,
    )

    # TOTP Setup
    router.post("/setup/totp")(partial(_setup_totp, deps))
    router.post("/verify/totp")(partial(_verify_totp_setup, deps))

    # Email OTP Setup
    router.post("/setup/email-otp")(partial(_setup_email_otp, deps))

    # 2FA Challenge
    router.post("/challenge")(partial(_challenge_2fa, deps))

    # 2FA Verify
    verify_handler = partial(_verify_2fa, deps)
    verify_handler = _rl.limiter.limit(_rl.twofa_limit)(verify_handler)  # type: ignore[misc,untyped-decorator,unused-ignore]
    router.post("/verify", include_in_schema=False)(verify_handler)

    # Recovery codes
    router.post("/recovery", include_in_schema=False)(partial(_use_recovery_code, deps))
    router.post("/recovery/regenerate")(partial(_regenerate_recovery_codes, deps))

    # 2FA Status & Disable
    router.get("/status")(partial(_get_2fa_status, deps))
    router.delete("/totp")(partial(_disable_totp, deps))
    router.delete("/email-otp")(partial(_disable_email_otp, deps))

    return router
