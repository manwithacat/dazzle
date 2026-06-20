"""Shared SSO session completion (auth Plan 5.ii).

The tail every enterprise-SSO callback runs once it has a proven ``(user, membership)``
— OIDC (4b.iii) and SAML (5.ii) both end here. Kept in one place so the security-critical
session-fixation + cookie handling has a single source of truth (no drift between the two
callbacks).

NOT a FastAPI route module (no decorators), so ADR-0014's no-``from __future__`` rule for
route files doesn't apply — but we omit it anyway since this imports fastapi response types.
"""

from typing import Any

from fastapi.responses import RedirectResponse

from dazzle.http.runtime.auth.cookie_name import read_session_id, select_write_name
from dazzle.http.runtime.auth.crypto import cookie_secure


def finish_login_session(
    request: Any,
    store: Any,
    user: Any,
    membership_id: str,
    *,
    cookie_name: str,
    safe_next: str,
) -> RedirectResponse:
    """Mint the authenticated session and return the post-login redirect.

    Session-fixation defence (mirrors sso_routes / #1198): a fresh server-minted session
    id replaces any pre-auth cookie the client presented (the old one is deleted). Sets the
    auth cookie + the session-bound CSRF cookie with the standard flags. ``safe_next`` MUST
    already be validated by the caller (it is the redirect target).
    """
    pre_auth_sid = read_session_id(request, default=cookie_name)
    session = store.create_session(user, active_membership_id=membership_id)
    if pre_auth_sid and pre_auth_sid != session.id:
        store.delete_session(pre_auth_sid)

    response = RedirectResponse(url=safe_next, status_code=303)
    response.set_cookie(
        key=select_write_name(
            request, user_roles=list(getattr(user, "roles", []) or []), default=cookie_name
        ),
        value=session.id,
        httponly=True,
        secure=cookie_secure(request),
        samesite="lax",
    )
    # Declarative-CSRF: bind the CSRF token to the new session (httponly=False so htmx/JS
    # can echo it into X-CSRF-Token). Mirrors the auth cookie's flags.
    response.set_cookie(
        key="dazzle_csrf",
        value=session.csrf_secret,
        httponly=False,
        secure=cookie_secure(request),
        samesite="lax",
    )
    return response
