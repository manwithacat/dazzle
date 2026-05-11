"""Server-side theme-variant resolution (UX-048 + UX-056 Q1).

Verifies the `dz_theme` cookie → `ThemeVariantMiddleware` → Jinja
`theme_variant()` global → `<html data-theme="…">` pipeline that
eliminates the flash-of-light for returning dark-mode users.

Run standalone:
    pytest tests/unit/test_theme_variant_middleware.py -v
"""

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from dazzle_ui.runtime.template_renderer import get_jinja_env
from dazzle_ui.runtime.theme import (
    COOKIE_NAME,
    DEFAULT_VARIANT,
    VALID_VARIANTS,
    ThemeVariantMiddleware,  # noqa: F401 — import check
    get_theme_variant,
    install_theme_middleware,
    theme_variant_ctxvar,
)


def _make_app() -> Starlette:
    async def _home(request: Request) -> PlainTextResponse:
        return PlainTextResponse(f"theme={get_theme_variant()}")

    app = Starlette(routes=[Route("/", _home)])
    install_theme_middleware(app)
    return app


# =============================================================================
# ContextVar defaults
# =============================================================================


def test_default_variant_is_light() -> None:
    """Called outside any request context (e.g. unit-test rendering
    paths that bypass middleware), `get_theme_variant()` must fall
    back to ``DEFAULT_VARIANT``."""
    assert get_theme_variant() == DEFAULT_VARIANT == "light"


def test_valid_variants_are_light_and_dark() -> None:
    """Keep the accepted-value set narrow. A future schema migration
    that adds a third variant MUST update this assertion AND the
    cookie-reading validation in the middleware."""
    assert VALID_VARIANTS == frozenset({"light", "dark"})


def test_ctxvar_roundtrip() -> None:
    """Manually setting and resetting the contextvar should produce
    the set value and then return to default."""
    token = theme_variant_ctxvar.set("dark")
    try:
        assert get_theme_variant() == "dark"
    finally:
        theme_variant_ctxvar.reset(token)
    assert get_theme_variant() == "light"


# =============================================================================
# Middleware behaviour over HTTP
# =============================================================================


def test_middleware_defaults_to_light_without_cookie() -> None:
    client = TestClient(_make_app())
    response = client.get("/")
    assert response.status_code == 200
    assert response.text == "theme=light"


@pytest.mark.parametrize(
    "cookie_value,expected_theme",
    [
        ("dark", "dark"),
        ("light", "light"),
        ("<script>alert(1)</script>", "light"),
        ("sepia", "light"),
    ],
    ids=[
        "test_middleware_reads_dark_cookie",
        "test_middleware_reads_light_cookie",
        "test_middleware_rejects_malformed_cookie",
        "test_middleware_rejects_unknown_variant",
    ],
)
def test_middleware_cookie_resolution(cookie_value: str, expected_theme: str) -> None:
    """Cookie values are validated against VALID_VARIANTS; unknown or
    malformed values fall back to the default variant."""
    client = TestClient(_make_app())
    response = client.get("/", cookies={COOKIE_NAME: cookie_value})
    assert response.text == f"theme={expected_theme}"


def test_ctxvar_resets_between_requests() -> None:
    """A request carrying `dark` must not leak its value into the
    next request that carries no cookie. Regression guard for the
    ``theme_variant_ctxvar.reset(token)`` call in the middleware's
    ``finally`` block."""
    client = TestClient(_make_app())
    r1 = client.get("/", cookies={COOKIE_NAME: "dark"})
    assert r1.text == "theme=dark"
    r2 = client.get("/")
    assert r2.text == "theme=light"


# =============================================================================
# Jinja global + template integration
# =============================================================================


def test_jinja_global_is_registered() -> None:
    env = get_jinja_env()
    assert "theme_variant" in env.globals
    assert callable(env.globals["theme_variant"])


@pytest.mark.skip(
    reason="v0.67.66 retired site/site_base.html — the typed Page primitive "
    "(dazzle.render.fragment.primitives.containers) owns the <html> shell and "
    "data-theme attribute. The `test_base_emits_theme_attribute_from_ctxvar` "
    "test below still covers the in-app base.html path."
)
def test_site_base_emits_theme_attribute_from_ctxvar() -> None: ...


def test_base_emits_theme_attribute_from_ctxvar() -> None:
    """base.html (the in-app shell's foundation) must render
    `<html data-theme="…">` from the current theme variant."""
    env = get_jinja_env()
    tmpl = env.get_template("base.html")

    html_light = tmpl.render(app_name="X", _dazzle_version="test", page_title="P")  # nosemgrep
    assert '<html lang="en" data-theme="light">' in html_light

    token = theme_variant_ctxvar.set("dark")
    try:
        html_dark = tmpl.render(app_name="X", _dazzle_version="test", page_title="P")  # nosemgrep
        assert '<html lang="en" data-theme="dark">' in html_dark
    finally:
        theme_variant_ctxvar.reset(token)


def test_htmx_partial_skips_html_wrapper() -> None:
    """base.html skips the <html> wrapper when ``_htmx_partial`` is
    true. The theme attribute is irrelevant in that branch. Regression
    guard to catch anyone who moves the `data-theme` emission outside
    the `_htmx_partial` guard and breaks HTMX fragment rendering."""
    env = get_jinja_env()
    tmpl = env.get_template("base.html")
    html = tmpl.render(  # nosemgrep: direct-use-of-jinja2
        app_name="X",
        _dazzle_version="test",
        page_title="P",
        _htmx_partial=True,
    )
    assert "<html" not in html
    assert "data-theme" not in html
