"""Leftover-honest catalog siblings (cycle 2185).

Tab / view / filter-enum leftover junk must not invent the first
declared sibling when rest is All / a later default. Valid catalog
ids still ride. Completes leftover_honest_catalog_id (oral #68) on
sibling pickers. Not leftover temporal echo (oral #67).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dazzle.http.runtime.page_routes import (
    _list_filter_enum_options,
    _parse_list_filter_enum_values,
    _parse_list_filters,
)
from dazzle.http.runtime.workspace_region_computes import compute_filter_columns_and_active
from dazzle.render.fragment.htmx import URL
from dazzle.render.fragment.primitives import LazyTab, LazyTabPanel, RelatedGroup, RelatedTab
from dazzle.render.fragment.renderer import FragmentRenderer
from dazzle.render.fragment.renderer._render_interactive import (
    leftover_honest_catalog_id,
    leftover_honest_catalog_option_values,
)

_HELPER = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "render"
    / "fragment"
    / "renderer"
    / "_render_interactive.py"
)
_TABLES = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "render"
    / "fragment"
    / "renderer"
    / "_render_tables.py"
)
_LAYOUT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "render"
    / "fragment"
    / "renderer"
    / "_render_layout.py"
)
_ORCH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "dazzle"
    / "http"
    / "runtime"
    / "workspace_region_orchestration.py"
)
_PAGE = (
    Path(__file__).resolve().parents[2] / "src" / "dazzle" / "http" / "runtime" / "page_routes.py"
)


def _tabs() -> tuple[RelatedTab, RelatedTab]:
    return (
        RelatedTab(tab_id="comments", label="Comments", headers=("Body",), rows=()),
        RelatedTab(tab_id="files", label="Files", headers=("Name",), rows=()),
    )


def test_helper_optional_catalog_does_not_invent_first() -> None:
    known = ("open", "closed")
    assert leftover_honest_catalog_id("closed", known, "", allow_empty_rest=True) == "closed"
    assert leftover_honest_catalog_id("ghost", known, "", allow_empty_rest=True) == ""
    assert leftover_honest_catalog_id("zzz", known, "", allow_empty_rest=True) == ""
    assert leftover_honest_catalog_id("", known, "", allow_empty_rest=True) == ""
    # required catalog still invents first when rest is empty
    assert leftover_honest_catalog_id("ghost", known, "") == "open"


def test_catalog_option_values_normalise_shapes() -> None:
    assert leftover_honest_catalog_option_values(["open", "closed"]) == ("open", "closed")
    assert leftover_honest_catalog_option_values(
        [{"value": "open", "label": "Open"}, {"value": "closed"}]
    ) == ("open", "closed")
    assert leftover_honest_catalog_option_values([("done", "Done")]) == ("done",)


def test_list_filter_enum_leftover_drops_junk() -> None:
    table = SimpleNamespace(
        columns=[
            SimpleNamespace(
                key="status",
                filter_options=[{"value": "open"}, {"value": "closed"}],
            )
        ]
    )
    parsed = _parse_list_filters(
        {"filter[status]": "ghost", "filter[title]": "Ada"},
        allowed=frozenset({"status", "title"}),
    )
    honest = _parse_list_filter_enum_values(parsed, _list_filter_enum_options(table))
    assert honest == {"title": "Ada"}
    valid = _parse_list_filter_enum_values(
        {"status": "closed", "title": "Ada"},
        _list_filter_enum_options(table),
    )
    assert valid == {"status": "closed", "title": "Ada"}


def test_workspace_filter_enum_leftover_drops_junk() -> None:
    columns = [
        {
            "key": "status",
            "label": "Status",
            "filterable": True,
            "filter_options": ["open", "closed"],
        }
    ]
    _, active = compute_filter_columns_and_active(
        columns, {"filter_status": "ghost", "filter_status_keep": "nope"}
    )
    assert "status" not in active
    _, valid = compute_filter_columns_and_active(columns, {"filter_status": "closed"})
    assert valid == {"status": "closed"}


def test_related_tab_valid_rides_later_sibling() -> None:
    html = FragmentRenderer().render(
        RelatedGroup(
            group_id="rel",
            label="Related",
            display="table",
            tabs=_tabs(),
            active_tab="files",
        )
    )
    assert 'data-dz-tab-target="dz-related-tab-files" aria-current="true"' in html.replace(
        "\n", " "
    ) or ('aria-current="true"' in html and "dz-related-tab-files" in html)
    files_idx = html.find("dz-related-tab-files")
    comments_btn = html.find("Comments")
    assert files_idx != -1
    # The files panel is visible; comments panel is hidden.
    comments_panel = html.find('id="dz-related-tab-comments"')
    files_panel = html.find('id="dz-related-tab-files"')
    assert comments_panel != -1 and files_panel != -1
    comments_chunk = html[comments_panel : comments_panel + 80]
    files_chunk = html[files_panel : files_panel + 80]
    assert " hidden" in comments_chunk
    assert " hidden" not in files_chunk
    assert comments_btn != -1


def test_related_tab_leftover_restores_first() -> None:
    html = FragmentRenderer().render(
        RelatedGroup(
            group_id="rel",
            label="Related",
            display="table",
            tabs=_tabs(),
            active_tab="ghost",
        )
    )
    comments_panel = html.find('id="dz-related-tab-comments"')
    files_panel = html.find('id="dz-related-tab-files"')
    comments_chunk = html[comments_panel : comments_panel + 80]
    files_chunk = html[files_panel : files_panel + 80]
    assert " hidden" not in comments_chunk
    assert " hidden" in files_chunk


def test_tabbed_list_valid_rides_later_sibling() -> None:
    html = FragmentRenderer().render(
        LazyTabPanel(
            region_name="issues",
            tabs=(
                LazyTab(key="open", label="Open", endpoint=URL("/open")),
                LazyTab(key="closed", label="Closed", endpoint=URL("/closed")),
            ),
            active_tab="closed",
        )
    )
    closed_panel = html.find('id="tab-issues-closed"')
    open_panel = html.find('id="tab-issues-open"')
    assert " hidden" not in html[closed_panel : closed_panel + 90]
    assert " hidden" in html[open_panel : open_panel + 90]
    assert 'hx-trigger="load"' in html[closed_panel : closed_panel + 160]


def test_tabbed_list_leftover_restores_first() -> None:
    html = FragmentRenderer().render(
        LazyTabPanel(
            region_name="issues",
            tabs=(
                LazyTab(key="open", label="Open", endpoint=URL("/open")),
                LazyTab(key="closed", label="Closed", endpoint=URL("/closed")),
            ),
            active_tab="ghost",
        )
    )
    open_panel = html.find('id="tab-issues-open"')
    closed_panel = html.find('id="tab-issues-closed"')
    assert " hidden" not in html[open_panel : open_panel + 90]
    assert " hidden" in html[closed_panel : closed_panel + 90]


def test_helper_source_pin() -> None:
    src = _HELPER.read_text(encoding="utf-8")
    assert "allow_empty_rest" in src
    assert "def leftover_honest_catalog_option_values(" in src


def test_contract_pins_catalog_leftover() -> None:
    root = Path(__file__).resolve().parents[2] / "packages" / "hatchi-maxchi" / "contracts"
    tabs = (root / "tabs.py").read_text(encoding="utf-8")
    related = (root / "related_group.py").read_text(encoding="utf-8")
    filters = (root / "filter_bar.py").read_text(encoding="utf-8")
    assert "leftover-honest catalog" in tabs.lower()
    assert "leftover-honest catalog" in related.lower()
    assert "leftover-honest catalog" in filters.lower()


def test_related_and_tabbed_source_pins() -> None:
    tables = _TABLES.read_text(encoding="utf-8")
    layout = _LAYOUT.read_text(encoding="utf-8")
    assert "leftover_honest_catalog_id" in tables
    assert "leftover_honest_catalog_id" in layout
    orch = _ORCH.read_text(encoding="utf-8")
    assert "leftover_honest_catalog_id" in orch
    page = _PAGE.read_text(encoding="utf-8")
    assert "_parse_list_filter_enum_values" in page
