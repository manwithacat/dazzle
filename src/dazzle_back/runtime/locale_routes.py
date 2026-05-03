"""Locale-switcher endpoint (#955 cycle 6).

Exposes ``POST /_dazzle/i18n/locale`` so the locale-switcher UI can
persist a user's choice. The cycle-1 ``LocaleMiddleware`` already
honours the cookie this endpoint sets — the missing piece was a
sanctioned way for the user to write to it.

Default cookie name is ``dazzle_locale``; matches the middleware's
default. Adopters who customise the middleware's ``cookie_name`` need
to pass the same value here when constructing the router.

Returns 303 redirect by default (so a plain ``<form>`` round-trip
lands the user back where they started). Sends ``HX-Refresh: true``
when the request is HTMX so the page re-renders against the new
locale without losing the URL.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response

logger = logging.getLogger(__name__)

LOCALE_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365
"""1-year persistence — the user's choice should survive cookie
sweeps. Modern browsers cap this at 400 days regardless."""


def _safe_redirect_target(raw: str | None) -> str:
    """Return *raw* iff it's a same-origin relative path; else ``"/"``.

    Defends against open-redirect attacks: an attacker-controlled
    ``next=https://evil.com`` mustn't bounce the user off-site after
    they switch locale. Only relative paths starting with a single ``/``
    (and not ``//`` which would be protocol-relative) pass through.
    """
    if not raw:
        return "/"
    parsed = urlparse(raw)
    # Reject any URL with a scheme or netloc — those are absolute and
    # potentially off-site. Also reject protocol-relative URLs (//evil/).
    if parsed.scheme or parsed.netloc:
        return "/"
    if not raw.startswith("/") or raw.startswith("//"):
        return "/"
    return raw


def create_locale_routes(
    *,
    cookie_name: str = "dazzle_locale",
    supported_locales: frozenset[str] | None = None,
) -> APIRouter:
    """Build the router carrying ``POST /_dazzle/i18n/locale``.

    Args:
        cookie_name: Cookie key the middleware reads. Pass the same
            value the middleware was constructed with.
        supported_locales: Allow-list. ``None`` / empty means "accept
            any plausible BCP-47 tag" — useful when the project hasn't
            decided on a translation matrix yet but still wants the
            switcher to work.
    """
    router = APIRouter(prefix="/_dazzle/i18n", tags=["i18n"])

    @router.post("/locale")
    async def set_locale(
        request: Request,
        locale: str = Form(...),
        next: str = Form("/"),
    ) -> Response:
        from dazzle_back.runtime.locale_middleware import _normalise_locale

        normalised = _normalise_locale(locale)
        if not normalised:
            return Response(
                status_code=400,
                content="Invalid locale tag",
                media_type="text/plain",
            )

        if supported_locales:
            primary = normalised.split("-", 1)[0]
            if normalised not in supported_locales and primary not in supported_locales:
                return Response(
                    status_code=400,
                    content=f"Unsupported locale {normalised!r}",
                    media_type="text/plain",
                )

        target = _safe_redirect_target(next)

        # HTMX: reply with HX-Refresh so the current page re-renders
        # against the new locale without a full navigation.
        is_htmx = request.headers.get("hx-request", "").lower() == "true"
        if is_htmx:
            response: Response = Response(status_code=204)
            response.headers["HX-Refresh"] = "true"
        else:
            response = RedirectResponse(url=target, status_code=303)

        # Secure flag follows the request scheme so production (HTTPS)
        # gets the protection while dev (HTTP localhost) still
        # persists the cookie. Reverse-proxy deployments that
        # terminate TLS should populate `X-Forwarded-Proto`; FastAPI
        # honours that via the ProxyHeadersMiddleware so request.url.scheme
        # reflects the original scheme.
        is_https = request.url.scheme == "https"
        response.set_cookie(
            cookie_name,
            normalised,
            max_age=LOCALE_COOKIE_MAX_AGE_SECONDS,
            httponly=True,
            samesite="lax",
            secure=is_https,
        )
        return response

    return router


__all__ = ["LOCALE_COOKIE_MAX_AGE_SECONDS", "create_locale_routes"]
