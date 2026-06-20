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

import logging
import re

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, Response

logger = logging.getLogger(__name__)

LOCALE_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 365
"""1-year persistence — the user's choice should survive cookie
sweeps. Modern browsers cap this at 400 days regardless."""

# Strict allowlist regex applied at the redirect / cookie sinks so the
# taint flow is visible to static analysis (CodeQL py/url-redirection,
# py/cookie-injection). Inline checks at the sinks themselves are the
# pattern CodeQL recognises as a sanitizer; helper functions get
# elided from the taint trace.
_SAFE_RELATIVE_PATH = re.compile(r"\A/(?!/)[A-Za-z0-9._~/\-?#=&%]{0,2048}\Z")
"""Same-origin relative URL: starts with a single ``/`` (not ``//``,
which would be protocol-relative), only safe URL characters, capped at
2 KB. Rejects schemes, hosts, control characters, and CR/LF."""

_SAFE_LOCALE_TAG = re.compile(r"\A[a-z]{2,3}(?:-[a-z0-9]{2,8}){0,4}\Z")
"""BCP-47 tag shape: 2-3 letter primary subtag, optionally followed by
up to 4 alphanumeric subtags of length 2-8. No semicolons, CRLF, or
other cookie-injection vectors can pass."""


def _safe_redirect_target(raw: str | None) -> str:
    """Return *raw* iff it's a same-origin relative path; else ``"/"``.

    Test-only helper that delegates to the same regex used inline at
    the redirect sink. The sink itself does NOT call this — CodeQL
    elides helper calls from its taint trace, so the inline check at
    the sink is what registers as a sanitizer.
    """
    if not raw:
        return "/"
    return raw if _SAFE_RELATIVE_PATH.fullmatch(raw) else "/"


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
        from dazzle.http.runtime.locale_middleware import _normalise_locale

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

        # Inline sanitization at the sink (CodeQL py/url-redirection).
        # `next` is form-controlled so any non-matching value falls back
        # to "/" — an attacker can't bounce us to https://evil.com.
        target = next if _SAFE_RELATIVE_PATH.fullmatch(next or "") else "/"

        # HTMX: reply with HX-Refresh so the current page re-renders
        # against the new locale without a full navigation.
        is_htmx = request.headers.get("hx-request", "").lower() == "true"
        if is_htmx:
            response: Response = Response(status_code=204)
            response.headers["HX-Refresh"] = "true"
        else:
            response = RedirectResponse(url=target, status_code=303)

        # Inline sanitization at the sink (CodeQL py/cookie-injection).
        # `_normalise_locale` already strips garbage, but enforcing the
        # BCP-47 shape one more time at the cookie sink makes the
        # injection-defense visible to static analysis.
        if not _SAFE_LOCALE_TAG.fullmatch(normalised):
            return Response(
                status_code=400,
                content="Invalid locale tag",
                media_type="text/plain",
            )

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
