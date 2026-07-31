"""#1626 R5 / P0-8 — colour fields render as swatches, not bare hex text."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.appspec_loader import load_project_appspec
from dazzle.http.runtime.workspace_columns import build_surface_columns
from dazzle.render.fragment.renderer._data_row import (
    _render_cell_display,
    _render_color_swatch_html,
)


def test_color_swatch_html_for_hex() -> None:
    html = _render_color_swatch_html("#336699")
    assert 'data-dz-color-swatch' in html
    assert "background-color: #336699" in html
    assert "#336699" in html


def test_color_swatch_rejects_non_hex() -> None:
    assert _render_color_swatch_html("red") == "red"
    assert "background" not in _render_color_swatch_html("javascript:alert(1)")


def test_cell_display_color_type() -> None:
    html = _render_cell_display({"type": "color", "key": "primary_color"}, "#AABBCC")
    assert "dz-color-swatch" in html


def test_design_studio_brand_list_columns_are_color() -> None:
    spec = load_project_appspec(Path("examples/design_studio"))
    entity = next(e for e in spec.domain.entities if e.name == "Brand")
    surface = next(s for s in spec.surfaces if s.name == "brand_list")
    cols = build_surface_columns(entity, surface)
    by = {c["key"]: c["type"] for c in cols}
    assert by["primary_color"] == "color"
    assert by["secondary_color"] == "color"
    assert by["accent_color"] == "color"
