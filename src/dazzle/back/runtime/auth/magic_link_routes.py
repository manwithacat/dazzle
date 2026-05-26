"""HTTP routes for magic link authentication.

Exposes the production-safe consumer endpoint GET /auth/magic/{token}.
The token validation primitives live in magic_link.py — this module
only wires them to HTTP.

This endpoint is mounted unconditionally and is suitable for:
- Email-based passwordless login
- Account recovery flows
- Dev QA mode (#768)
"""

import logging
from typing import Annotated
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import RedirectResponse

from dazzle.back.runtime.auth.magic_link import (
    create_magic_link,
    validate_magic_link,
)
from dazzle.back.runtime.auth.mailer import get_mailer

_logger = logging.getLogger(__name__)


def _build_magic_link_url(*, request: Request, token: str, next_path: str) -> str:
    """Compose the absolute consumer URL for a magic-link token.

    Format: `<base_url>/auth/magic/<token>[?next=<next_path>]`.
    Used by both the login + signup issuance paths so the URL
    shape stays consistent."""
    base = str(request.base_url).rstrip("/")
    # CodeQL alert #132 / py/url-redirection: encode `next_path` so a value
    # like `/foo&inject=1` doesn't introduce an extra query parameter at
    # the consumer-side URL. The guard `_is_safe_redirect_path` ensures
    # the path itself is same-origin, but `&` in the path passes the
    # guard and would otherwise be interpolated raw.
    next_param = f"?next={quote(next_path, safe='/')}" if next_path and next_path != "/" else ""
    return f"{base}/auth/magic/{token}{next_param}"


def _is_safe_redirect_path(value: str) -> bool:
    """Return True if ``value`` is safe to use as a same-origin redirect target.

    Uses ``urllib.parse.urlparse`` to catch bypasses that string-prefix
    checks miss — specifically backslash escaping (``/\\@evil.com``,
    which modern browsers may normalize per the WHATWG URL spec to a
    protocol-relative URL pointing at ``evil.com``).

    A safe value must:

    1. Contain no backslash. Browsers normalize ``\\`` to ``/`` in URL
       parsing in some contexts, which can turn an apparently-local path
       into a protocol-relative URL. Reject explicitly.
    2. Have no ``scheme`` (``http://``, ``https://``, ``javascript:``,
       ``data:``, etc.) — would escape the origin entirely.
    3. Have no ``netloc`` (authority / host). This catches both
       ``//evil.com`` (protocol-relative) and any malformed URL whose
       authority parses out of the input.
    4. Have a ``path`` that begins with ``/`` (absolute within-origin
       path), excluding the empty string.

    Closes CodeQL alert ``py/url-redirection`` at this call site.
    """
    if "\\" in value:
        return False
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        return False
    return parsed.path.startswith("/")


def create_magic_link_routes() -> APIRouter:
    """Create the magic link consumer router.

    Routes are registered under /auth/* to keep auth-related endpoints
    grouped. The caller is responsible for including this router on the
    FastAPI app.
    """
    router = APIRouter(tags=["auth"])

    @router.get("/auth/magic/{token}")
    async def consume_magic_link(
        token: str,
        request: Request,
        next: Annotated[str, Query()] = "/",
    ) -> RedirectResponse:
        """Validate a magic link token and create a session.

        One-time use, expiry-gated. On success: creates session, sets
        the dazzle_session cookie, and redirects to ?next=... (if
        same-origin) or /. On failure: redirects to /auth/login with an
        error query param.

        The ``next`` parameter is validated via ``_is_safe_redirect_path``
        (urllib.parse-based), which rejects: backslash-containing paths,
        paths with a scheme (http://, javascript:, data:, etc.), paths
        with a netloc (//evil.com protocol-relative), and anything that
        doesn't begin with "/". Unsafe values fall back to "/".
        """
        auth_store = request.app.state.auth_store
        user_id = validate_magic_link(auth_store, token)
        if user_id is None:
            return RedirectResponse(
                url="/auth/login?error=invalid_magic_link",
                status_code=303,
            )

        user = auth_store.get_user_by_id(user_id)
        if user is None:
            # Token was valid but the user no longer exists.
            return RedirectResponse(
                url="/auth/login?error=invalid_magic_link",
                status_code=303,
            )

        # Create session (same code path as password login).
        # Session-fixation defence (#1198): regenerate the session id on
        # magic-link consumption — invalidate any pre-auth session cookie
        # the client presented so an attacker-planted id can't survive into
        # the authenticated state.
        pre_auth_sid = request.cookies.get("dazzle_session")
        session = auth_store.create_session(user)
        if pre_auth_sid and pre_auth_sid != session.id:
            auth_store.delete_session(pre_auth_sid)

        # Honour ?next= only when it is a same-origin path.
        redirect_to = next if _is_safe_redirect_path(next) else "/"

        response = RedirectResponse(url=redirect_to, status_code=303)
        response.set_cookie(
            key="dazzle_session",
            value=session.id,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
        )
        return response

    @router.post("/auth/login/magic-link")
    async def issue_magic_link(
        request: Request,
        email: Annotated[str, Form()] = "",
        next: Annotated[str, Query()] = "/",
    ) -> RedirectResponse:
        """Issue a magic-link login token for the supplied email.

        Phase 1.A (v0.67.29) of the Jinja2 retirement plan:
        consolidates the email-link passwordless login as the v1
        default. Endpoint contract:

        1. Look up the user by email. If not found, **still return
           the same response** as the success path — defensive
           against account enumeration. The user gets the "check
           your inbox" page either way; the absence of a real
           inbox just means no link is ever delivered.
        2. When the user exists, create a magic-link token via
           `magic_link.create_magic_link` and emit it to the
           application log at INFO level (real email delivery is
           a follow-on ship — see the Jinja2 retirement plan
           Phase 1.B notes on email integration).
        3. Redirect to `/login/sent` with status 303. The `next`
           query param is preserved through the redirect so the
           consumed magic-link lands the user on the originally-
           requested page.

        SECURITY: this endpoint is unauthenticated and rate-
        limit-able. Production deployments should add a per-IP
        rate limit at the reverse-proxy layer (n requests / min)
        to prevent enumeration via timing or volume.
        """
        auth_store = request.app.state.auth_store
        mailer = get_mailer(request.app.state)
        normalized_email = email.strip().lower()
        if normalized_email:
            user = auth_store.get_user_by_email(normalized_email)
            if user is not None:
                token = create_magic_link(
                    auth_store,
                    user_id=user.id,
                    ttl_seconds=900,  # 15 minutes
                    created_by="login_form",
                )
                link_url = _build_magic_link_url(request=request, token=token, next_path=next)
                mailer.send_magic_link(to_email=normalized_email, link_url=link_url)
            else:
                _logger.info(
                    "Magic-link request for unknown email %s — "
                    "no link issued (account-enumeration guard)",
                    normalized_email,
                )
        # Same response regardless of whether email matched a user
        # — defensive against account enumeration.
        sent_url = "/login/sent"
        if next and _is_safe_redirect_path(next) and next != "/":
            # CodeQL alert #132: encode `next` so `&` in the value cannot inject extra params.
            sent_url = f"/login/sent?next={quote(next, safe='/')}"
        return RedirectResponse(url=sent_url, status_code=303)

    @router.post("/auth/signup/magic-link")
    async def signup_with_magic_link(
        request: Request,
        email: Annotated[str, Form()] = "",
        name: Annotated[str, Form()] = "",
        next: Annotated[str, Query()] = "/",
    ) -> RedirectResponse:
        """Issue a magic-link for signup (#1037 Phase 1.B, v0.67.30).

        Behaviour:
        1. Look up user by email.
        2. If user exists: silently issue a sign-in link (treat as
           a login attempt — the user already has an account).
           This is the friendly UX: signup form doesn't need to
           know whether the email is new or returning.
        3. If user doesn't exist AND email is well-formed: create
           a passwordless user record (random unguessable hash —
           the user can opt into a password later via account
           settings) and issue a magic link.
        4. Empty / malformed email: log + redirect to /login/sent
           anyway (account-enumeration guard parity with login).

        SECURITY: same rate-limit considerations as the login
        endpoint apply. The create-or-login branch means a
        determined attacker could observe whether an email was
        registered by timing the response — a real production
        deployment should add timing equalisation if that's a
        concern.
        """
        auth_store = request.app.state.auth_store
        mailer = get_mailer(request.app.state)
        normalized_email = email.strip().lower()
        normalized_name = name.strip()

        if normalized_email and "@" in normalized_email:
            user = auth_store.get_user_by_email(normalized_email)
            if user is None:
                # Create passwordless user. Random password fills
                # the column; the user can set a real password
                # later via account settings if they want password-
                # mode login enabled.
                import secrets

                random_password = secrets.token_urlsafe(48)
                try:
                    user = auth_store.create_user(
                        email=normalized_email,
                        password=random_password,
                        username=normalized_name or None,
                    )
                except Exception as exc:  # noqa: BLE001 — surface in logs
                    _logger.warning(
                        "Signup magic-link: create_user failed for %s: %s",
                        normalized_email,
                        exc,
                    )
                    user = None
            if user is not None:
                token = create_magic_link(
                    auth_store,
                    user_id=user.id,
                    ttl_seconds=900,
                    created_by="signup_form",
                )
                link_url = _build_magic_link_url(request=request, token=token, next_path=next)
                mailer.send_magic_link(to_email=normalized_email, link_url=link_url)
        else:
            _logger.info(
                "Signup magic-link: malformed/empty email %r — "
                "no user created (account-enumeration guard)",
                normalized_email,
            )

        sent_url = "/login/sent"
        if next and _is_safe_redirect_path(next) and next != "/":
            # CodeQL alert #132: encode `next` so `&` in the value cannot inject extra params.
            sent_url = f"/login/sent?next={quote(next, safe='/')}"
        return RedirectResponse(url=sent_url, status_code=303)

    return router
