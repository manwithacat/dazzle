"""Form-encoded 2FA submission endpoints (Phase 1.D.1, v0.67.35).

Pairs with the typed 2FA challenge view in `two_factor_views.py`.
The legacy JSON `POST /auth/2fa/verify` endpoint (in `routes_2fa.py`)
remains mounted for programmatic API callers; these new endpoints
accept `application/x-www-form-urlencoded` and return HTML redirects
so the typed forms work without JS.

Two endpoints:
  - `POST /auth/2fa/verify/submit` — verifies a TOTP / email-OTP /
    recovery code, sets the session cookie on success, 303s to /app
    (or `?next=` when safe). Failure 303s back to /2fa/challenge with
    `?error=invalid_code` and the user's chosen `method` preserved.
  - `POST /auth/2fa/email-otp-send/submit` — triggers an email-OTP
    delivery for the pending login session, 303s back to
    /2fa/challenge with `?mode=email_otp&sent=1`.
"""

import logging
from datetime import timedelta
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import RedirectResponse, Response

from dazzle.back.runtime.auth.crypto import cookie_secure
from dazzle.back.runtime.auth.forbidden_org import forbidden_org_response
from dazzle.back.runtime.auth.org_activation import (
    FORBIDDEN_SENTINEL,
    _login_redirect_for_outcome,
    activate_session_for_login,
    memberships_required,
)
from dazzle.back.runtime.auth.redirect_safety import (
    is_safe_redirect_path as _is_safe_redirect_path,
)

_logger = logging.getLogger(__name__)


def create_two_factor_form_routes(
    *,
    cookie_name: str = "dazzle_session",
    session_expires_days: int = 7,
) -> APIRouter:
    """Form-encoded 2FA endpoints used by the typed challenge view."""
    router = APIRouter(tags=["auth"])

    @router.post("/auth/2fa/verify/submit")
    async def submit_verify_2fa(
        request: Request,
        session_token: Annotated[str, Form()] = "",
        method: Annotated[str, Form()] = "totp",
        code: Annotated[str, Form()] = "",
        next: Annotated[str, Query()] = "/",
    ) -> Response:
        """Verify a 2FA code and complete login.

        Reuses the validation primitives backing the JSON endpoint
        (`routes_2fa._verify_2fa`) so TOTP / email-OTP / recovery
        codes are all accepted. The pending login session is
        consumed on success and a fresh full session is created
        with a 7-day default lifetime.
        """
        from dazzle.back.runtime.totp import verify_totp

        auth_store = request.app.state.auth_store
        # URL-encode the form-supplied values so a crafted token can't
        # break out of the query string. Path is hardcoded same-origin.
        challenge_back = (
            f"/2fa/challenge?session={quote(session_token, safe='')}"
            f"&method={quote(method, safe='')}"
        )

        if not session_token or not code:
            return RedirectResponse(url=f"{challenge_back}&error=invalid_code", status_code=303)

        auth_context = auth_store.validate_session(session_token)
        if not auth_context.is_authenticated or not auth_context.user:
            # Pending session expired — back to /login.
            return RedirectResponse(url="/login?error=invalid_credentials", status_code=303)

        user = auth_context.user
        verified = False

        if method == "totp":
            secret = auth_store.get_totp_secret(user.id)
            if secret:
                verified = verify_totp(secret, code)
        elif method == "email_otp":
            otp_store = getattr(auth_store, "otp_store", None)
            if otp_store is not None:
                verified = otp_store.verify_otp(user.id, code, method="email_otp")
        elif method == "recovery":
            recovery_store = getattr(auth_store, "recovery_store", None)
            if recovery_store is not None:
                verified = recovery_store.verify_code(user.id, code)

        if not verified:
            return RedirectResponse(url=f"{challenge_back}&error=invalid_code", status_code=303)

        auth_store.delete_session(session_token)
        # Session-fixation defence (#1198): regenerate the session id on
        # 2FA verification success — invalidate any pre-auth session cookie
        # the client presented (separate from the pending 2FA token deleted
        # above) so an attacker-planted id can't survive into the
        # authenticated state.
        pre_auth_sid = request.cookies.get(cookie_name)
        # Phase 2 (auth Plan 1b): the post-2FA session is the real authenticated
        # session — activate an org context for the proven identity.
        safe_next = next if next and next != "/" and _is_safe_redirect_path(next) else "/app"
        outcome = activate_session_for_login(auth_store, user, request)
        membership_id, redirect_to = _login_redirect_for_outcome(
            outcome, safe_next, memberships_required=memberships_required(request)
        )
        if redirect_to == FORBIDDEN_SENTINEL:
            return forbidden_org_response(request)  # #1393: branded host-pin 403
        session = auth_store.create_session(
            user,
            expires_in=timedelta(days=session_expires_days),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            active_membership_id=membership_id,
        )
        if pre_auth_sid and pre_auth_sid != session.id:
            auth_store.delete_session(pre_auth_sid)

        response = RedirectResponse(url=redirect_to, status_code=303)
        response.set_cookie(
            key=cookie_name,
            value=session.id,
            httponly=True,
            secure=cookie_secure(request),
            samesite="lax",
            max_age=session_expires_days * 24 * 60 * 60,
        )
        # Declarative-CSRF Phase 1: bind the CSRF token to the full session minted
        # on form-based 2FA-verification success. httponly=False so htmx/JS can
        # echo it into the X-CSRF-Token header. Cookies set on a 303 redirect are
        # honoured by the browser. See
        # docs/superpowers/specs/2026-06-03-declarative-csrf-design.md.
        response.set_cookie(
            key="dazzle_csrf",
            value=session.csrf_secret,
            httponly=False,
            secure=cookie_secure(request),
            samesite="lax",
            max_age=session_expires_days * 24 * 60 * 60,
        )
        return response

    @router.post("/auth/2fa/email-otp-send/submit")
    async def submit_email_otp_send(
        request: Request,
        session_token: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        """Trigger an email-OTP delivery for the pending login session.

        Account-enumeration not a concern here — the user has already
        passed primary auth and reached the 2FA challenge page. If the
        session token is invalid or the user has no email-OTP store
        configured, we silently 303 back to the challenge page with
        the same `?sent=1` indicator so the verify form renders.
        """
        auth_store = request.app.state.auth_store
        # URL-encode the form-supplied value so a crafted token can't
        # break out of the query string. Path is hardcoded same-origin.
        back = f"/2fa/challenge?session={quote(session_token, safe='')}&mode=email_otp&sent=1"

        if not session_token:
            return RedirectResponse(url="/login?error=invalid_credentials", status_code=303)

        auth_context = auth_store.validate_session(session_token)
        if auth_context.is_authenticated and auth_context.user:
            otp_store = getattr(auth_store, "otp_store", None)
            if otp_store is not None:
                try:
                    otp_store.send_otp(auth_context.user.id, method="email_otp")
                except Exception as exc:  # noqa: BLE001 — surface in logs
                    _logger.warning(
                        "Email-OTP send failed for user %s: %s",
                        auth_context.user.id,
                        exc,
                    )
        return RedirectResponse(url=back, status_code=303)

    return router
