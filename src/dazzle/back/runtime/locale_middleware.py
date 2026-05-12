"""Locale-resolution middleware (#955 cycle 1).

Resolves the request's locale from (in order):

  1. Explicit cookie override (default name ``dazzle_locale``) — set by
     the locale-switcher UI primitive in cycle 6.
  2. ``Accept-Language`` header — quality-weighted, narrowed to the
     project's supported locales.
  3. Project default (``[i18n] default = "en"`` in dazzle.toml).

Sets ``request.state.locale`` (a ``str``) and ``request.state.locale_supported``
(a ``frozenset[str]``). Templates and route handlers read these to drive
gettext lookups, date/number formatting, and per-locale layout choices.

Cycle 1 scope is **resolution only** — no message catalogue is loaded yet
and the ``_()`` Jinja filter passes its argument through unchanged. The
state attributes still land on every request so adopters can probe locale
selection in templates today (``request.state.locale``) and the wiring is
in place for cycle 2's gettext catalogue.
"""

from __future__ import annotations

import logging
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


_BCP47_TAG_CHARS = set("abcdefghijklmnopqrstuvwxyz0123456789-")


def _normalise_locale(raw: str) -> str:
    """Lower-case + strip the locale tag; keep ``en-GB`` shape, drop garbage.

    Returns an empty string for input that isn't a plausible BCP-47 tag
    (so the caller falls through to the next resolution layer instead of
    matching against a malformed cookie value).
    """
    candidate = raw.strip().lower()
    if not candidate:
        return ""
    # First segment must be 2-3 letters; subsequent segments 2-8 alnum.
    parts = candidate.split("-")
    if not (2 <= len(parts[0]) <= 3 and parts[0].isalpha()):
        return ""
    if not all(set(part).issubset(_BCP47_TAG_CHARS) for part in parts):
        return ""
    return candidate


def parse_accept_language(header: str) -> list[tuple[str, float]]:
    """Parse an Accept-Language header into ``[(locale, q-weight), ...]``.

    Sorted by quality descending (RFC 9110). Malformed entries are
    skipped silently — a quality of 0 means "explicitly excluded" so we
    drop those too.
    """
    if not header:
        return []
    out: list[tuple[str, float]] = []
    for entry in header.split(","):
        if not entry.strip():
            continue
        bits = entry.split(";", 1)
        tag = _normalise_locale(bits[0])
        if not tag:
            continue
        q = 1.0
        if len(bits) == 2 and "q=" in bits[1]:
            try:
                q = float(bits[1].strip().removeprefix("q="))
            except ValueError:
                continue
        if q <= 0:
            continue
        out.append((tag, q))
    out.sort(key=lambda pair: -pair[1])
    return out


def _pick_supported(
    candidates: list[tuple[str, float]],
    supported: frozenset[str],
    default: str,
) -> str:
    """Walk *candidates* highest-quality-first; return the first match
    against *supported*. Falls back to *default* when nothing matches.

    Matches both exact tag (``en-GB``) and primary subtag (``en``) so a
    request preferring ``en-GB`` still picks ``en`` when only the latter
    is supported.
    """
    if not supported:
        # An empty supported-set means "every locale is fine" — pick the
        # highest-quality candidate, falling back to the default.
        return candidates[0][0] if candidates else default
    for tag, _q in candidates:
        if tag in supported:
            return tag
        primary = tag.split("-", 1)[0]
        if primary in supported:
            return primary
    return default


class LocaleMiddleware(BaseHTTPMiddleware):
    """Sets ``request.state.locale`` from cookie / Accept-Language / default.

    Configuration is captured at construction time from
    :class:`~dazzle.core.manifest.I18nConfig` so the request hot-path
    only touches a frozenset + a header parse — no per-request manifest
    reload.
    """

    def __init__(
        self,
        app: Any,
        *,
        default_locale: str = "en",
        supported_locales: list[str] | None = None,
        cookie_name: str = "dazzle_locale",
    ) -> None:
        super().__init__(app)
        self._default = _normalise_locale(default_locale) or "en"
        self._supported = frozenset(
            _normalise_locale(loc) for loc in (supported_locales or []) if _normalise_locale(loc)
        )
        self._cookie_name = cookie_name

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        locale = self._resolve(request)
        request.state.locale = locale
        request.state.locale_supported = self._supported

        # #955 cycle 2: also set the i18n ContextVar so the `_()` Jinja
        # filter can read the locale at render time without templates
        # threading it through their context. The reset on the way out
        # is good hygiene for test environments where multiple requests
        # share a worker.
        from dazzle.i18n import locale_ctxvar

        token = locale_ctxvar.set(locale)
        try:
            response: Response = await call_next(request)
            return response
        finally:
            locale_ctxvar.reset(token)

    def _resolve(self, request: Request) -> str:
        # 1. Cookie override
        raw_cookie = request.cookies.get(self._cookie_name, "")
        cookie_locale = _normalise_locale(raw_cookie)
        if cookie_locale and self._matches_supported(cookie_locale):
            return cookie_locale

        # 2. Accept-Language
        candidates = parse_accept_language(request.headers.get("accept-language", ""))
        if candidates:
            picked = _pick_supported(candidates, self._supported, self._default)
            if picked:
                return picked

        # 3. Default
        return self._default

    def _matches_supported(self, locale: str) -> bool:
        if not self._supported:
            return True
        if locale in self._supported:
            return True
        return locale.split("-", 1)[0] in self._supported
