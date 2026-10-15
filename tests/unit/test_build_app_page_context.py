"""#1392 item 2 P1 — build_app_page_context (the reusable app-shell nav/chrome
builder the route-override response-contract wrap consumes)."""

import asyncio
from types import SimpleNamespace
from typing import Any

import pytest

from dazzle.http.runtime.page_routes import build_app_page_context


def _app_state(**over: Any) -> SimpleNamespace:
    return SimpleNamespace(
        fragment_chrome_css_links=over.get("css", ("/x.css",)),
        fragment_chrome_js_scripts=over.get("js", ("/x.js",)),
        fragment_chrome_theme=over.get("theme", None),
        fragment_chrome_font_preconnect=over.get("fonts", ()),
        fragment_chrome_favicon=over.get("favicon", "/f.svg"),
    )


def _deps() -> Any:
    # Minimal _PageRouterConfig-shaped object: build_app_page_context only touches
    # .get_auth_context and .appspec (+ _resolve_nav_model reads precomputed navs,
    # unused on the anon/no-auth path).
    return SimpleNamespace(
        get_auth_context=None,
        appspec=SimpleNamespace(app_title="My App", name="myapp"),
        unrestricted_nav=None,
    )


def _build(app_state: Any) -> Any:
    request = SimpleNamespace(
        app=SimpleNamespace(state=app_state),
        state=SimpleNamespace(tenant_config={}),
    )
    return asyncio.run(build_app_page_context(request, deps=_deps(), current_route="/app/board"))


def test_build_app_page_context_anon() -> None:
    ctx, _assets = _build(_app_state())

    assert ctx.current_route == "/app/board"
    assert ctx.app_name == "My App"
    assert ctx.nav_model.groups == ()  # no auth context → explicit empty model
    assert ctx.nav_model.auto_discovered


@pytest.mark.parametrize(
    ("app_state", "css", "js", "favicon"),
    [
        pytest.param(_app_state(), ("/x.css",), ("/x.js",), "/f.svg", id="reads-app-state"),
        pytest.param(
            SimpleNamespace(),
            ("/static/dist/dazzle.min.css",),
            ("/static/dist/dazzle.min.js",),
            "/static/assets/dazzle-favicon.svg",
            id="framework-defaults-when-unset",
        ),
    ],
)
def test_build_app_page_context_chrome_assets(
    app_state: Any, css: tuple, js: tuple, favicon: str
) -> None:
    _ctx, assets = _build(app_state)

    assert (assets.css_links, assets.js_scripts, assets.favicon) == (css, js, favicon)
