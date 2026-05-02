"""Internationalisation primitive (#955).

Cycle 1 added ``LocaleMiddleware`` (request-time locale resolution) and
the identity-passthrough ``_()`` Jinja filter. Cycle 2 (this module)
adds the in-memory message catalogue that ``_()`` consults, keyed off
the locale set by the middleware.

The catalogue is registered programmatically via
:func:`register_translations` — projects call it at server-startup time
with a ``dict[locale][msgid] -> translation`` mapping. Cycle 3 adds the
``dazzle i18n extract`` CLI that walks templates and emits a ``.pot``
file; cycle 4 adds ``.po``/``.mo`` compilation. Today, projects that
want to translate can drop the dict inline in their startup hook.

Design choices:

* **Process-global singleton.** A single ``MessageCatalogue`` is shared
  across the worker; locale switches are per-request only. Multi-tenant
  projects that need per-tenant catalogues can register namespaced
  msgids (e.g. ``"tenant_a.welcome"``) — the design stays simple and
  the namespacing convention lives in project code, not the framework.

* **Identity fallback when no translation exists.** A missing
  translation returns the ``msgid`` unchanged (with kwargs interpolated
  if any). This is the same behaviour as cycle 1 so adding the catalogue
  is non-breaking — projects that haven't registered translations get
  the source text everywhere.

* **Locale narrowing.** When the requested locale is ``en-GB`` and the
  catalogue only has ``en``, the lookup falls through to ``en``. This
  matches the middleware's primary-subtag fallback and keeps templates
  rendering in something close to the user's preference even without
  exhaustive coverage.
"""

from __future__ import annotations

import logging
import threading
from contextvars import ContextVar
from typing import Any

logger = logging.getLogger(__name__)

# Per-request locale (mirrors the theme_variant ContextVar pattern in
# `dazzle_ui.runtime.theme`). Set by :class:`LocaleMiddleware` on
# ingress; read by the ``_()`` Jinja filter at render time so templates
# never have to thread the locale through their context arguments.
DEFAULT_LOCALE = "en"
locale_ctxvar: ContextVar[str] = ContextVar("dz_locale", default=DEFAULT_LOCALE)


def get_current_locale() -> str:
    """Return the locale resolved for the current request.

    Falls back to :data:`DEFAULT_LOCALE` outside of a request scope so
    template renders performed in tests / CLI commands stay sane.
    """
    return locale_ctxvar.get()


class MessageCatalogue:
    """In-memory ``dict[locale][msgid] -> translation`` catalogue.

    Thread-safe registration so server-startup registration races are
    impossible. Lookup is not locked — registration is expected to
    complete before request traffic; per-request lookups stay on a
    fast hot path.
    """

    def __init__(self) -> None:
        self._messages: dict[str, dict[str, str]] = {}
        self._register_lock = threading.Lock()

    def register(self, locale: str, messages: dict[str, str]) -> None:
        """Register (or extend) translations for *locale*.

        Subsequent calls for the same locale merge onto the existing
        dict rather than replace it — projects can register per-feature
        bundles without coordination.
        """
        if not locale:
            return
        normalised = locale.strip().lower()
        if not normalised:
            return
        with self._register_lock:
            existing = self._messages.setdefault(normalised, {})
            existing.update(messages)

    def lookup(self, locale: str, msgid: str) -> str | None:
        """Return the translation of *msgid* for *locale*, or ``None``.

        Tries an exact match first, then primary-subtag fallback so a
        request preferring ``en-GB`` still matches ``en`` translations
        when only the latter is registered. ``None`` means "no
        translation registered" — callers should fall back to the
        msgid as the source text.
        """
        if not locale or not msgid:
            return None
        normalised = locale.strip().lower()
        bundle = self._messages.get(normalised)
        if bundle is not None:
            translation = bundle.get(msgid)
            if translation is not None:
                return translation
        # Primary subtag fallback (en-GB → en)
        if "-" in normalised:
            primary = normalised.split("-", 1)[0]
            bundle = self._messages.get(primary)
            if bundle is not None:
                return bundle.get(msgid)
        return None

    def has_locale(self, locale: str) -> bool:
        """Return True iff at least one msgid is registered for *locale*."""
        if not locale:
            return False
        return locale.strip().lower() in self._messages

    def locales(self) -> list[str]:
        """Sorted list of locales for which at least one translation is registered."""
        return sorted(self._messages.keys())

    def reset(self) -> None:
        """Clear all registered translations. Primarily for tests."""
        with self._register_lock:
            self._messages.clear()


# Process-global singleton. Adopters mutate via `register_translations()`;
# the framework reads via `get_catalogue()`. Direct access stays
# discouraged — this is a private name on purpose.
_catalogue = MessageCatalogue()


def get_catalogue() -> MessageCatalogue:
    """Return the process-global :class:`MessageCatalogue` singleton."""
    return _catalogue


def register_translations(locale: str, messages: dict[str, str]) -> None:
    """Convenience: register translations on the global catalogue.

    Typical usage in a project's startup hook::

        from dazzle.i18n import register_translations

        register_translations("fr", {
            "Welcome": "Bienvenue",
            "Sign in": "Connexion",
        })
    """
    _catalogue.register(locale, messages)


def translate(locale: str, msgid: str, **kwargs: Any) -> str:
    """Translate *msgid* for *locale*, falling back to source on miss.

    Performs ``str.format(**kwargs)`` on the result so callers can write
    ``translate("en", "Hello {name}", name="world")``. A missing
    translation returns ``msgid`` unchanged before formatting.
    """
    translation = _catalogue.lookup(locale, msgid)
    if translation is None:
        translation = msgid
    if not kwargs:
        return translation
    try:
        return translation.format(**kwargs)
    except (KeyError, IndexError, ValueError):
        return translation


__all__ = [
    "DEFAULT_LOCALE",
    "MessageCatalogue",
    "get_catalogue",
    "get_current_locale",
    "locale_ctxvar",
    "register_translations",
    "translate",
]
