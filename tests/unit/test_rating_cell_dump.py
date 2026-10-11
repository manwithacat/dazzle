"""List/queue rating cells must not dump a bare integer (oral #172)."""

from __future__ import annotations

from dazzle.http.runtime.workspace_csv import _csv_cell
from dazzle.render.fragment.format_cell import format_cell
from dazzle.render.fragment.region._shared import _render_typed_value
from dazzle.render.fragment.renderer._data_row import _render_cell_display
from dazzle.render.rating_cell import (
    clerk_rating_cell_html,
    clerk_rating_display,
    clerk_rating_value,
    rating_field_name,
)


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
