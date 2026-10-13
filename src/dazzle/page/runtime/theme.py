"""Request-scoped app-shell chrome state read from cookies (#1294).

:class:`ThemeVariantMiddleware` reads the ``dz_sidebar`` cookie at request
ingress and publishes a validated value in :data:`sidebar_state_ctxvar`;
:func:`get_sidebar_state` hands it to the Fragment app shell so SSR emits the
correct ``data-dz-sidebar`` attribute on first paint.

The light/dark colour scheme is not resolved server-side: ``static/js/site.js``
reads the ``dz_theme`` cookie and rewrites ``data-theme`` on first paint. A
server-side theme-variant context variable used to be published here as well,
but its only reader (a Jinja global) went with ADR-0023 and nothing read it
afterwards, so it was removed in flense ship K.
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


# ── Sidebar open/closed state (#1294) ───────────────────────────────
# The Fragment app-shell sidebar is driven by `data-dz-sidebar` on the
# shell root (open → slid on-screen + content offset; closed → off-
# screen). The state persists in the `dz_sidebar` cookie, written by
# the topbar toggle's JS controller and read back here at request
# ingress so SSR emits the correct initial attribute (no flash, and —
# critically — the nav is reachable on first paint). Default "open" so
# anonymous first-time visitors land on a desktop shell with visible
# navigation.
SIDEBAR_COOKIE_NAME = "dz_sidebar"
DEFAULT_SIDEBAR_STATE = "open"
VALID_SIDEBAR_STATES: frozenset[str] = frozenset({"open", "closed"})
sidebar_state_ctxvar: ContextVar[str] = ContextVar(
    "dz_sidebar_state", default=DEFAULT_SIDEBAR_STATE
)


# #938/#1445 — `[ui] dark_mode_toggle` previously lived here as a process-wide
# module global (`_DARK_MODE_TOGGLE_ENABLED`) set at boot via `configure_dark_mode_toggle`
# and read via `is_dark_mode_toggle_enabled()`. That was an ADR-0005 mutable-global
# violation (and forced per-process, blocking per-tenant override). The flag now flows
# through the typed render context: `app.state.dark_mode_toggle` is set at boot from the
# manifest, threaded onto `SitePageContext.dark_mode_toggle`, and the site nav renderer
# gates the toggle button on `ctx.dark_mode_toggle`.


def get_sidebar_state() -> str:
    """Return the current request's app-shell sidebar state ("open" or
    "closed"), or the default ("open") outside a request context.

    Emitted as ``data-dz-sidebar`` on ``.dz-app-shell`` so the sidebar
    renders on-screen (and the nav is reachable) on first paint (#1294).
    """
    return sidebar_state_ctxvar.get()


class ThemeVariantMiddleware(BaseHTTPMiddleware):
    """Read the ``dz_sidebar`` cookie and publish a validated sidebar
    state into :data:`sidebar_state_ctxvar` for the lifetime of the
    request.

    Unknown cookie values fall back to :data:`DEFAULT_SIDEBAR_STATE`,
    so a malformed client can never inject arbitrary strings into the
    rendered ``data-dz-sidebar`` attribute.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # #1294 — unknown/absent → DEFAULT_SIDEBAR_STATE ("open") so a
        # malformed cookie can't inject arbitrary `data-dz-sidebar`
        # values and first-time visitors get a reachable nav.
        raw_sidebar = request.cookies.get(SIDEBAR_COOKIE_NAME)
        sidebar = raw_sidebar if raw_sidebar in VALID_SIDEBAR_STATES else DEFAULT_SIDEBAR_STATE
        sidebar_token = sidebar_state_ctxvar.set(sidebar)
        try:
            return await call_next(request)
        finally:
            # Restore the previous value so nested request-handlers
            # (rare but possible with Starlette test clients) don't
            # leak state across boundaries.
            sidebar_state_ctxvar.reset(sidebar_token)


def install_theme_middleware(app: ASGIApp) -> None:
    """Register :class:`ThemeVariantMiddleware` on a Starlette/FastAPI
    app. Safe to call multiple times — the last registration wins;
    duplicate registrations are harmless.
    """
    # The stub protocol is sufficient — both Starlette and FastAPI
    # expose an ``add_middleware`` method on their app instances.
    app.add_middleware(ThemeVariantMiddleware)  # type: ignore[attr-defined]
