"""Issue #1029 phase 5 (v0.66.137): regression tests for the LIST
adapter's search box + filter bar toolbar.

Pre-fix, list surfaces declaring `search:` or `filter:` blocks in
their `ux:` block rendered nothing — the toolbar primitives existed
but weren't wired into the LIST adapter. Fix: thread `search_enabled`,
`search_fields`, `filter_values`, and per-column `filter_options`
into ctx; adapter composes `SearchBox` (when search is configured)
and `FilterBar` (when any column is `filterable`) prepended to the
list region body."""

from __future__ import annotations

from typing import Any

import pytest

from dazzle.render.context import ColumnContext
from tests.unit.helpers.list_surface import contact_table, list_ctx, render_list

_NAME = ColumnContext(key="name", label="Name")
_STATUS = ColumnContext(
    key="status",
    label="Status",
    filterable=True,
    filter_type="select",
    filter_options=[
        {"value": "active", "label": "Active"},
        {"value": "archived", "label": "Archived"},
    ],
)
_ROWS = {"rows": [{"id": "1", "name": "Alice"}], "total": 1}


def test_dispatch_ctx_threads_search_and_filter_state() -> None:
    """`search_enabled`, `search_fields`, `filter_values` all reach the
    adapter; per-column `filter_options` flatten to (value, label) pairs."""
    ctx = list_ctx(
        contact_table(
            **_ROWS,
            columns=[_NAME, _STATUS],
            search_enabled=True,
            search_fields=["first_name", "last_name", "email"],
            filter_values={"status": "active"},
        )
    )
    assert ctx["search_enabled"] is True
    assert ctx["search_fields"] == ["first_name", "last_name", "email"]
    assert ctx["filter_values"] == {"status": "active"}
    assert ctx["columns"][1]["filterable"] is True
    assert ctx["columns"][1]["filter_options"] == [("active", "Active"), ("archived", "Archived")]


@pytest.mark.parametrize(
    ("surface", "expected"),
    [
        pytest.param(None, "contact_list", id="surface_name_not_dt_table_id_1205"),
        pytest.param(object(), "dt-device_list", id="falls_back_to_table_id_without_surface_name"),
    ],
)
def test_dispatch_ctx_region_name(surface: Any, expected: str) -> None:
    """#1205: `region_name` must match the workspace region container id
    (`region-<surface.name>`), not the renderer's `dt-`-prefixed `table_id`
    (the one-prefix mismatch fired htmx:targetError on every filter change).
    Without a surface name it falls back to `table_id` rather than an empty suffix."""
    ctx = list_ctx(contact_table(**_ROWS, table_id="dt-device_list"), surface)
    assert ctx["region_name"] == expected


@pytest.mark.parametrize(
    ("table", "present", "absent"),
    [
        pytest.param(
            {"search_enabled": True, "search_fields": ["first_name", "email"]},
            ["/_dazzle/fts/Contact", "dz-search-results-contact_list_search"],
            [],
            id="search_input_when_search_configured",
        ),
        pytest.param(
            {"search_enabled": False, "search_fields": []},
            [],
            ["/_dazzle/fts/"],
            id="no_search_input_when_search_disabled",
        ),
        pytest.param(
            {"search_enabled": True, "search_fields": []},
            [],
            ["/_dazzle/fts/"],
            id="no_search_input_when_search_fields_empty",
        ),
        pytest.param(
            {"columns": [_NAME, _STATUS]},
            ["dz-filter-bar", ">Active<", ">Archived<"],
            [],
            id="filter_bar_when_any_column_filterable",
        ),
        pytest.param(
            {"columns": [_NAME, _STATUS], "filter_values": {"status": "archived"}},
            ['value="archived" selected'],
            ['value="active" selected'],
            id="filter_bar_preselects_active_value",
        ),
        pytest.param(
            {"columns": [_NAME]},
            [],
            ["filter-bar"],
            id="no_filter_bar_without_filterable_columns",
        ),
        pytest.param(
            {"columns": [_STATUS], "api_endpoint": ""},
            [],
            ["filter-bar"],
            id="no_filter_bar_without_endpoint",
        ),
        pytest.param(
            {"columns": [_NAME, _STATUS], "table_id": "dt-contact_list"},
            ['name="filter[status]"', 'data-dz-grid-filter="filter[status]"'],
            ['hx-target="#contact_list-body"', "#region-"],
            id="filter_select_uses_grid_controller_seam_not_htmx_target",
        ),
    ],
)
def test_list_toolbar_render(table: dict[str, Any], present: list[str], absent: list[str]) -> None:
    """Convergence C1.1: filter controls carry the HM grid seam
    (`data-dz-grid-filter="filter[<key>]"`), never a per-control hx-target."""
    html = render_list(list_ctx(contact_table(**{**_ROWS, **table})))
    for fragment in present:
        assert fragment in html
    for fragment in absent:
        assert fragment not in html


def test_list_search_input_precedes_filter_bar() -> None:
    """Search and filter coexist; SearchBox renders before FilterBar."""
    html = render_list(
        list_ctx(
            contact_table(
                **_ROWS,
                search_enabled=True,
                search_fields=["name"],
                columns=[_STATUS],
                filter_values={},
            )
        )
    )
    search_pos = html.find("/_dazzle/fts/")
    filter_pos = html.find("dz-filter-bar")
    assert -1 < search_pos < filter_pos
