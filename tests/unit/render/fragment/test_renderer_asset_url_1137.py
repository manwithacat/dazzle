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

import pytest

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


def _registered(tmp_path: pathlib.Path) -> tuple[RendererRegistry, str, str]:
    reg, _ = _make_registry(tmp_path)
    return reg, "brand_analytics", "init.js"


def _unregistered(tmp_path: pathlib.Path) -> tuple[RendererRegistry, str, str]:
    _content_hash.cache_clear()
    return RendererRegistry(), "nonexistent", "init.js"


def _file_vanished(tmp_path: pathlib.Path) -> tuple[RendererRegistry, str, str]:
    _content_hash.cache_clear()
    js = tmp_path / "gone.js"
    js.write_bytes(b"x")
    reg = RendererRegistry()
    reg.register(name="r", handler=_RendererWithAssets([RendererAsset(path=js, kind="js")]))
    js.unlink()
    return reg, "r", "gone.js"


def _subpath_lookup(tmp_path: pathlib.Path) -> tuple[RendererRegistry, str, str]:
    _content_hash.cache_clear()
    js = tmp_path / "lib.js"
    js.write_bytes(b"x")
    reg = RendererRegistry()
    reg.register(name="g", handler=_RendererWithAssets([RendererAsset(path=js, kind="js")]))
    return reg, "g", "vendor/lib.js"


@pytest.mark.parametrize(
    ("setup", "cache", "expected"),
    [
        pytest.param(
            _registered,
            "no-store",
            "/static/dazzle-renderers/brand_analytics/init.js",
            id="no-store-strategy",
        ),
        # `immutable` relies on the Cache-Control header (the auto-mount's job);
        # a cache-busting query string would defeat immutable caching.
        pytest.param(
            _registered,
            "immutable",
            "/static/dazzle-renderers/brand_analytics/init.js",
            id="immutable-strategy",
        ),
        # Unregistered renderer → can't hash; render must not hard-fail.
        pytest.param(
            _unregistered,
            None,
            "/static/dazzle-renderers/nonexistent/init.js",
            id="unknown-renderer",
        ),
        # Registered asset whose file vanished → operator error, page keeps going.
        pytest.param(_file_vanished, None, "/static/dazzle-renderers/r/gone.js", id="missing-file"),
        # `asset.path.name` is the lookup key, so a subpath doesn't match;
        # documents current behaviour (extend the key format if needed).
        pytest.param(
            _subpath_lookup,
            None,
            "/static/dazzle-renderers/g/vendor/lib.js",
            id="subpath-not-supported-yet",
        ),
    ],
)
def test_asset_url_falls_back_to_bare_url(tmp_path, setup, cache, expected) -> None:
    reg, name, filename = setup(tmp_path)
    kwargs = {"cache": cache} if cache else {}
    assert reg.asset_url(name, filename, **kwargs) == expected


def test_hash_is_memoised(tmp_path) -> None:
    """Second call for the same (renderer, filename) returns cached
    hash without re-reading the file. Verified by mutating the file
    between calls without clearing the cache: the URL must NOT change."""
    reg, js = _make_registry(tmp_path, b"original")
    url_1 = reg.asset_url("brand_analytics", "init.js")
    js.write_bytes(b"different bytes")
    url_2 = reg.asset_url("brand_analytics", "init.js")
    assert url_1 == url_2
