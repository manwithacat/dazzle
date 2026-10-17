"""#1793: renderer-declared css/js are linked in the chrome at boot.

``inject_renderer_assets`` runs from the server lifespan once every renderer
is registered: css lands before the project's ``custom.css`` (which keeps the
last word), js is appended, duplicates are dropped, the ``fragment_chrome_*``
slots follow, a second call is a no-op and a missing file is logged.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from dazzle.http.runtime.renderer_assets import inject_renderer_assets
from dazzle.page.runtime.app_chrome import AppChrome
from dazzle.render.fragment import RendererAsset, RendererRegistry

CUSTOM = "/static/css/custom.css"


class _R:
    def __init__(self, assets: list[RendererAsset]) -> None:
        self._assets = assets

    def render(self, surface: object, ctx: object) -> str:
        return ""

    def assets(self) -> list[RendererAsset]:
        return self._assets


@pytest.fixture
def app(tmp_path: Path) -> SimpleNamespace:
    css = tmp_path / "fastmark.css"
    css.write_text(".fm{}")
    js = tmp_path / "picker.js"
    js.write_text("pick();")
    registry = RendererRegistry()
    registry.register(
        name="fastmark",
        handler=_R(
            [
                RendererAsset(path=css, kind="css"),
                RendererAsset(path=js, kind="js"),
                RendererAsset(path=tmp_path / "gone.css", kind="css"),
            ]
        ),
    )
    # A second renderer sharing the same stylesheet — linked once.
    registry.register(name="other", handler=_R([RendererAsset(path=css, kind="css")]))
    chrome = AppChrome(css_links=("/static/dist/dazzle.min.css", CUSTOM))
    state = SimpleNamespace(
        services=SimpleNamespace(renderer_registry=registry),
        fragment_chrome=chrome,
        fragment_chrome_css_links=chrome.css_links,
        fragment_chrome_js_scripts=chrome.js_scripts,
    )
    return SimpleNamespace(state=state)


def test_injects_css_before_custom_and_appends_js(app, caplog) -> None:
    with caplog.at_level(logging.ERROR, logger="dazzle.http.runtime.renderer_assets"):
        added = inject_renderer_assets(app)
    assert added == 2
    links = app.state.fragment_chrome.css_links
    assert links == (
        "/static/dist/dazzle.min.css",
        "/static/dazzle-renderers/fastmark/fastmark.css",
        CUSTOM,
    )
    assert app.state.fragment_chrome.js_scripts[-1] == "/static/dazzle-renderers/fastmark/picker.js"
    assert app.state.fragment_chrome_css_links == links
    assert app.state.fragment_chrome_js_scripts == app.state.fragment_chrome.js_scripts
    assert "gone.css" in caplog.text
    # Idempotent: a second pass adds nothing.
    assert inject_renderer_assets(app) == 0
    assert app.state.fragment_chrome.css_links == links


async def test_server_lifespan_links_assets_of_a_hook_registered_renderer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end through ``DazzleBackendApp._lifespan``: a renderer registered
    by a project startup hook (after the chrome was resolved) gets its
    stylesheet linked, content-hashed in production."""
    from unittest.mock import MagicMock

    from dazzle.core import ir
    from dazzle.http.runtime.lifespan_hooks import register_lifespan_hook
    from dazzle.http.runtime.server import DazzleBackendApp, ServerConfig
    from dazzle.page.runtime.app_chrome import resolve_app_chrome
    from dazzle.page.runtime.asset_fingerprint import FINGERPRINT_RE, StaticFingerprinter

    monkeypatch.setenv("DAZZLE_ENV", "production")
    css = tmp_path / "fastmark.css"
    css.write_text(".fm{}")
    builder = DazzleBackendApp(
        ir.AppSpec(name="t", domain=ir.DomainSpec(entities=[])),
        config=ServerConfig(database_url="postgresql://example/test"),
    )
    builder._create_app()
    builder._db_manager = MagicMock()
    app = builder._app
    assert app is not None
    fp = StaticFingerprinter.for_project(None)
    app.state.services.renderer_registry.fingerprinter = fp
    chrome = resolve_app_chrome(None, fingerprinter=fp)  # what system_routes stashes
    app.state.fragment_chrome = chrome
    app.state.fragment_chrome_css_links = chrome.css_links

    def _register() -> None:
        app.state.services.renderer_registry.register(
            name="fastmark", handler=_R([RendererAsset(path=css, kind="css")])
        )

    register_lifespan_hook(app, startup=_register)
    async with app.router.lifespan_context(app):
        linked = app.state.fragment_chrome_css_links[-1]
    assert linked.startswith("/static/dazzle-renderers/fastmark/fastmark.")
    assert FINGERPRINT_RE.match(linked.rsplit("/", 1)[1])
