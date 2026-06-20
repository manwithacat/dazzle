"""Form-encoded password-reset endpoints (Phase 1.B.2, v0.67.31).

Pairs with the typed-Fragment views in `auth_views.py`:
`build_forgot_password_view` posts to `/auth/forgot-password/submit`;
`build_reset_password_view` posts to `/auth/reset-password/submit`.

The legacy `/auth/forgot-password` and `/auth/reset-password` endpoints
(in `routes.py`) accept JSON and return JSON — they remain mounted for
API callers. These new endpoints accept `application/x-www-form-urlencoded`
and return HTML redirects, matching the typed-Fragment retirement plan's
"native form submission, server-side redirect" shape.

Both endpoints route password-reset notifications through the existing
`MagicLinkMailer` protocol — re-used because the contract (one-shot
link-by-email) is identical. The mailer call is logged at INFO when the
default `LogMailer` is wired (development pickup).
"""

import logging
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from dazzle.http.runtime.auth.mailer import get_mailer

_logger = logging.getLogger(__name__)


def _build_reset_link_url(*, request: Request, token: str) -> str:
    """Compose the absolute reset-link URL for ``token``."""
    base = str(request.base_url).rstrip("/")
    return f"{base}/reset-password?token={token}"


def create_password_reset_routes() -> APIRouter:
    """Form-encoded password-reset endpoints used by typed-Fragment views."""
    router = APIRouter(tags=["auth"])

    @router.post("/auth/forgot-password/submit")
    async def submit_forgot_password(
        request: Request,
        email: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        """Issue a password-reset token for the supplied email.

        Account-enumeration safe: ALWAYS redirects to
        `/forgot-password/sent` regardless of whether the email
        matched a real user. When the email matches, a reset token
        is created and a notification dispatched via the
        `MagicLinkMailer` protocol (the same Protocol used for
        passwordless login — see `mailer.py`).
        """
        auth_store = request.app.state.auth_store
        mailer = get_mailer(request.app.state)
        normalized_email = email.strip().lower()
        if normalized_email:
            user = auth_store.get_user_by_email(normalized_email)
            if user is not None and getattr(user, "is_active", True):
                token = auth_store.create_password_reset_token(user.id)
                link_url = _build_reset_link_url(request=request, token=token)
                mailer.send_magic_link(to_email=normalized_email, link_url=link_url)
            else:
                _logger.info(  # nosemgrep
                    "Reset request for unknown/inactive email %s — "  # nosemgrep
                    "no token issued (account-enumeration guard)",
                    normalized_email,
                )
        return RedirectResponse(url="/forgot-password/sent", status_code=303)

    @router.post("/auth/reset-password/submit")
    async def submit_reset_password(
        request: Request,
        token: Annotated[str, Form()] = "",
        new_password: Annotated[str, Form()] = "",
        confirm_password: Annotated[str, Form()] = "",
    ) -> RedirectResponse:
        """Consume a reset token and update the user's password.

        Validates that ``new_password`` matches ``confirm_password``
        BEFORE touching the auth store — a mismatch redirects back
        to `/reset-password?token=<token>&error=mismatch`. An
        invalid / expired token redirects to `/reset-password?error=invalid`.
        On success, the token is consumed, existing sessions are
        cleared, and the user lands on `/reset-password/done`.
        """
        if not new_password or new_password != confirm_password:
            target = "/reset-password?error=mismatch"
            if token:
                # URL-encode the token so a crafted value can't break out
                # of the query string. The path itself is hardcoded
                # same-origin, so this stays an internal redirect.
                target = f"/reset-password?token={quote(token, safe='')}&error=mismatch"
            return RedirectResponse(url=target, status_code=303)

        auth_store = request.app.state.auth_store
        user = auth_store.validate_password_reset_token(token)
        if user is None:
            return RedirectResponse(
                url="/reset-password?error=invalid",
                status_code=303,
            )

        auth_store.update_password(user.id, new_password)
        auth_store.consume_password_reset_token(token)
        auth_store.delete_user_sessions(user.id)
        return RedirectResponse(url="/reset-password/done", status_code=303)

    return router
