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
from urllib.parse import urlparse

from fastapi import APIRouter, Query, Request
from fastapi.responses import RedirectResponse

from dazzle_back.runtime.auth.magic_link import validate_magic_link


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
        session = auth_store.create_session(user)

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

    return router
