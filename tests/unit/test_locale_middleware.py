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

from dazzle.http.runtime.locale_middleware import (
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
    @pytest.mark.parametrize(
        ("header", "expected"),
        [
            ("en", [("en", 1.0)]),
            ("fr;q=0.8, en;q=0.9, de;q=0.7", [("en", 0.9), ("fr", 0.8), ("de", 0.7)]),
            ("en;q=0, fr;q=0.5", [("fr", 0.5)]),
            ("en;q=high, fr;q=0.5", [("fr", 0.5)]),
            ("", []),
            ("12-foo, en;q=0.9, /;q=0.5", [("en", 0.9)]),
        ],
        ids=[
            "test_single_locale",
            "test_multiple_with_quality",
            "test_quality_zero_excluded",
            "test_malformed_q_value_skipped",
            "test_empty_header",
            "test_garbage_entries_skipped",
        ],
    )
    def test_parse(self, header: str, expected: list[tuple[str, float]]) -> None:
        assert parse_accept_language(header) == expected


class TestPickSupported:
    @pytest.mark.parametrize(
        ("candidates", "supported", "default", "expected"),
        [
            ([("en-gb", 1.0), ("en", 0.8)], frozenset({"en-gb", "en"}), "en", "en-gb"),
            ([("en-gb", 1.0)], frozenset({"en"}), "fr", "en"),
            ([("ja", 1.0), ("ko", 0.8)], frozenset({"en", "fr"}), "en", "en"),
            ([("en", 1.0), ("ja", 0.9)], frozenset(), "fr", "en"),
            ([], frozenset(), "en", "en"),
        ],
        ids=[
            "test_exact_match_wins",
            "test_primary_subtag_fallback",
            "test_default_when_none_match",
            "test_empty_supported_picks_first_candidate",
            "test_empty_supported_no_candidates_falls_back",
        ],
    )
    def test_pick(self, candidates, supported, default, expected) -> None:
        assert _pick_supported(candidates, supported, default) == expected


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

    @pytest.mark.parametrize(
        ("default", "supported", "accept_language", "locale_cookie", "expected"),
        [
            # Cookie wins over Accept-Language when supported
            ("en", ["en", "fr", "de"], "de;q=0.9, en;q=0.5", "fr", "fr"),
            # Unsupported cookie + unsupported Accept-Language → default
            ("en", ["en", "fr"], "de;q=0.9", "ja", "en"),
            # Accept-Language used when no cookie
            ("en", ["en", "fr"], "fr;q=0.9, en;q=0.5", None, "fr"),
            # No cookie + no Accept-Language → default
            ("en", ["en", "fr"], None, None, "en"),
            # Primary-subtag fallback (en-GB → en when only en is supported)
            ("en", ["en"], "en-GB;q=0.9, fr;q=0.5", None, "en"),
            # Empty supported list → return highest-quality user preference
            ("en", [], "ja;q=0.9, ko;q=0.7", None, "ja"),
        ],
        ids=[
            "cookie_wins_over_accept_language",
            "cookie_ignored_when_unsupported",
            "accept_language_used_when_no_cookie",
            "default_when_no_cookie_or_header",
            "primary_subtag_fallback",
            "empty_supported_list_passes_preference",
        ],
    )
    def test_resolve(
        self, make_request, default, supported, accept_language, locale_cookie, expected
    ) -> None:
        mw = self._middleware(default=default, supported=supported)
        kwargs: dict[str, str] = {}
        if accept_language is not None:
            kwargs["accept_language"] = accept_language
        if locale_cookie is not None:
            kwargs["locale_cookie"] = locale_cookie
        assert mw._resolve(make_request(**kwargs)) == expected

    def test_unsupported_default_normalised(self, make_request) -> None:
        """Garbage default falls back to `en` — defensive against
        malformed dazzle.toml [i18n] default values."""
        mw = self._middleware(default="!!!garbage!!!")
        assert mw._resolve(make_request()) == "en"


class TestGettextFilter:
    """The ``_()`` Jinja filter is identity-passthrough in cycle 1."""

    def test_passthrough_no_kwargs(self) -> None:
        from dazzle.render.filters import _gettext

        assert _gettext("Hello") == "Hello"

    def test_format_substitutes_kwargs(self) -> None:
        from dazzle.render.filters import _gettext

        assert _gettext("Hello {name}", name="world") == "Hello world"

    def test_malformed_format_returns_source(self) -> None:
        """Don't raise on malformed placeholders; cycle 2 will warn."""
        from dazzle.render.filters import _gettext

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
