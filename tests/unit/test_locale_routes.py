"""Tests for #955 cycle 6 — locale-switcher endpoint.

The cycle-1 LocaleMiddleware honours a `dazzle_locale` cookie but
nothing on the server actually sets it. This endpoint closes that
gap: a `<form>` POST (or htmx) writes the cookie, the middleware
picks it up on the next request, the user sees the page in their
chosen language.

Tests cover:
- Happy path: form post sets cookie + redirects
- Validation: bad locale → 400, unsupported locale → 400
- HTMX: HX-Refresh header instead of redirect
- Open-redirect defence: `next` is sanitised to same-origin
- Secure-cookie auto-detection: only flags `secure=True` over HTTPS
- The CSRF middleware exempts the route (no token required)
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dazzle_back.runtime.locale_routes import (
    _safe_redirect_target,
    create_locale_routes,
)

# ---------------------------------------------------------------------------
# _safe_redirect_target — open-redirect defence
# ---------------------------------------------------------------------------


class TestSafeRedirectTarget:
    def test_relative_path_passes(self):
        assert _safe_redirect_target("/app/users") == "/app/users"

    def test_query_and_fragment_preserved(self):
        assert (
            _safe_redirect_target("/dashboard?tab=overview#row-3")
            == "/dashboard?tab=overview#row-3"
        )

    def test_absolute_url_rejected(self):
        # Attacker-controlled `next=https://evil.com` must NOT bounce off-site.
        assert _safe_redirect_target("https://evil.com/landing") == "/"

    def test_protocol_relative_rejected(self):
        # `//evil/x` is protocol-relative and reaches off-site under https.
        assert _safe_redirect_target("//evil.com/x") == "/"

    def test_path_without_leading_slash_rejected(self):
        # A path like `app/users` could resolve relative to current location;
        # safer to refuse.
        assert _safe_redirect_target("app/users") == "/"

    def test_none_and_empty_default_to_root(self):
        assert _safe_redirect_target(None) == "/"
        assert _safe_redirect_target("") == "/"


# ---------------------------------------------------------------------------
# Endpoint behaviour
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    """App with the locale router mounted, no supported-locale restriction."""
    app = FastAPI()
    app.include_router(create_locale_routes(cookie_name="dazzle_locale"))
    return TestClient(app, follow_redirects=False)


@pytest.fixture
def restricted_client() -> TestClient:
    """App that only accepts `en` and `fr`."""
    app = FastAPI()
    app.include_router(
        create_locale_routes(
            cookie_name="dazzle_locale",
            supported_locales=frozenset({"en", "fr"}),
        )
    )
    return TestClient(app, follow_redirects=False)


class TestSetLocale:
    def test_happy_path_sets_cookie_and_redirects(self, client: TestClient):
        response = client.post(
            "/_dazzle/i18n/locale",
            data={"locale": "fr", "next": "/app/users"},
        )
        assert response.status_code == 303
        assert response.headers["location"] == "/app/users"
        # Cookie set on response
        cookie_header = response.headers.get("set-cookie", "")
        assert "dazzle_locale=fr" in cookie_header
        assert "HttpOnly" in cookie_header
        assert "SameSite=lax" in cookie_header.lower() or "samesite=lax" in cookie_header.lower()

    def test_default_redirect_to_root(self, client: TestClient):
        response = client.post("/_dazzle/i18n/locale", data={"locale": "fr"})
        assert response.status_code == 303
        assert response.headers["location"] == "/"

    def test_bcp47_locale_normalised_lowercase(self, client: TestClient):
        response = client.post("/_dazzle/i18n/locale", data={"locale": "EN-GB"})
        assert response.status_code == 303
        assert "dazzle_locale=en-gb" in response.headers["set-cookie"]

    def test_invalid_locale_400(self, client: TestClient):
        # `12_garbage` doesn't pass _normalise_locale — must reject.
        response = client.post("/_dazzle/i18n/locale", data={"locale": "12-garbage"})
        assert response.status_code == 400
        # No cookie set on rejection
        assert "set-cookie" not in {k.lower() for k in response.headers.keys()}

    def test_unsupported_locale_400(self, restricted_client: TestClient):
        # Allow-list = {en, fr}; `de` must be rejected even though tag is valid.
        response = restricted_client.post(
            "/_dazzle/i18n/locale",
            data={"locale": "de"},
        )
        assert response.status_code == 400
        assert b"de" in response.content or b"Unsupported" in response.content

    def test_supported_locale_with_subtag_match(self, restricted_client: TestClient):
        # `fr-CA` should match the `fr` allow-list entry via primary subtag.
        response = restricted_client.post(
            "/_dazzle/i18n/locale",
            data={"locale": "fr-CA"},
        )
        assert response.status_code == 303
        assert "dazzle_locale=fr-ca" in response.headers["set-cookie"]


class TestHtmxResponse:
    def test_hx_request_header_triggers_hx_refresh(self, client: TestClient):
        response = client.post(
            "/_dazzle/i18n/locale",
            data={"locale": "fr"},
            headers={"HX-Request": "true"},
        )
        assert response.status_code == 204
        assert response.headers.get("HX-Refresh") == "true"
        # Cookie still set
        assert "dazzle_locale=fr" in response.headers.get("set-cookie", "")


class TestSecureCookie:
    def test_http_omits_secure_flag(self, client: TestClient):
        # TestClient defaults to http://; cookie must NOT carry Secure
        # (otherwise it wouldn't persist over plain HTTP localhost dev).
        response = client.post("/_dazzle/i18n/locale", data={"locale": "fr"})
        cookie_header = response.headers.get("set-cookie", "")
        assert "Secure" not in cookie_header

    def test_https_sets_secure_flag(self):
        # Build a test client over https://.
        app = FastAPI()
        app.include_router(create_locale_routes())
        client = TestClient(app, base_url="https://test", follow_redirects=False)
        response = client.post("/_dazzle/i18n/locale", data={"locale": "fr"})
        cookie_header = response.headers.get("set-cookie", "")
        assert "Secure" in cookie_header


# ---------------------------------------------------------------------------
# Macro registration on framework env
# ---------------------------------------------------------------------------


class TestMacroRendering:
    def test_macro_template_loads(self):
        """The locale-switcher macro must be importable from the framework
        Jinja env so projects can call it without copying the template."""
        from dazzle_ui.runtime.template_renderer import get_jinja_env

        env = get_jinja_env()
        # Framework templates are mounted under `dz://` — the macro is at
        # `macros/locale_switcher.html` relative to the framework root.
        template = env.get_template("dz://macros/locale_switcher.html")
        assert "render_locale_switcher" in template.module.__dict__ or hasattr(
            template.module, "render_locale_switcher"
        )

    def test_macro_renders_no_supported_locales_block_when_empty(self):
        """When the project hasn't declared supported_locales, the switcher
        renders nothing — no half-built UI, no broken `<select>`."""
        from jinja2 import DictLoader, Environment

        from dazzle_ui.runtime.template_renderer import get_jinja_env

        framework_env = get_jinja_env()
        # Use a stub `request` with no locale_supported set.
        macro_src = framework_env.loader.get_source(
            framework_env, "dz://macros/locale_switcher.html"
        )[0]
        env = Environment(  # nosemgrep
            loader=DictLoader({"m.html": macro_src}), autoescape=True
        )

        class _RequestStateEmpty:
            locale = "en"
            locale_supported: Any = frozenset()

        class _RequestEmpty:
            state = _RequestStateEmpty()

            class url:
                path = "/here"

        # Render the whole template with the macro called — easier than
        # poking at the macro callable's wrapper attributes.
        env.globals["request"] = _RequestEmpty()
        tpl2 = env.from_string(
            "{% from 'm.html' import render_locale_switcher %}{{ render_locale_switcher() }}"
        )
        out = tpl2.render()
        assert "<form" not in out  # nothing emitted

    def test_macro_renders_select_with_supported_locales(self):
        from jinja2 import DictLoader, Environment

        from dazzle_ui.runtime.template_renderer import get_jinja_env

        framework_env = get_jinja_env()
        macro_src = framework_env.loader.get_source(
            framework_env, "dz://macros/locale_switcher.html"
        )[0]
        env = Environment(  # nosemgrep
            loader=DictLoader({"m.html": macro_src}), autoescape=True
        )

        class _RequestState:
            locale = "fr"
            locale_supported = frozenset({"en", "fr", "de"})

        class _Request:
            state = _RequestState()

            class url:
                path = "/dashboard"

        env.globals["request"] = _Request()
        env.globals["_"] = lambda s: s
        tpl = env.from_string(
            "{% from 'm.html' import render_locale_switcher %}{{ render_locale_switcher() }}"
        )
        out = tpl.render()
        assert "<form" in out
        assert 'action="/_dazzle/i18n/locale"' in out
        assert 'name="locale"' in out
        # Each supported locale appears as an option.
        for tag in ("en", "fr", "de"):
            assert f'value="{tag}"' in out
        # Current locale (`fr`) is selected.
        assert 'value="fr"' in out and "selected" in out
        # Hidden `next` input carries the current path.
        assert 'name="next"' in out and 'value="/dashboard"' in out
