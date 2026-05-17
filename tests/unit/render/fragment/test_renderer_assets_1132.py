"""#1132: ``RendererAsset`` + ``Renderer.assets()`` + ``RendererRegistry.collect_assets()``.

Three surfaces under test:

1. ``RendererAsset`` dataclass: frozen, validated path/kind shape.
2. ``RendererRegistry.collect_assets`` walks registered handlers and
   collects the ``(name, asset)`` pairs from any ``assets()`` they
   declare. Handlers without ``assets()`` are skipped (the method
   is optional on the Protocol).
3. ``asset_url(name, filename)`` returns the well-known framework
   URL convention every renderer's ``render()`` calls.
"""

from __future__ import annotations

import pathlib

import pytest

from dazzle.render.fragment import (
    RendererAsset,
    RendererRegistry,
    asset_url,
)

# ---------------------------------------------------------------------------
# RendererAsset dataclass shape
# ---------------------------------------------------------------------------


def test_renderer_asset_defaults() -> None:
    """``cache`` defaults to ``fingerprint``, ``where`` to ``head`` —
    the values production renderers want 99% of the time."""
    asset = RendererAsset(path=pathlib.Path("/x.js"), kind="js")
    assert asset.cache == "fingerprint"
    assert asset.where == "head"


def test_renderer_asset_is_frozen() -> None:
    a = RendererAsset(path=pathlib.Path("/x.js"), kind="js")
    with pytest.raises((AttributeError, Exception)):
        a.kind = "css"  # type: ignore[misc]


def test_renderer_asset_rejects_non_path() -> None:
    with pytest.raises(TypeError, match="RendererAsset.path expects pathlib.Path"):
        RendererAsset(path="/x.js", kind="js")  # type: ignore[arg-type]


def test_renderer_asset_rejects_invalid_kind() -> None:
    with pytest.raises(ValueError, match="RendererAsset.kind invalid"):
        RendererAsset(path=pathlib.Path("/x"), kind="bogus")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# RendererRegistry.collect_assets
# ---------------------------------------------------------------------------


class _RendererWithAssets:
    """Implements both Renderer.render and the optional assets()."""

    def __init__(self, declared: list[RendererAsset]) -> None:
        self._declared = declared

    def render(self, surface, ctx) -> str:
        return "<x/>"

    def assets(self) -> list[RendererAsset]:
        return list(self._declared)


class _RendererWithoutAssets:
    """Implements only Renderer.render — should be skipped cleanly."""

    def render(self, surface, ctx) -> str:
        return "<x/>"


def test_collect_assets_walks_handlers_with_assets_method() -> None:
    reg = RendererRegistry()
    a1 = RendererAsset(path=pathlib.Path("/a/x.js"), kind="js")
    a2 = RendererAsset(path=pathlib.Path("/a/x.css"), kind="css")
    reg.register(name="my_renderer", handler=_RendererWithAssets([a1, a2]))

    collected = reg.collect_assets()

    assert collected == [("my_renderer", a1), ("my_renderer", a2)]


def test_collect_assets_skips_handlers_without_assets_method() -> None:
    """A renderer that doesn't implement ``assets()`` is silently
    skipped — the method is optional on the Protocol so existing
    renderers stay compliant without an empty no-op."""
    reg = RendererRegistry()
    reg.register(name="bare", handler=_RendererWithoutAssets())
    assert reg.collect_assets() == []


def test_collect_assets_preserves_registration_order() -> None:
    """Asset URLs render in the order they're collected — so the
    declared order on each renderer + registration order across
    renderers must both be deterministic for reproducible chrome."""
    reg = RendererRegistry()
    a_b = RendererAsset(path=pathlib.Path("/b.js"), kind="js")
    a_a = RendererAsset(path=pathlib.Path("/a.js"), kind="js")
    reg.register(name="second", handler=_RendererWithAssets([a_b]))
    reg.register(name="first", handler=_RendererWithAssets([a_a]))

    names = [n for n, _ in reg.collect_assets()]
    assert names == ["second", "first"]


def test_collect_assets_raises_on_non_RendererAsset_entry() -> None:
    """A renderer that returns the wrong shape from assets() should
    fail loud, not silently — catching this at boot time is far
    better than a cryptic AttributeError mid-render."""

    class _BadRenderer:
        def render(self, surface, ctx):
            return ""

        def assets(self):
            return [{"path": "/x.js"}]  # dict, not RendererAsset

    reg = RendererRegistry()
    reg.register(name="bad", handler=_BadRenderer())

    with pytest.raises(TypeError, match="non-RendererAsset entry"):
        reg.collect_assets()


# ---------------------------------------------------------------------------
# asset_url — well-known URL helper
# ---------------------------------------------------------------------------


def test_asset_url_shape() -> None:
    assert asset_url("word_cloud", "wordcloud.js") == (
        "/static/dazzle-renderers/word_cloud/wordcloud.js"
    )


def test_asset_url_preserves_extension_and_subpath() -> None:
    assert asset_url("graph", "vendor/cytoscape.min.js") == (
        "/static/dazzle-renderers/graph/vendor/cytoscape.min.js"
    )
