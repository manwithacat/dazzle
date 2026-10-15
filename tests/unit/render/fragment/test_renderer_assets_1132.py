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


_JS_X = RendererAsset(path=pathlib.Path("/a/x.js"), kind="js")
_CSS_X = RendererAsset(path=pathlib.Path("/a/x.css"), kind="css")
_JS_A = RendererAsset(path=pathlib.Path("/a.js"), kind="js")
_JS_B = RendererAsset(path=pathlib.Path("/b.js"), kind="js")


@pytest.mark.parametrize(
    ("registrations", "expected"),
    [
        pytest.param(
            [("my_renderer", [_JS_X, _CSS_X])],
            [("my_renderer", _JS_X), ("my_renderer", _CSS_X)],
            id="walks-handlers-with-assets-method",
        ),
        # `assets()` is optional on the Protocol: renderers without it are
        # skipped, so existing renderers stay compliant without a no-op.
        pytest.param([("bare", None)], [], id="skips-handlers-without-assets-method"),
        # Declared order per renderer + registration order across renderers are
        # both deterministic, so the emitted chrome is reproducible.
        pytest.param(
            [("second", [_JS_B]), ("first", [_JS_A])],
            [("second", _JS_B), ("first", _JS_A)],
            id="preserves-registration-order",
        ),
    ],
)
def test_collect_assets(
    registrations: list[tuple[str, list[RendererAsset] | None]],
    expected: list[tuple[str, RendererAsset]],
) -> None:
    reg = RendererRegistry()
    for name, assets in registrations:
        handler = _RendererWithoutAssets() if assets is None else _RendererWithAssets(assets)
        reg.register(name=name, handler=handler)
    assert reg.collect_assets() == expected


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


@pytest.mark.parametrize(
    ("name", "filename", "expected"),
    [
        pytest.param(
            "word_cloud",
            "wordcloud.js",
            "/static/dazzle-renderers/word_cloud/wordcloud.js",
            id="bare-filename",
        ),
        pytest.param(
            "graph",
            "vendor/cytoscape.min.js",
            "/static/dazzle-renderers/graph/vendor/cytoscape.min.js",
            id="preserves-extension-and-subpath",
        ),
    ],
)
def test_asset_url(name: str, filename: str, expected: str) -> None:
    assert asset_url(name, filename) == expected
