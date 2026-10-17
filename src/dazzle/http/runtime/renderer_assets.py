"""Mount and inject renderer-declared assets (#1132 → #1793).

A custom renderer declares its client files with ``assets() ->
list[RendererAsset]``. The framework:

- serves every declared file under
  ``/static/dazzle-renderers/<renderer>/<filename>`` (``renderer_asset_files``,
  mounted by ``system_routes`` before the catch-all ``/static``) — looked up
  by declaration, so nothing undeclared is ever reachable;
- links ``css`` assets in the chrome ``<head>`` and appends ``js`` assets to
  the chrome's deferred scripts (``inject_renderer_assets``, run from the
  server lifespan once every renderer is registered).

URLs come from the app's ``StaticFingerprinter`` (wired on
``RendererRegistry.fingerprinter``): content-hashed in production/staging,
plain in dev/test.
"""

import dataclasses
import logging
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, PlainTextResponse, Response
from starlette.routing import Route

from dazzle.http.runtime.static_files import static_cache_control
from dazzle.page.runtime.app_chrome import PROJECT_CUSTOM_CSS
from dazzle.page.runtime.asset_fingerprint import strip_fingerprint
from dazzle.render.fragment.registry import RendererAsset, RendererRegistry, asset_url

logger = logging.getLogger(__name__)


def _registry_of(app: Any) -> RendererRegistry | None:
    services = getattr(getattr(app, "state", None), "services", None)
    registry = getattr(services, "renderer_registry", None)
    return registry if isinstance(registry, RendererRegistry) else None


def renderer_asset_files(
    app: Any,
    *,
    active_development: bool = False,
    default_max_age: int | None = None,
) -> Starlette:
    """ASGI app serving ``<renderer>/<filename>`` from ``app``'s renderer registry.

    The registry is read per request (renderers register after the mounts
    exist). A hashed filename (``<stem>.<sha8><ext>``) is served ``immutable``;
    ``cache="no-store"`` assets ``no-store``; the rest at the static max-age.
    """

    async def serve(request: Request) -> Response:
        renderer = request.path_params["renderer"]
        filename = request.path_params["filename"]
        registry = _registry_of(app)
        if registry is None:
            return PlainTextResponse("Not Found", status_code=404)
        asset = registry.declared_asset(renderer, filename)
        if asset is None:
            original = strip_fingerprint(filename)
            asset = registry.declared_asset(renderer, original) if original else None
        if asset is None or not asset.path.is_file():
            return PlainTextResponse("Not Found", status_code=404)
        if asset.cache == "no-store" and not active_development:
            cache = "no-store"
        else:
            cache = static_cache_control(
                request.url.path,
                asset.path.suffix,
                active_development=active_development,
                default_max_age=default_max_age,
            )
        return FileResponse(asset.path, headers={"Cache-Control": cache})

    return Starlette(routes=[Route("/{renderer}/{filename}", serve, methods=["GET", "HEAD"])])


def _asset_url(registry: RendererRegistry, renderer_name: str, asset: RendererAsset) -> str:
    fp = registry.fingerprinter
    if fp is None:
        return asset_url(renderer_name, asset.path.name)
    return fp.renderer_asset_url(renderer_name, asset)


def _is_custom_css(url: str) -> bool:
    rel = url.removeprefix("/static/")
    return url == PROJECT_CUSTOM_CSS or f"/static/{strip_fingerprint(rel)}" == PROJECT_CUSTOM_CSS


def inject_renderer_assets(app: Any) -> int:
    """Link every registered renderer's declared ``css`` / ``js`` in the chrome.

    Runs once all renderers are registered (server lifespan). ``css`` lands
    before the project's ``custom.css`` (which must keep the last word), else
    at the end; ``js`` is appended. Deduplicated by resolved path and by URL,
    so a second call is a no-op. A declared file missing on disk is logged as
    an error and skipped — a renamed sheet never ships as a silent 404.

    Returns the number of URLs added.
    """
    registry = _registry_of(app)
    chrome = getattr(app.state, "fragment_chrome", None)
    if registry is None or chrome is None:
        return 0
    css_links = list(chrome.css_links)
    js_scripts = list(chrome.js_scripts)
    seen: set[Any] = set()
    added = 0
    for name, asset in registry.collect_assets():
        if asset.kind not in ("css", "js"):
            continue  # wasm / json are fetched by the renderer itself
        key = asset.path.resolve()
        if key in seen:
            continue
        seen.add(key)
        if not asset.path.is_file():
            logger.error(
                "[dazzle] renderer %r declares asset %s but the file does not exist — "
                "it will not be linked (#1793)",
                name,
                asset.path,
            )
            continue
        url = _asset_url(registry, name, asset)
        if url in css_links or url in js_scripts:
            continue
        if asset.kind == "js":
            js_scripts.append(url)
        else:
            custom_at = next((i for i, u in enumerate(css_links) if _is_custom_css(u)), None)
            css_links.insert(len(css_links) if custom_at is None else custom_at, url)
        added += 1
    if added:
        chrome = dataclasses.replace(
            chrome, css_links=tuple(css_links), js_scripts=tuple(js_scripts)
        )
        app.state.fragment_chrome = chrome
        app.state.fragment_chrome_css_links = chrome.css_links
        app.state.fragment_chrome_js_scripts = chrome.js_scripts
    return added
