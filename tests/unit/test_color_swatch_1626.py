"""#1626 R5 / P0-8 — colour fields render as swatches, not bare hex text."""

from __future__ import annotations

from dazzle.render.cell_chrome import _render_color_swatch_html
from dazzle.render.fragment.renderer._data_row import _render_cell_display


def test_color_swatch_html_for_hex() -> None:
    html = _render_color_swatch_html("#336699")
    assert "data-dz-color-swatch" in html
    assert "background-color: #336699" in html
    assert "#336699" in html


def test_color_swatch_rejects_non_hex() -> None:
    assert _render_color_swatch_html("red") == "red"
    assert "background" not in _render_color_swatch_html("javascript:alert(1)")


def test_cell_display_color_type() -> None:
    html = _render_cell_display({"type": "color", "key": "primary_color"}, "#AABBCC")
    assert "dz-color-swatch" in html
