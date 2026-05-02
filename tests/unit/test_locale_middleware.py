"""Tests for the locale-resolution middleware (#955 cycle 1).

Pins:

  * cookie override > Accept-Language > default
  * Accept-Language quality weighting + supported-locale narrowing
  * primary-subtag fallback (en-GB → en when only "en" is supported)
  * empty supported list = "any locale OK" — pick highest-quality candidate
  * malformed inputs fall through cleanly (no crashes, no surprises)
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from dazzle_back.runtime.locale_middleware import (
    LocaleMiddleware,
    _normalise_locale,
    _pick_supported,
    parse_accept_language,
)


class TestNormaliseLocale:
    def test_lowercases(self) -> None:
        assert _normalise_locale("EN-GB") == "en-gb"

    def test_strips_whitespace(self) -> None:
        assert _normalise_locale("  fr  ") == "fr"

    def test_rejects_empty(self) -> None:
        assert _normalise_locale("") == ""
        assert _normalise_locale("   ") == ""

    def test_rejects_non_letter_primary(self) -> None:
        assert _normalise_locale("12-foo") == ""
        assert _normalise_locale("a") == ""  # too short

    def test_rejects_garbage_chars(self) -> None:
        assert _normalise_locale("en;DROP TABLE") == ""
        assert _normalise_locale("en/gb") == ""


class TestParseAcceptLanguage:
    def test_single_locale(self) -> None:
        assert parse_accept_language("en") == [("en", 1.0)]

    def test_multiple_with_quality(self) -> None:
        result = parse_accept_language("fr;q=0.8, en;q=0.9, de;q=0.7")
        assert result == [("en", 0.9), ("fr", 0.8), ("de", 0.7)]

    def test_quality_zero_excluded(self) -> None:
        result = parse_accept_language("en;q=0, fr;q=0.5")
        assert result == [("fr", 0.5)]

    def test_malformed_q_value_skipped(self) -> None:
        result = parse_accept_language("en;q=high, fr;q=0.5")
        assert result == [("fr", 0.5)]

    def test_empty_header(self) -> None:
        assert parse_accept_language("") == []

    def test_garbage_entries_skipped(self) -> None:
        result = parse_accept_language("12-foo, en;q=0.9, /;q=0.5")
        assert result == [("en", 0.9)]


class TestPickSupported:
    def test_exact_match_wins(self) -> None:
        candidates = [("en-gb", 1.0), ("en", 0.8)]
        assert _pick_supported(candidates, frozenset({"en-gb", "en"}), "en") == "en-gb"

    def test_primary_subtag_fallback(self) -> None:
        """Browser sends en-GB, project supports only `en` → match on `en`."""
        candidates = [("en-gb", 1.0)]
        assert _pick_supported(candidates, frozenset({"en"}), "fr") == "en"

    def test_default_when_none_match(self) -> None:
        candidates = [("ja", 1.0), ("ko", 0.8)]
        assert _pick_supported(candidates, frozenset({"en", "fr"}), "en") == "en"

    def test_empty_supported_picks_first_candidate(self) -> None:
        """An empty supported set means "any locale ok" — return the
        first candidate. ``parse_accept_language`` sorts by quality
        descending so callers passing the helper's output get the
        highest-quality locale automatically."""
        # As parse_accept_language would yield: highest q first.
        candidates = [("en", 1.0), ("ja", 0.9)]
        assert _pick_supported(candidates, frozenset(), "fr") == "en"

    def test_empty_supported_no_candidates_falls_back(self) -> None:
        assert _pick_supported([], frozenset(), "en") == "en"


@pytest.fixture()
def make_request():
    """Build a minimal Starlette-shaped Request stub."""

    def _make(
        accept_language: str = "",
        locale_cookie: str = "",
        cookie_name: str = "dazzle_locale",
    ):
        request = MagicMock()
        request.headers = {"accept-language": accept_language} if accept_language else {}
        request.cookies = {cookie_name: locale_cookie} if locale_cookie else {}
        request.state = MagicMock()
        return request

    return _make


class TestLocaleMiddlewareResolution:
    """End-to-end resolution priority: cookie > Accept-Language > default."""

    def _middleware(
        self,
        default: str = "en",
        supported: list[str] | None = None,
    ) -> LocaleMiddleware:
        return LocaleMiddleware(
            app=MagicMock(),
            default_locale=default,
            supported_locales=supported,
        )

    def test_cookie_wins_over_accept_language(self, make_request) -> None:
        mw = self._middleware(default="en", supported=["en", "fr", "de"])
        req = make_request(accept_language="de;q=0.9, en;q=0.5", locale_cookie="fr")
        assert mw._resolve(req) == "fr"

    def test_cookie_ignored_when_unsupported(self, make_request) -> None:
        mw = self._middleware(default="en", supported=["en", "fr"])
        req = make_request(accept_language="de;q=0.9", locale_cookie="ja")
        # Cookie 'ja' isn't supported → fall through to Accept-Language.
        # 'de' isn't supported either → fall to default.
        assert mw._resolve(req) == "en"

    def test_accept_language_used_when_no_cookie(self, make_request) -> None:
        mw = self._middleware(default="en", supported=["en", "fr"])
        req = make_request(accept_language="fr;q=0.9, en;q=0.5")
        assert mw._resolve(req) == "fr"

    def test_default_when_no_cookie_or_header(self, make_request) -> None:
        mw = self._middleware(default="en", supported=["en", "fr"])
        req = make_request()
        assert mw._resolve(req) == "en"

    def test_primary_subtag_fallback_on_accept_language(self, make_request) -> None:
        mw = self._middleware(default="en", supported=["en"])
        req = make_request(accept_language="en-GB;q=0.9, fr;q=0.5")
        assert mw._resolve(req) == "en"

    def test_unsupported_default_normalised(self, make_request) -> None:
        """Garbage default falls back to `en` — defensive against
        malformed dazzle.toml [i18n] default values."""
        mw = self._middleware(default="!!!garbage!!!")
        req = make_request()
        assert mw._resolve(req) == "en"

    def test_empty_supported_list_passes_user_preference(self, make_request) -> None:
        mw = self._middleware(default="en", supported=[])
        req = make_request(accept_language="ja;q=0.9, ko;q=0.7")
        assert mw._resolve(req) == "ja"


class TestGettextFilter:
    """The ``_()`` Jinja filter is identity-passthrough in cycle 1."""

    def test_passthrough_no_kwargs(self) -> None:
        from dazzle_ui.runtime.template_renderer import _gettext

        assert _gettext("Hello") == "Hello"

    def test_format_substitutes_kwargs(self) -> None:
        from dazzle_ui.runtime.template_renderer import _gettext

        assert _gettext("Hello {name}", name="world") == "Hello world"

    def test_malformed_format_returns_source(self) -> None:
        """Don't raise on malformed placeholders; cycle 2 will warn."""
        from dazzle_ui.runtime.template_renderer import _gettext

        # Missing kwarg should not crash — return the unsubstituted string.
        assert _gettext("Hello {missing}") == "Hello {missing}"


class TestI18nManifestConfig:
    """`[i18n]` block parses cleanly + defaults are sane."""

    def test_defaults(self) -> None:
        from dazzle.core.manifest import I18nConfig

        cfg = I18nConfig()
        assert cfg.default_locale == "en"
        assert cfg.supported_locales == []
        assert cfg.cookie_name == "dazzle_locale"

    def test_parses_block(self, tmp_path) -> None:
        """`[i18n]` block in dazzle.toml lands on `manifest.i18n`."""
        from dazzle.core.manifest import load_manifest

        toml = tmp_path / "dazzle.toml"
        toml.write_text(
            """
[project]
name = "test"
version = "0.1.0"

[modules]
paths = ["./dsl"]

[i18n]
default = "fr"
supported = ["fr", "en", "de"]
"""
        )
        manifest = load_manifest(toml)
        assert manifest.i18n.default_locale == "fr"
        assert manifest.i18n.supported_locales == ["fr", "en", "de"]

    def test_missing_block_uses_defaults(self, tmp_path) -> None:
        from dazzle.core.manifest import load_manifest

        toml = tmp_path / "dazzle.toml"
        toml.write_text(
            """
[project]
name = "test"
version = "0.1.0"

[modules]
paths = ["./dsl"]
"""
        )
        manifest = load_manifest(toml)
        assert manifest.i18n.default_locale == "en"
        assert manifest.i18n.supported_locales == []
