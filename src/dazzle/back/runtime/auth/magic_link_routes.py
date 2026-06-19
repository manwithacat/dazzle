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
from urllib.parse import quote

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import RedirectResponse, Response

from dazzle.back.runtime.auth.cookie_name import read_session_id, select_write_name
from dazzle.back.runtime.auth.forbidden_org import forbidden_org_response
from dazzle.back.runtime.auth.magic_link import (
    create_magic_link,
    validate_magic_link,
)
from dazzle.back.runtime.auth.mailer import get_mailer
from dazzle.back.runtime.auth.org_activation import (
    FORBIDDEN_SENTINEL,
    _login_redirect_for_outcome,
    activate_session_for_login,
    memberships_required,
)
from dazzle.back.runtime.auth.redirect_safety import is_safe_redirect_path as _is_safe_redirect_path

_logger = logging.getLogger(__name__)


def _warn_if_misencoded_body(request: Request, email: str, where: str) -> None:
    """Surface the #1417 silent-failure: a non-form body whose form fields parse empty.

    The magic-link forms submit ``application/x-www-form-urlencoded`` (htmx 4 dropped
    ``json-enc``), so a JSON (or otherwise non-form) body makes ``Form()`` read empty and
    the handler silently takes the enumeration-guard branch (303, no mail). When the email
    parsed empty **and** the request carried a non-form body, log a WARNING — operationally
    distinct from a user genuinely submitting an empty field (which stays the quiet INFO
    enumeration guard). Detection-only: the request contract remains form-urlencoded.
    """
    if email.strip():
        return
    content_type = request.headers.get("content-type", "")
    is_form = "form-urlencoded" in content_type or "multipart/form-data" in content_type
    content_length = request.headers.get("content-length", "")
    has_body = (content_length not in ("", "0")) or (bool(content_type) and not is_form)
    if has_body and not is_form:
        _logger.warning(
            "%s received a non-form request body (content-type=%r) — the magic-link "
            "endpoints expect application/x-www-form-urlencoded, so the form fields parsed "
            "empty and no link was issued. Likely a JSON client; switch it to form encoding.",
            where,
            content_type or "<none>",
        )


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
    ) -> Response:
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
        pre_auth_sid = read_session_id(request)
        # Phase 2 (auth Plan 1b): activate an org context for the proven identity.
        # Honour ?next= only when it is a same-origin path.
        safe_next = next if _is_safe_redirect_path(next) else "/"
        outcome = activate_session_for_login(auth_store, user, request)
        membership_id, redirect_to = _login_redirect_for_outcome(
            outcome, safe_next, memberships_required=memberships_required(request)
        )
        if redirect_to == FORBIDDEN_SENTINEL:
            return forbidden_org_response(request)  # #1393: branded host-pin 403
        session = auth_store.create_session(user, active_membership_id=membership_id)
        if pre_auth_sid and pre_auth_sid != session.id:
            auth_store.delete_session(pre_auth_sid)

        response = RedirectResponse(url=redirect_to, status_code=303)
        response.set_cookie(
            key=select_write_name(request, user_roles=list(getattr(user, "roles", []) or [])),
            value=session.id,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
        )
        # Declarative-CSRF Phase 1: bind the CSRF token to the full session minted
        # on magic-link consumption. httponly=False so htmx/JS can echo it into the
        # X-CSRF-Token header. Mirrors the auth cookie's flags above (no max_age =
        # session cookie). See
        # docs/superpowers/specs/2026-06-03-declarative-csrf-design.md.
        response.set_cookie(
            key="dazzle_csrf",
            value=session.csrf_secret,
            httponly=False,
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
        else:
            _warn_if_misencoded_body(request, email, "Login magic-link")
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
            _warn_if_misencoded_body(request, email, "Signup magic-link")

        sent_url = "/login/sent"
        if next and _is_safe_redirect_path(next) and next != "/":
            # CodeQL alert #132: encode `next` so `&` in the value cannot inject extra params.
            sent_url = f"/login/sent?next={quote(next, safe='/')}"
        return RedirectResponse(url=sent_url, status_code=303)

    return router
