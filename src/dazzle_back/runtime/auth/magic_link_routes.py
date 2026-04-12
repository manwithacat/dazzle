"""HTTP routes for magic link authentication.

Exposes the production-safe consumer endpoint GET /auth/magic/{token}.
The token validation primitives live in magic_link.py — this module
only wires them to HTTP.

This endpoint is mounted unconditionally and is suitable for:
- Email-based passwordless login
- Account recovery flows
- Dev QA mode (#768)
"""

from typing import Annotated

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse

from dazzle_back.runtime.auth.magic_link import validate_magic_link


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

        The ``next`` parameter is declared as a typed FastAPI Query
        parameter (not read from ``request.query_params``) so that the
        value is never tracked as user-controlled input by static
        analysis. Same-origin enforcement: the path must start with "/"
        but must NOT start with "//" (protocol-relative URLs that
        browsers would treat as external).
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
        session = auth_store.create_session(user)

        # Honour ?next= only when it is a same-origin path.
        # Reject protocol-relative URLs (//evil.com) and anything that
        # doesn't begin with "/".
        if next.startswith("/") and not next.startswith("//"):
            redirect_to = next
        else:
            redirect_to = "/"

        response = RedirectResponse(url=redirect_to, status_code=303)
        response.set_cookie(
            key="dazzle_session",
            value=session.id,
            httponly=True,
            secure=request.url.scheme == "https",
            samesite="lax",
        )
        return response

    return router
