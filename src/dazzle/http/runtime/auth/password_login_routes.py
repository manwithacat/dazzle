"""Form-encoded password-mode login + signup endpoints (Phase 1.B.3,
v0.67.32). Pairs with the typed-Fragment views in `auth_views.py`:
`build_login_password_view` posts to `/auth/login/password`, and
`build_signup_password_view` posts to `/auth/signup/password`.

The legacy JSON endpoints in `routes.py` (`/auth/login`, `/auth/register`)
remain mounted for programmatic API callers; these new endpoints accept
`application/x-www-form-urlencoded`, set the session cookie, and return
HTML redirects so the typed-Fragment forms work end-to-end without JS.

Mount only when `app.state.auth_password_mode_enabled` is True (the
default is False — magic-link mode is the framework default per
ADR-N from the Jinja2 retirement plan)."""

import logging
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Form, Query, Request
from fastapi.responses import RedirectResponse, Response

from dazzle.http.runtime.auth.auth_views import leftover_auth_email_or_400
from dazzle.http.runtime.auth.enterprise_login import sso_redirect_for
from dazzle.http.runtime.auth.redirect_safety import (
    is_safe_redirect_path as _is_safe_redirect_path,
)
from dazzle.http.runtime.auth.sign_in import complete_sign_in

_logger = logging.getLogger(__name__)


def _encode_next(value: str) -> str:
    """URL-encode a `next` parameter value for safe interpolation into
    a query string (CodeQL alert #132 / py/url-redirection).

    `_is_safe_redirect_path` rejects scheme/netloc/backslash but accepts
    paths like `/foo&inject=1` whose `&` would inject extra query params
    when interpolated raw into another URL. `quote(safe="/")` percent-
    encodes everything except `/`, so the interpolated value is treated
    as a single query-string value rather than a separator-bearing tail.
    """
    return quote(value, safe="/")


def create_password_login_routes() -> APIRouter:
    """Form-encoded password-mode endpoints for the typed-Fragment views."""
    router = APIRouter(tags=["auth"])

    @router.post("/auth/login/password")
    async def submit_login_password(
        request: Request,
        email: Annotated[str, Form()] = "",
        password: Annotated[str, Form()] = "",
        next: Annotated[str, Query()] = "/",
    ) -> Response:
        """Authenticate email + password and create a session.

        Failed authentication redirects to `/login?error=invalid_credentials`
        (preserving `?next=` so the user lands on the original page after
        a successful retry).
        """
        auth_store = request.app.state.auth_store
        # Leftover ``email=zzz`` used to invent invalid_credentials.
        normalized_email = leftover_auth_email_or_400(email)
        if not isinstance(normalized_email, str):
            return normalized_email
        safe_next_param = next if next and next != "/" and _is_safe_redirect_path(next) else ""
        # DD-013 require_sso: the org's IdP owns this address; the password is never checked.
        sso_url = sso_redirect_for(request, auth_store, normalized_email, next_path=safe_next_param)
        if sso_url is not None:
            return RedirectResponse(url=sso_url, status_code=303)
        user = auth_store.authenticate(normalized_email, password) if password else None
        if user is None:
            target = "/login?error=invalid_credentials"
            if next and _is_safe_redirect_path(next) and next != "/":
                target = f"/login?error=invalid_credentials&next={_encode_next(next)}"
            return RedirectResponse(url=target, status_code=303)

        # The single sign-in completion point (#1804): org activation, the 2FA
        # challenge when one is owed, session-fixation defence, cookies, event.
        safe_next = next if next and next != "/" and _is_safe_redirect_path(next) else "/app"
        return await complete_sign_in(
            request, auth_store, user, method="password", mode="redirect", next_url=safe_next
        )

    @router.post("/auth/signup/password")
    async def submit_signup_password(
        request: Request,
        email: Annotated[str, Form()] = "",
        name: Annotated[str, Form()] = "",
        password: Annotated[str, Form()] = "",
        confirm_password: Annotated[str, Form()] = "",
        next: Annotated[str, Query()] = "/",
    ) -> Response:
        """Create a password-mode user and sign them in.

        Failure paths:
          - leftover / malformed email stays put (400) — do not invent
            ``invalid_email`` theater (oral #105).
          - ``mismatch``: ``password != confirm_password`` (303).
          - blank email: ``/signup?error=invalid_email`` (honest first-visit).
          - ``already_registered``: ``get_user_by_email`` returned a row.
          - ``create_failed``: ``create_user`` raised — usually a
            unique-constraint race we lost to a concurrent signup.

        Success path: create session, set cookie, redirect to
        ``next_url`` (when safe) or ``/app``.
        """
        if not password or password != confirm_password:
            return RedirectResponse(url="/signup?error=mismatch", status_code=303)

        auth_store = request.app.state.auth_store
        # Leftover ``email=zzz`` used to invent /signup?error=invalid_email.
        normalized_email = leftover_auth_email_or_400(email)
        if not isinstance(normalized_email, str):
            return normalized_email
        normalized_name = name.strip() or None

        if not normalized_email:
            return RedirectResponse(url="/signup?error=invalid_email", status_code=303)

        # DD-013 require_sso: the org's IdP owns this address; no local account is created.
        sso_url = sso_redirect_for(request, auth_store, normalized_email)
        if sso_url is not None:
            return RedirectResponse(url=sso_url, status_code=303)

        existing = auth_store.get_user_by_email(normalized_email)
        if existing is not None:
            return RedirectResponse(url="/signup?error=already_registered", status_code=303)

        try:
            user = auth_store.create_user(
                email=normalized_email,
                password=password,
                username=normalized_name,
            )
        except Exception as exc:  # noqa: BLE001 — surface in logs
            _logger.warning(  # nosemgrep
                "Signup: create_user failed for %s: %s",  # nosemgrep
                normalized_email,
                exc,
            )
            return RedirectResponse(url="/signup?error=create_failed", status_code=303)

        # A brand-new user has no memberships yet: NoOrgs → /auth/no-orgs when the app
        # gates on membership; an enforce_for_roles role lands on 2FA enrolment.
        safe_next = next if next and next != "/" and _is_safe_redirect_path(next) else "/app"
        return await complete_sign_in(
            request,
            auth_store,
            user,
            method="signup",
            mode="redirect",
            next_url=safe_next,
            event="registered",
        )

    return router
