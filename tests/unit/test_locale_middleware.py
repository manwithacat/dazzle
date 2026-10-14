"""Tests for the locale-resolution middleware (#955 cycle 1).

Pins:

  * cookie override > Accept-Language > default
  * Accept-Language quality weighting + supported-locale narrowing
  * primary-subtag fallback (en-GB → en when only "en" is supported)
  * empty supported list = "any locale OK" — pick highest-quality candidate
  * malformed inputs fall through cleanly (no crashes, no surprises)
  * the mounted middleware binds the tenant display profile (locale.* params)
    that date/datetime cells render with
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from starlette.requests import Request

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


# ---------------------------------------------------------------------------
# Display profile binding (flense ship AB): the mounted middleware carries the
# tenant's locale.* params to every date renderer.
# ---------------------------------------------------------------------------


def _locale_app(*, tenant_id: str | None, tenant_config: dict[str, str] | None = None) -> Any:
    """Tenancy stub (outer) -> LocaleMiddleware (inner) -> a route rendering cells,
    mirroring the server's stack order."""
    from datetime import UTC, date, datetime
    from types import SimpleNamespace

    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from starlette.middleware.base import BaseHTTPMiddleware

    from dazzle.core.ir.params import ParamSpec
    from dazzle.http.runtime.param_store import ParamResolver
    from dazzle.render.fragment.format_cell import format_cell
    from dazzle.render.fragment.region._shared import _render_typed_value

    app = FastAPI()
    specs = {
        "locale.date_format": ParamSpec(
            key="locale.date_format", param_type="str", default="D MMM YYYY", scope="tenant"
        ),
        "locale.timezone": ParamSpec(
            key="locale.timezone", param_type="str", default="Europe/London", scope="tenant"
        ),
    }
    resolver = ParamResolver(specs=specs)
    resolver.set_override("locale.date_format", "tenant", "t-us", "MM/DD/YYYY")
    resolver.set_override("locale.timezone", "tenant", "t-us", "America/New_York")
    app.state.param_resolver = resolver

    @app.get("/cells")
    async def cells(request: Request) -> JSONResponse:
        stamp = datetime(2026, 7, 16, 13, 30, tzinfo=UTC)
        workspace_cell = _render_typed_value(
            {"due": date(2026, 7, 16)}, {"key": "due", "type": "date"}
        )
        return JSONResponse(
            {
                "date": format_cell(date(2026, 7, 16), "date"),
                "datetime": format_cell(stamp, "datetime"),
                "workspace": str(getattr(workspace_cell, "html", workspace_cell)),
                "state_format": request.state.display_locale.date_format,
            }
        )

    app.add_middleware(LocaleMiddleware)

    async def _tenancy(request: Request, call_next: Any) -> Any:
        request.state.tenant = SimpleNamespace(id=tenant_id) if tenant_id else None
        request.state.tenant_config = tenant_config or {}
        return await call_next(request)

    app.add_middleware(BaseHTTPMiddleware, dispatch=_tenancy)
    return app


class TestDisplayProfileBinding:
    def test_tenant_param_override_reaches_rendered_cells(self) -> None:
        from fastapi.testclient import TestClient

        body = TestClient(_locale_app(tenant_id="t-us")).get("/cells").json()
        assert body["state_format"] == "MM/DD/YYYY"
        assert body["date"] == "07/16/2026"
        assert body["datetime"] == "07/16/2026 09:30"  # 13:30 UTC in New York
        assert "07/16/2026" in body["workspace"]

    def test_tenant_without_override_gets_dsl_default(self) -> None:
        from fastapi.testclient import TestClient

        body = TestClient(_locale_app(tenant_id="t-uk")).get("/cells").json()
        assert body["date"] == "16 Jul 2026"
        assert body["datetime"] == "16 Jul 2026 14:30"  # BST
        assert "16 Jul 2026" in body["workspace"]

    def test_profile_does_not_leak_past_the_request(self) -> None:
        from fastapi.testclient import TestClient

        from dazzle.i18n.display_locale import PRODUCT_DEFAULT_PROFILE, get_display_locale

        TestClient(_locale_app(tenant_id="t-us")).get("/cells")
        assert get_display_locale() == PRODUCT_DEFAULT_PROFILE

    def test_server_mounts_locale_middleware(self) -> None:
        from dazzle.http.runtime.server import DazzleBackendApp
        from tests.unit.test_build_server_config import _appspec

        builder = DazzleBackendApp(_appspec(), enable_auth=False)
        builder._create_app()
        assert builder._app is not None
        mounted = [getattr(mw, "cls", None) for mw in builder._app.user_middleware]
        assert LocaleMiddleware in mounted
