"""2b preload-drill — drilling is perceived-instant via htmx-4 preload (#1491).

Every clickable list row carries `hx-preload="mouseover"`, so the vendored
htmx-4 `preload` extension warms the detail GET on hover and the click serves
the cached prefetch. The extension is bundled into dazzle.min.js after the core.
"""

from __future__ import annotations

import pathlib

from dazzle.render.fragment.renderer._data_row import drill_row_attrs

_REPO = pathlib.Path(__file__).resolve().parents[2]
_VENDOR = _REPO / "src" / "dazzle" / "page" / "runtime" / "static" / "vendor"
_BUILD_DIST = _REPO / "scripts" / "build_dist.py"


def test_drill_row_wires_hover_preload() -> None:
    attrs = drill_row_attrs("/app/task/abc-123")
    # The htmx GET drill + a hover preload trigger → click serves the prefetch.
    assert 'hx-get="/app/task/abc-123"' in attrs
    assert 'hx-preload="mouseover"' in attrs
    assert 'hx-trigger="click"' in attrs


def test_non_clickable_row_has_no_preload() -> None:
    # An empty URL means the row isn't clickable — no drill, no preload.
    assert drill_row_attrs("") == ""


def test_preload_extension_is_vendored() -> None:
    assert (_VENDOR / "hx-preload.min.js").exists()
    body = (_VENDOR / "hx-preload.min.js").read_text(encoding="utf-8")
    assert 'registerExtension("preload"' in body


def test_preload_extension_is_bundled_after_core() -> None:
    # Order matters: the core must register htmx before the extension calls
    # htmx.registerExtension(...). Assert hx-preload follows htmx core in the
    # bundle source list (read as text — build_dist isn't an importable package).
    src = _BUILD_DIST.read_text(encoding="utf-8")
    assert '"hx-preload.min.js"' in src
    assert src.index('"htmx.min.js"') < src.index('"hx-preload.min.js"')
