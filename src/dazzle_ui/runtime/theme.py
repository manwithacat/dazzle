"""Theme-variant server-side resolution (UX-048 + UX-056 Q1).

The marketing shell (`site_base.html`) and in-app shell (`base.html`)
both emit `<html data-theme="<variant>">` on first paint. Historically
this was hardcoded to `"light"` and `site.js` flipped it client-side
after `DOMContentLoaded` — which produced a visible flash-of-light for
returning dark-mode users.

This module closes that gap by:

1. Reading a `dz_theme` cookie from the incoming request via
   :class:`ThemeVariantMiddleware` and storing the validated variant
   in :data:`theme_variant_ctxvar`.
2. Exposing :func:`get_theme_variant` as a Jinja global so the two
   layout templates can emit the correct attribute at render time.

The client side (`static/js/site.js` and `templates/layouts/
app_shell.html` Alpine controller) writes the cookie alongside its
existing ``localStorage`` state on toggle. Server + client stay in
sync through the cookie round-trip.

Side-effect: closes UX-048 Q1 (cross-shell sync gap). Both shells
now read the same cookie and write the same cookie on toggle, so a
user toggling dark on the marketing site and then signing in keeps
dark-mode in the in-app shell.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.types import ASGIApp


# The cookie name and accepted values. Kept narrow on purpose —
# unknown cookie values fall back to the default so a malformed
# client can't inject arbitrary attribute values into `<html
# data-theme>`.
COOKIE_NAME = "dz_theme"
DEFAULT_VARIANT = "light"
VALID_VARIANTS: frozenset[str] = frozenset({"light", "dark"})

# Per-request theme variant. The middleware sets it at request
# ingress; Jinja's `theme_variant()` global reads it at render time.
# Defaults to ``DEFAULT_VARIANT`` when no request is active (e.g. in
# unit-test rendering paths that bypass the middleware).
theme_variant_ctxvar: ContextVar[str] = ContextVar("dz_theme_variant", default=DEFAULT_VARIANT)


# #938 — process-wide flag set once at server startup from
# ``[ui] dark_mode_toggle`` in dazzle.toml. When ``False``:
#   - get_theme_variant() returns "light" regardless of the cookie,
#     so a stale ``dz_theme=dark`` cookie from before the project
#     opted out cannot leave the user trapped in a dark-mode render
#     they have no UI affordance to undo.
#   - is_dark_mode_toggle_enabled() returns False so layout
#     templates skip rendering the toggle button in the topbar,
#     sidebar footer, and marketing nav.
_DARK_MODE_TOGGLE_ENABLED = True


def configure_dark_mode_toggle(enabled: bool) -> None:
    """Set the process-wide dark-mode-toggle flag from manifest data.

    Call once at server startup after loading ``dazzle.toml``. Safe
    to call multiple times — the last call wins. No-op when the
    framework is used without a manifest (e.g. unit tests).
    """
    global _DARK_MODE_TOGGLE_ENABLED
    _DARK_MODE_TOGGLE_ENABLED = bool(enabled)


def is_dark_mode_toggle_enabled() -> bool:
    """Return whether the dark/light toggle should render in the
    app shell + marketing nav. Exposed as a Jinja global so layout
    templates can gate the button render on it.
    """
    return _DARK_MODE_TOGGLE_ENABLED


def get_theme_variant() -> str:
    """Return the current request's theme variant, or the default
    when called outside a request context (e.g. in unit tests).

    Used as a Jinja global so templates can call ``{{ theme_variant()
    }}`` to populate ``<html data-theme="…">`` on first paint.

    When ``[ui] dark_mode_toggle = false`` (#938), always returns
    ``"light"`` — a stale cookie from before the project opted out
    cannot trap the user in dark-mode without a toggle button to
    undo it.
    """
    if not _DARK_MODE_TOGGLE_ENABLED:
        return DEFAULT_VARIANT
    return theme_variant_ctxvar.get()


class ThemeVariantMiddleware(BaseHTTPMiddleware):
    """Read the ``dz_theme`` cookie and publish a validated theme
    variant into :data:`theme_variant_ctxvar` for the lifetime of
    the request.

    Unknown cookie values fall back to :data:`DEFAULT_VARIANT`, so a
    malformed client (or a stale cookie from a future schema change)
    can never inject arbitrary strings into the rendered
    ``data-theme`` attribute.

    This middleware is intentionally a no-op when the cookie is
    absent — the ``ContextVar`` default of ``"light"`` already gives
    anonymous first-time visitors the correct starting value.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        raw = request.cookies.get(COOKIE_NAME)
        variant = raw if raw in VALID_VARIANTS else DEFAULT_VARIANT
        token = theme_variant_ctxvar.set(variant)
        try:
            return await call_next(request)
        finally:
            # Restore the previous value so nested request-handlers
            # (rare but possible with Starlette test clients) don't
            # leak state across boundaries.
            theme_variant_ctxvar.reset(token)


def install_theme_middleware(app: ASGIApp) -> None:
    """Register :class:`ThemeVariantMiddleware` on a Starlette/FastAPI
    app. Safe to call multiple times — the last registration wins;
    duplicate registrations are harmless.
    """
    # The stub protocol is sufficient — both Starlette and FastAPI
    # expose an ``add_middleware`` method on their app instances.
    app.add_middleware(ThemeVariantMiddleware)  # type: ignore[attr-defined]
