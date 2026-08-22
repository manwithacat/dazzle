"""List/queue rating cells must not dump a bare integer (oral #172)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.runtime.workspace_columns import (
    build_surface_columns,
    field_kind_to_col_type,
)
from dazzle.http.runtime.workspace_csv import _csv_cell
from dazzle.page.converters.template_compiler import _field_type_to_column_type
from dazzle.render.fragment.format_cell import format_cell
from dazzle.render.fragment.region._shared import _render_typed_value
from dazzle.render.fragment.renderer._data_row import _render_cell_display
from dazzle.render.rating_cell import (
    clerk_rating_cell_html,
    clerk_rating_display,
    clerk_rating_value,
    rating_field_name,
)


def _feedback_rating_field():
    spec = load_project(Path("examples/design_studio"))
    feedback = spec.get_entity("Feedback")
    assert feedback is not None
    rating = next(f for f in feedback.fields if f.name == "rating")
    surface = next(s for s in spec.surfaces if s.name == "feedback_list")
    return spec, feedback, rating, surface


def _asset_quality_field():
    spec = load_project(Path("examples/design_studio"))
    asset = spec.get_entity("Asset")
    assert asset is not None
    quality = next(f for f in asset.fields if f.name == "quality_score")
    surface = next(s for s in spec.surfaces if s.name == "asset_list")
    return spec, asset, quality, surface


def test_feedback_list_rating_is_rating_cell() -> None:
    spec, feedback, rating, surface = _feedback_rating_field()
    assert rating_field_name("rating")
    assert field_kind_to_col_type(rating, feedback) == "rating"
    assert _field_type_to_column_type(rating, "rating") == "rating"
    col = next(
        c for c in build_surface_columns(feedback, surface, spec.enums) if c["key"] == "rating"
    )
    assert col["type"] == "rating"


def test_asset_list_quality_score_is_rating_cell() -> None:
    spec, asset, quality, surface = _asset_quality_field()
    assert rating_field_name("quality_score")
    assert field_kind_to_col_type(quality, asset) == "rating"
    assert _field_type_to_column_type(quality, "quality_score") == "rating"
    col = next(
        c for c in build_surface_columns(asset, surface, spec.enums) if c["key"] == "quality_score"
    )
    assert col["type"] == "rating"


def test_generic_score_is_not_a_rating_cell() -> None:
    assert not rating_field_name("confidence")
    assert not rating_field_name("skill_level")
    assert not rating_field_name("error_score")


def test_clerk_rating_split_leftover_and_empty() -> None:
    assert clerk_rating_value(4) == 4
    assert clerk_rating_value("5") == 5
    assert clerk_rating_value(0) is None
    assert clerk_rating_value(6) is None
    assert clerk_rating_value("zzz") is None
    assert clerk_rating_value("") is None
    assert clerk_rating_display(4) == "4/5"
    assert clerk_rating_display("zzz") == "zzz"
    assert clerk_rating_display("") == ""
    assert clerk_rating_display(100) == "100"
    assert format_cell(4, "rating") == "4/5"
    assert format_cell("zzz", "rating") == "zzz"


def test_list_html_renders_stars_not_bare_int() -> None:
    html = _render_cell_display({"key": "rating", "label": "Rating", "type": "rating"}, 4)
    assert "dz-rating" in html
    assert "4 out of 5" in html
    assert "★★★★" in html
    assert "☆" in html
    leftover = _render_cell_display({"key": "rating", "type": "rating"}, "zzz")
    assert "zzz" in leftover
    assert "dz-rating" not in leftover
    assert clerk_rating_cell_html("") == ""
    assert _render_cell_display({"key": "rating", "type": "rating"}, "") == "—"


def test_workspace_typed_value_renders_stars() -> None:
    frag = _render_typed_value(
        {"rating": 3},
        {"key": "rating", "label": "Rating", "type": "rating"},
    )
    html = getattr(frag, "html", str(frag))
    assert "dz-rating" in html
    assert "3 out of 5" in html
    leftover = _render_typed_value(
        {"rating": "zzz"},
        {"key": "rating", "type": "rating"},
    )
    leftover_html = getattr(leftover, "html", str(leftover))
    assert "zzz" in leftover_html
    assert "dz-rating" not in leftover_html


def test_csv_rating_is_over_max_not_bare_int() -> None:
    col = {"key": "rating", "label": "Rating", "type": "rating"}
    assert _csv_cell({"rating": 4}, col) == "4/5"
    assert _csv_cell({"rating": "zzz"}, col) == "zzz"
    assert _csv_cell({"rating": ""}, col) == ""
    quality = {"key": "quality_score", "label": "Quality", "type": "rating"}
    assert _csv_cell({"quality_score": 2}, quality) == "2/5"
