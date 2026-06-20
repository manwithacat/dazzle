"""Tests for the i18n message catalogue + ContextVar wiring (#955 cycle 2).

Cycle 1 shipped the locale-resolution middleware and the identity-passthrough
``_()`` Jinja filter. Cycle 2 adds the catalogue + ContextVar so ``_()``
actually translates against per-request locale state.

Pinned contracts:
  * `register_translations(locale, mapping)` merges onto existing dicts
  * `lookup` returns None on miss (callers fall back to msgid)
  * Primary-subtag fallback: en-GB → en when only "en" registered
  * `_()` reads `locale_ctxvar`, lookups catalogue, falls back to source
  * LocaleMiddleware sets the ContextVar (request-scoped)
"""

from __future__ import annotations

from contextvars import copy_context
from unittest.mock import MagicMock

import pytest

from dazzle.i18n import (
    DEFAULT_LOCALE,
    get_catalogue,
    get_current_locale,
    locale_ctxvar,
    register_translations,
    translate,
)


@pytest.fixture(autouse=True)
def _reset_catalogue():
    """Each test starts with an empty catalogue so cross-test pollution
    can't make a missing-translation lookup pass spuriously."""
    get_catalogue().reset()
    yield
    get_catalogue().reset()


class TestCatalogueRegistration:
    def test_register_then_lookup(self):
        register_translations("fr", {"Welcome": "Bienvenue"})
        assert get_catalogue().lookup("fr", "Welcome") == "Bienvenue"

    def test_register_merges_subsequent_calls(self):
        register_translations("fr", {"Welcome": "Bienvenue"})
        register_translations("fr", {"Sign in": "Connexion"})
        cat = get_catalogue()
        assert cat.lookup("fr", "Welcome") == "Bienvenue"
        assert cat.lookup("fr", "Sign in") == "Connexion"

    def test_lookup_miss_returns_none(self):
        register_translations("fr", {"Welcome": "Bienvenue"})
        assert get_catalogue().lookup("fr", "Unknown") is None

    def test_lookup_for_unregistered_locale_returns_none(self):
        register_translations("fr", {"Welcome": "Bienvenue"})
        assert get_catalogue().lookup("ja", "Welcome") is None

    def test_locale_normalised_lowercase(self):
        register_translations("FR", {"Hi": "Salut"})
        assert get_catalogue().lookup("fr", "Hi") == "Salut"

    def test_empty_locale_no_op(self):
        register_translations("", {"X": "Y"})
        assert get_catalogue().locales() == []

    def test_has_locale(self):
        register_translations("de", {"Hi": "Hallo"})
        assert get_catalogue().has_locale("de")
        assert not get_catalogue().has_locale("ja")

    def test_locales_sorted(self):
        register_translations("ja", {"Hi": "こんにちは"})
        register_translations("fr", {"Hi": "Salut"})
        register_translations("de", {"Hi": "Hallo"})
        assert get_catalogue().locales() == ["de", "fr", "ja"]


class TestPrimarySubtagFallback:
    """Lookup walks `en-GB` → `en` so partial coverage degrades gracefully."""

    def test_subtag_falls_back_to_primary(self):
        register_translations("en", {"Welcome": "Welcome (US)"})
        assert get_catalogue().lookup("en-GB", "Welcome") == "Welcome (US)"

    def test_exact_subtag_wins_when_both_registered(self):
        register_translations("en", {"Welcome": "Welcome (US)"})
        register_translations("en-gb", {"Welcome": "Welcome (UK)"})
        assert get_catalogue().lookup("en-GB", "Welcome") == "Welcome (UK)"

    def test_no_fallback_when_primary_missing(self):
        register_translations("en", {"Welcome": "Welcome"})
        # zh-Hans not registered, zh not registered either → None
        assert get_catalogue().lookup("zh-Hans", "Welcome") is None


class TestTranslateHelper:
    """`translate(locale, msgid, **kwargs)` is the standalone API."""

    @pytest.mark.parametrize(
        ("setup_locale", "setup_mapping", "locale", "msgid", "kwargs", "expected"),
        [
            ("fr", {"Welcome": "Bienvenue"}, "fr", "Welcome", {}, "Bienvenue"),
            (None, {}, "fr", "Welcome", {}, "Welcome"),
            (
                "fr",
                {"Hello {name}": "Bonjour {name}"},
                "fr",
                "Hello {name}",
                {"name": "Alice"},
                "Bonjour Alice",
            ),
            (None, {}, "fr", "Hello {name}", {"name": "Alice"}, "Hello Alice"),
            ("fr", {"Hello {name}": "Bonjour {name}"}, "fr", "Hello {name}", {}, "Bonjour {name}"),
        ],
        ids=[
            "test_returns_translation_when_registered",
            "test_falls_back_to_msgid_on_miss",
            "test_format_kwargs_against_translation",
            "test_format_kwargs_against_msgid_on_miss",
            "test_malformed_format_returns_unsubstituted",
        ],
    )
    def test_translate(
        self,
        setup_locale: str | None,
        setup_mapping: dict,
        locale: str,
        msgid: str,
        kwargs: dict,
        expected: str,
    ) -> None:
        if setup_locale:
            register_translations(setup_locale, setup_mapping)
        assert translate(locale, msgid, **kwargs) == expected


class TestLocaleContextVar:
    """`locale_ctxvar` integrates with the Jinja `_()` filter at render time."""

    def test_default_locale_when_unset(self):
        # Each test runs in a fresh contextvar context (autouse fixture
        # below would conflict if we set it directly — use copy_context).
        ctx = copy_context()
        assert ctx.run(get_current_locale) == DEFAULT_LOCALE

    def test_can_set_locale_in_scoped_context(self):
        def _set_and_read():
            locale_ctxvar.set("fr")
            return get_current_locale()

        ctx = copy_context()
        assert ctx.run(_set_and_read) == "fr"

    def test_outer_context_unaffected_by_inner_set(self):
        """Setting the ctxvar in a copied context doesn't leak back to
        the parent context — required for request isolation in async
        workers serving multiple locales concurrently."""
        outer_locale = get_current_locale()

        def _inner():
            locale_ctxvar.set("ja")
            return get_current_locale()

        ctx = copy_context()
        assert ctx.run(_inner) == "ja"
        assert get_current_locale() == outer_locale


class TestGettextFilterReadsContextVar:
    """`_gettext` reads the locale ContextVar and looks up the catalogue."""

    @pytest.mark.parametrize(
        ("reg_locale", "reg_mapping", "set_locale", "msgid", "kwargs", "expected"),
        [
            (None, {}, "fr", "Welcome", {}, "Welcome"),
            ("fr", {"Welcome": "Bienvenue"}, "fr", "Welcome", {}, "Bienvenue"),
            (None, {}, DEFAULT_LOCALE, "Welcome", {}, "Welcome"),
            (
                "fr",
                {"Hello {name}": "Bonjour {name}"},
                "fr",
                "Hello {name}",
                {"name": "Alice"},
                "Bonjour Alice",
            ),
            ("en", {"Sign in": "Sign in (US)"}, "en-GB", "Sign in", {}, "Sign in (US)"),
        ],
        ids=[
            "test_passthrough_when_no_translation_registered",
            "test_returns_translation_when_locale_matches",
            "test_default_locale_no_lookup_returns_source",
            "test_kwargs_format_against_translation",
            "test_subtag_fallback_through_filter",
        ],
    )
    def test_gettext_filter(
        self,
        reg_locale: str | None,
        reg_mapping: dict,
        set_locale: str,
        msgid: str,
        kwargs: dict,
        expected: str,
    ) -> None:
        from dazzle.render.filters import _gettext

        if reg_locale:
            register_translations(reg_locale, reg_mapping)

        def _run():
            locale_ctxvar.set(set_locale)
            return _gettext(msgid, **kwargs)

        assert copy_context().run(_run) == expected


class TestLocaleMiddlewareSetsContextVar:
    """`LocaleMiddleware.dispatch` sets `locale_ctxvar` for the request."""

    @pytest.mark.asyncio
    async def test_middleware_sets_contextvar_during_dispatch(self):
        from dazzle.http.runtime.locale_middleware import LocaleMiddleware

        seen: list[str] = []

        async def fake_call_next(request):
            # Read the ctxvar from inside the dispatched scope.
            seen.append(get_current_locale())
            return MagicMock()

        mw = LocaleMiddleware(
            app=MagicMock(),
            default_locale="en",
            supported_locales=["en", "fr"],
        )

        request = MagicMock()
        request.headers = {"accept-language": "fr;q=0.9"}
        request.cookies = {}
        request.state = MagicMock()

        await mw.dispatch(request, fake_call_next)
        assert seen == ["fr"]
        # After dispatch the ctxvar resets (we're outside the scope of
        # the token).
        assert get_current_locale() == DEFAULT_LOCALE

    @pytest.mark.asyncio
    async def test_middleware_resets_contextvar_on_exception(self):
        """If the downstream raises, the ctxvar still resets — otherwise
        a stuck locale would bleed across requests on a worker."""
        from dazzle.http.runtime.locale_middleware import LocaleMiddleware

        async def fake_call_next(request):
            raise RuntimeError("downstream blew up")

        mw = LocaleMiddleware(
            app=MagicMock(),
            default_locale="en",
            supported_locales=["en", "fr"],
        )

        request = MagicMock()
        request.headers = {"accept-language": "fr"}
        request.cookies = {}
        request.state = MagicMock()

        with pytest.raises(RuntimeError):
            await mw.dispatch(request, fake_call_next)

        assert get_current_locale() == DEFAULT_LOCALE
