"""Workspace bool FilterBar must not dump true/false (oral #146)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.runtime.workspace_columns import (
    _field_to_entity_column,
    bool_filter_options,
    build_surface_columns,
)
from dazzle.http.runtime.workspace_region_computes import compute_filter_columns_and_active
from dazzle.render.fragment import URL, FilterBar, FilterColumn, FragmentRenderer
from dazzle.render.fragment.format_cell import format_cell
from dazzle.render.fragment.renderer._render_interactive import leftover_honest_catalog_id


def test_bool_filter_options_are_yes_no() -> None:
    assert bool_filter_options() == [("true", "Yes"), ("false", "No")]
    assert format_cell(True, "bool") == "Yes"
    assert format_cell(False, "bool") == "No"


def test_contact_list_favorite_filter_is_yes_no() -> None:
    spec = load_project(Path("examples/contact_manager"))
    contact = spec.get_entity("Contact")
    assert contact is not None
    surf = next(s for s in spec.surfaces if s.name == "contact_list")
    cols = build_surface_columns(contact, surf, spec.enums)
    fav = next(c for c in cols if c["key"] == "is_favorite")
    assert fav["type"] == "bool"
    assert fav["filterable"] is True
    assert fav["filter_options"] == [("true", "Yes"), ("false", "No")]
    assert fav["filter_options"] != ["true", "false"]


def test_entity_bool_column_filter_is_yes_no() -> None:
    spec = load_project(Path("examples/contact_manager"))
    contact = spec.get_entity("Contact")
    assert contact is not None
    fav = next(f for f in contact.fields if f.name == "is_favorite")
    col = _field_to_entity_column(fav, contact, spec.enums)
    assert col is not None
    assert col["type"] == "bool"
    assert col["filter_options"] == [("true", "Yes"), ("false", "No")]


def test_bool_filter_query_values_stay_true_false() -> None:
    columns = [
        {
            "key": "is_favorite",
            "label": "Favorite",
            "filterable": True,
            "filter_options": bool_filter_options(),
        }
    ]
    _, active = compute_filter_columns_and_active(columns, {"filter_is_favorite": "true"})
    assert active["is_favorite"] == "true"
    _, leftover = compute_filter_columns_and_active(columns, {"filter_is_favorite": "zzz"})
    assert "is_favorite" not in leftover
    known = ("true", "false")
    assert leftover_honest_catalog_id("zzz", known, "", allow_empty_rest=True) == ""
    assert leftover_honest_catalog_id("true", known, "", allow_empty_rest=True) == "true"


def test_bool_filter_html_is_yes_no_not_true() -> None:
    html = FragmentRenderer().render(
        FilterBar(
            endpoint=URL("/app/contact"),
            region_name="contact_list",
            columns=(
                FilterColumn(
                    key="is_favorite",
                    label="Favorite",
                    options=tuple(bool_filter_options()),
                ),
            ),
        )
    )
    assert 'value="true"' in html
    assert ">Yes<" in html
    assert ">No<" in html
    assert ">true<" not in html
    assert ">false<" not in html


def test_bool_filter_leftover_html_stays_put() -> None:
    html = FragmentRenderer().render(
        FilterBar(
            endpoint=URL("/app/contact"),
            region_name="contact_list",
            columns=(
                FilterColumn(
                    key="is_favorite",
                    label="Favorite",
                    options=(("zzz", "zzz"), ("true", "Yes")),
                ),
            ),
        )
    )
    assert 'value="zzz"' in html
    assert ">zzz<" in html
    assert ">Yes<" in html
