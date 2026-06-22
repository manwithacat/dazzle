"""#1137: ``RendererRegistry.asset_url`` honours ``cache="fingerprint"``.

The bare module-level ``asset_url(name, file)`` (registry-free) keeps
returning a bare URL. The new registry-aware
``RendererRegistry.asset_url(name, file, cache=...)`` looks up the
registered asset's on-disk path, hashes the contents, and appends
``?v=<8-hex>`` — so a new version of the file invalidates the
browser cache without operator intervention.
"""

from __future__ import annotations

import pathlib
import re

from dazzle.render.fragment import RendererAsset, RendererRegistry
from dazzle.render.fragment.registry import _content_hash


class _RendererWithAssets:
    def __init__(self, declared: list[RendererAsset]) -> None:
        self._declared = declared

    def render(self, surface, ctx) -> str:
        return "<x/>"

    def assets(self) -> list[RendererAsset]:
        return list(self._declared)


def _make_registry(
    tmp_path: pathlib.Path, contents: bytes = b"init();"
) -> tuple[RendererRegistry, pathlib.Path]:
    _content_hash.cache_clear()
    js = tmp_path / "init.js"
    js.write_bytes(contents)
    reg = RendererRegistry()
    reg.register(
        name="brand_analytics",
        handler=_RendererWithAssets([RendererAsset(path=js, kind="js", cache="fingerprint")]),
    )
    return reg, js


def test_asset_url_appends_content_hash_when_fingerprint(tmp_path) -> None:
    reg, _ = _make_registry(tmp_path)
    url = reg.asset_url("brand_analytics", "init.js")
    assert url.startswith("/static/dazzle-renderers/brand_analytics/init.js?v=")
    hash_part = url.rsplit("=", 1)[1]
    assert re.fullmatch(r"[0-9a-f]{8}", hash_part)


def test_hash_changes_when_file_contents_change(tmp_path) -> None:
    reg, js = _make_registry(tmp_path, b"a")
    url_a = reg.asset_url("brand_analytics", "init.js")
    _content_hash.cache_clear()
    js.write_bytes(b"b")
    url_b = reg.asset_url("brand_analytics", "init.js")
    assert url_a != url_b


def test_no_store_returns_bare_url(tmp_path) -> None:
    reg, _ = _make_registry(tmp_path)
    url = reg.asset_url("brand_analytics", "init.js", cache="no-store")
    assert url == "/static/dazzle-renderers/brand_analytics/init.js"


def test_immutable_returns_bare_url(tmp_path) -> None:
    """``immutable`` strategy emits the bare URL — the
    ``Cache-Control: immutable`` header is the auto-mount's job
    (future iteration). The cache-busting query string would defeat
    the point of immutable caching anyway."""
    reg, _ = _make_registry(tmp_path)
    url = reg.asset_url("brand_analytics", "init.js", cache="immutable")
    assert url == "/static/dazzle-renderers/brand_analytics/init.js"


def test_unknown_renderer_falls_back_to_bare_url(tmp_path) -> None:
    """A renderer not registered → can't hash → bare URL.
    Render must not hard-fail because of a missing registration."""
    _content_hash.cache_clear()
    reg = RendererRegistry()
    url = reg.asset_url("nonexistent", "init.js")
    assert url == "/static/dazzle-renderers/nonexistent/init.js"


def test_missing_file_falls_back_to_bare_url(tmp_path) -> None:
    """A registered asset whose file vanished → bare URL, no crash.
    Operator error, but page rendering keeps going."""
    _content_hash.cache_clear()
    js = tmp_path / "gone.js"
    js.write_bytes(b"x")
    reg = RendererRegistry()
    reg.register(
        name="r",
        handler=_RendererWithAssets([RendererAsset(path=js, kind="js")]),
    )
    js.unlink()
    url = reg.asset_url("r", "gone.js")
    assert url == "/static/dazzle-renderers/r/gone.js"


def test_hash_is_memoised(tmp_path, monkeypatch) -> None:
    """Second call for the same (renderer, filename) returns cached
    hash without re-reading the file. Verified by mutating the file
    between calls without clearing the cache: the URL must NOT change."""
    reg, js = _make_registry(tmp_path, b"original")
    url_1 = reg.asset_url("brand_analytics", "init.js")
    # Mutate without resetting the cache.
    js.write_bytes(b"different bytes")
    url_2 = reg.asset_url("brand_analytics", "init.js")
    assert url_1 == url_2


def test_filename_with_subpath_not_supported_yet(tmp_path) -> None:
    """``asset.path.name`` is the lookup key, so passing
    ``vendor/cytoscape.min.js`` to ``asset_url`` won't match a
    registered asset whose ``path.name`` is ``cytoscape.min.js``.
    Documents current behaviour — if subpath-aware lookup is needed,
    extend the registry's key format. Bare URL is the fallback,
    which is fine for static-mount scenarios."""
    _content_hash.cache_clear()
    reg = RendererRegistry()
    js = tmp_path / "lib.js"
    js.write_bytes(b"x")
    reg.register(
        name="g",
        handler=_RendererWithAssets([RendererAsset(path=js, kind="js")]),
    )
    url = reg.asset_url("g", "vendor/lib.js")
    # Falls back to bare URL because subpath lookup isn't supported.
    assert url == "/static/dazzle-renderers/g/vendor/lib.js"
