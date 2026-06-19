"""#1392 item 2 P1 — build_app_page_context + _resolve_chrome_assets (the reusable
app-shell nav/chrome builder the route-override response-contract wrap consumes)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from dazzle.ui.runtime.page_routes import (
    _ChromeAssets,
    _resolve_chrome_assets,
    build_app_page_context,
)


def _app_state(**over: Any) -> SimpleNamespace:
    return SimpleNamespace(
        fragment_chrome_css_links=over.get("css", ("/x.css",)),
        fragment_chrome_js_scripts=over.get("js", ("/x.js",)),
        fragment_chrome_theme=over.get("theme", None),
        fragment_chrome_font_preconnect=over.get("fonts", ()),
        fragment_chrome_favicon=over.get("favicon", "/f.svg"),
    )


def test_resolve_chrome_assets_reads_app_state() -> None:
    a = _resolve_chrome_assets(_app_state())
    assert isinstance(a, _ChromeAssets)
    assert a.css_links == ("/x.css",) and a.js_scripts == ("/x.js",) and a.favicon == "/f.svg"


def test_resolve_chrome_assets_defaults_when_unset() -> None:
    a = _resolve_chrome_assets(SimpleNamespace())
    assert a.css_links == ("/static/dist/dazzle.min.css",)
    assert a.favicon == "/static/assets/dazzle-favicon.svg"


def _deps() -> Any:
    # Minimal _PageRouterConfig-shaped object: build_app_page_context only touches
    # .get_auth_context and .appspec (+ _resolve_nav_model reads precomputed navs,
    # unused on the anon/no-auth path).
    return SimpleNamespace(
        get_auth_context=None,
        appspec=SimpleNamespace(app_title="My App", name="myapp"),
    )


def test_build_app_page_context_anon() -> None:
    request = SimpleNamespace(
        app=SimpleNamespace(state=_app_state()),
        state=SimpleNamespace(tenant_config={}),
    )
    ctx, assets = asyncio.run(
        build_app_page_context(request, deps=_deps(), current_route="/app/board")
    )
    assert ctx.current_route == "/app/board"
    assert ctx.app_name == "My App"
    assert ctx.nav_model is None  # no auth context → anon/no-nav-model path
    assert assets.css_links == ("/x.css",)
