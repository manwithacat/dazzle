"""List/queue tag cells must not dump comma blobs (oral #171)."""

from __future__ import annotations

from dazzle.http.runtime.workspace_csv import _csv_cell
from dazzle.render.fragment.region._shared import _render_typed_value
from dazzle.render.fragment.renderer._data_row import _render_cell_display
from dazzle.render.tags_cell import clerk_tags_cell_html, clerk_tags_join, clerk_tags_tokens


def test_clerk_tags_split_leftover_and_empty() -> None:
    assert clerk_tags_tokens("brand, spring, logo") == ("brand", "spring", "logo")
    assert clerk_tags_tokens(["urgent", "backend"]) == ("urgent", "backend")
    assert clerk_tags_tokens("zzz") == ("zzz",)
    assert clerk_tags_tokens("") == ()
    assert clerk_tags_join(["brand", "spring"]) == "brand, spring"


def test_list_html_renders_chips_not_comma_blob() -> None:
    html = _render_cell_display(
        {"key": "tags", "label": "Tags", "type": "tags"},
        "brand,spring,logo",
    )
    assert "dz-tags-chip-label" in html
    assert "brand" in html
    assert "spring" in html
    assert "logo" in html
    assert "brand,spring,logo" not in html
    leftover = _render_cell_display({"key": "tags", "type": "tags"}, "zzz")
    assert "zzz" in leftover
    assert clerk_tags_cell_html("") == ""
    assert _render_cell_display({"key": "tags", "type": "tags"}, "") == "—"


def test_workspace_typed_value_renders_chips() -> None:
    frag = _render_typed_value(
        {"tags": "brand, spring"},
        {"key": "tags", "label": "Tags", "type": "tags"},
    )
    html = getattr(frag, "html", str(frag))
    assert "dz-tags-chip-label" in html
    assert "brand" in html
    assert "brand, spring" not in html
    empty = _render_typed_value({"tags": ""}, {"key": "tags", "type": "tags"})
    assert getattr(empty, "html", str(empty)) == "—"


def test_csv_tags_join_not_python_list() -> None:
    col = {"key": "tags", "label": "Tags", "type": "tags"}
    assert _csv_cell({"tags": "brand,spring"}, col) == "brand, spring"
    assert _csv_cell({"tags": ["brand", "spring"]}, col) == "brand, spring"
    assert _csv_cell({"tags": "zzz"}, col) == "zzz"
    assert _csv_cell({"tags": ""}, col) == ""
