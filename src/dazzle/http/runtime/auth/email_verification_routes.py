"""HTTP routes for email verification (#1109).

Three endpoints siblings to magic-link signup. Mounted under ``/auth/``:

- ``GET /auth/verify-email?token=…`` — validate a token, flip
  ``users.email_verified=true``, redirect with a success/error flag.
- ``POST /auth/resend-verification`` — rate-limited form post that
  issues another token + emails it. Same account-enumeration guard as
  the magic-link login path (same response whether or not the email
  matches).
- ``POST /auth/send-verification`` — same shape as resend but used as
  the first send (typically from the password-signup happy path). The
  difference is purely semantic; the implementation is identical.

The token primitive lives in :mod:`email_verification` so the
operational contract (DB-backed, single-use, TTL-gated) stays
consistent with magic-link tokens.
"""

import logging
import time
from typing import Annotated

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import RedirectResponse

from dazzle.http.runtime.auth.email_verification import (
    DEFAULT_TOKEN_TTL_HOURS,
    create_email_verification_token,
    validate_email_verification_token,
)
from dazzle.http.runtime.auth.events import emit_user_email_verified
from dazzle.http.runtime.auth.mailer import get_verification_mailer
from dazzle.http.runtime.auth.redirect_safety import (
    is_safe_redirect_path as _is_safe_redirect_path,
)

_logger = logging.getLogger(__name__)

_DEFAULT_RESEND_INTERVAL_S = 60.0


def _build_verify_url(*, request: Request, token: str, next_path: str) -> str:
    """Compose the absolute consumer URL for an email-verification token."""
    base = str(request.base_url).rstrip("/")
    next_param = f"&next={next_path}" if next_path and next_path != "/" else ""
    return f"{base}/auth/verify-email?token={token}{next_param}"


def create_email_verification_routes(
    *,
    token_ttl_hours: int = DEFAULT_TOKEN_TTL_HOURS,
    resend_rate_limit_seconds: float = _DEFAULT_RESEND_INTERVAL_S,
) -> APIRouter:
    """Build the email-verification router.

    Args:
        token_ttl_hours: Token validity window. 24h by default — long
            enough for the email to clear spam, short enough that a
            leaked token doesn't sit live for weeks.
        resend_rate_limit_seconds: Minimum interval between two
            ``/auth/resend-verification`` calls for the same email,
            tracked in-process. Production deployments fronted by a
            reverse proxy should ALSO apply a per-IP rate limit at
            that layer.
    """
    router = APIRouter(tags=["auth"])

    # In-process resend throttle: maps lowercase email → last-issued
    # monotonic timestamp. Cleared at process restart, which is the
    # correct semantics for a soft rate limit — if a determined attacker
    # restarts the server they have bigger problems than verification
    # email spam.
    last_resend_at: dict[str, float] = {}

    @router.get("/auth/verify-email")
    async def consume_verification_token(
        request: Request,
        token: Annotated[str, Query()] = "",
        next: Annotated[str, Query()] = "/",
    ) -> RedirectResponse:
        """Validate ``token`` and flip ``email_verified=true``.

        Redirects to ``?next=…`` (when same-origin) or ``/`` on success
        with a ``?verified=ok`` query flag, or to ``/auth/login`` with
        ``?verified=error`` on failure. The redirect-with-flag pattern
        lets the consuming page surface a banner without needing a
        Flash-message machinery.
        """
        if not token:
            return RedirectResponse(
                url="/auth/login?verified=error&reason=missing_token",
                status_code=303,
            )

        auth_store = request.app.state.auth_store
        user_id = validate_email_verification_token(auth_store, token)
        if user_id is None:
            return RedirectResponse(
                url="/auth/login?verified=error&reason=invalid_or_expired",
                status_code=303,
            )

        # Emit downstream event (welcome mail, feature gates, etc.).
        user = auth_store.get_user_by_id(user_id)
        if user is not None:
            try:
                await emit_user_email_verified(user_id, email=user.email)
            except Exception:
                # Never block on event-bus failures — fire-and-forget.
                _logger.warning(
                    "Failed to emit email_verified event for user %s",
                    user_id,
                    exc_info=True,
                )

        redirect_to = next if _is_safe_redirect_path(next) else "/"
        sep = "&" if "?" in redirect_to else "?"
        return RedirectResponse(url=f"{redirect_to}{sep}verified=ok", status_code=303)

    def _issue_verification_for(email: str, request: Request, next_path: str) -> None:
        """Look up the user and (if found + unverified) issue a token + mail.

        Quietly swallows the not-found case to maintain account-
        enumeration guard parity with the magic-link login path.
        """
        auth_store = request.app.state.auth_store
        mailer = get_verification_mailer(request.app.state)
        normalized_email = email.strip().lower()
        if not normalized_email:
            return

        user = auth_store.get_user_by_email(normalized_email)
        if user is None:
            _logger.info(
                "Verification mail requested for unknown email %s — "
                "no token issued (account-enumeration guard)",
                normalized_email,
            )
            return
        if user.email_verified:
            _logger.info(
                "Verification mail requested for already-verified email %s — skipping resend",
                normalized_email,
            )
            return

        token = create_email_verification_token(
            auth_store,
            user_id=str(user.id),
            ttl_hours=token_ttl_hours,
            created_by="email_verification_route",
        )
        verify_url = _build_verify_url(request=request, token=token, next_path=next_path)
        mailer.send_verification_email(to_email=normalized_email, verify_url=verify_url)

    def _resend_allowed(email_lower: str) -> bool:
        """Apply the per-email rate limit window. Returns True iff the
        request should proceed and updates the bookkeeping timestamp."""
        now = time.monotonic()
        prev = last_resend_at.get(email_lower)
        if prev is not None and (now - prev) < resend_rate_limit_seconds:
            return False
        last_resend_at[email_lower] = now
        return True

    @router.post("/auth/resend-verification")
    async def resend_verification(
        request: Request,
        email: Annotated[str, Form()] = "",
        next: Annotated[str, Query()] = "/",
    ) -> RedirectResponse:
        """Re-issue a verification token + mail.

        Rate-limited (in-process) to one request per
        ``resend_rate_limit_seconds`` per email. Production deployments
        should also apply a per-IP limit at the reverse-proxy layer.
        """
        normalized_email = email.strip().lower()
        if normalized_email and _resend_allowed(normalized_email):
            _issue_verification_for(normalized_email, request, next)
        sent_url = "/verification/sent"
        if next and _is_safe_redirect_path(next) and next != "/":
            sent_url = f"/verification/sent?next={next}"
        return RedirectResponse(url=sent_url, status_code=303)

    @router.post("/auth/send-verification")
    async def send_verification(
        request: Request,
        email: Annotated[str, Form()] = "",
        next: Annotated[str, Query()] = "/",
    ) -> RedirectResponse:
        """Initial verification-mail issuance.

        Semantically the "first send" of a verification flow — typically
        invoked from the password-signup happy path. Skips the resend
        rate limit because the throttle is for repeats only; the
        account-enumeration guard still applies.
        """
        _issue_verification_for(email, request, next)
        sent_url = "/verification/sent"
        if next and _is_safe_redirect_path(next) and next != "/":
            sent_url = f"/verification/sent?next={next}"
        return RedirectResponse(url=sent_url, status_code=303)

    return router
