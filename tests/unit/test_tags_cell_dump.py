"""List/queue tag cells must not dump comma blobs (oral #171)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.runtime.workspace_columns import (
    build_surface_columns,
    field_kind_to_col_type,
)
from dazzle.http.runtime.workspace_csv import _csv_cell
from dazzle.render.fragment.region._shared import _render_typed_value
from dazzle.render.fragment.renderer._data_row import _render_cell_display
from dazzle.render.tags_cell import clerk_tags_cell_html, clerk_tags_join, clerk_tags_tokens


def _asset_tags_field():
    spec = load_project(Path("examples/design_studio"))
    asset = spec.get_entity("Asset")
    assert asset is not None
    tags = next(f for f in asset.fields if f.name == "tags")
    surface = next(s for s in spec.surfaces if s.name == "asset_list")
    return spec, asset, tags, surface


def _task_labels_field():
    spec = load_project(Path("examples/project_tracker"))
    task = spec.get_entity("Task")
    assert task is not None
    labels = next(f for f in task.fields if f.name == "labels")
    surface = next(s for s in spec.surfaces if s.name == "task_list")
    return spec, task, labels, surface


def test_asset_list_tags_are_tag_cells() -> None:
    spec, asset, tags, surface = _asset_tags_field()
    assert field_kind_to_col_type(tags, asset) == "tags"
    col = next(c for c in build_surface_columns(asset, surface, spec.enums) if c["key"] == "tags")
    assert col["type"] == "tags"


def test_task_list_labels_are_tag_cells() -> None:
    spec, task, labels, surface = _task_labels_field()
    assert field_kind_to_col_type(labels, task) == "tags"
    col = next(c for c in build_surface_columns(task, surface, spec.enums) if c["key"] == "labels")
    assert col["type"] == "tags"


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
