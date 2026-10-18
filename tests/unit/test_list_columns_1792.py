"""#1792 — one column grammar for regions and list surfaces, plus `page_size:`.

Region ``columns: title(width: 34%), owner(truncate), status`` and a list
surface's ``field title "Title" width: 34%`` both produce ``ir.ColumnSpec`` data
and render through the same column path. ``page_size:`` sets the rows per page.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.core.linker import build_appspec
from dazzle.core.lint import lint_appspec
from dazzle.http.runtime.dispatch_ctx import _build_dispatch_ctx
from dazzle.http.runtime.handlers.list_handlers import build_data_table
from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
from dazzle.http.runtime.workspace_columns import build_region_columns, build_surface_columns
from dazzle.page.converters.template_compiler import compile_surface_to_context
from dazzle.render.fragment import FragmentRenderer
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer._data_row import render_data_table_rows

_HEAD = """module t
app t "T"

entity Owner "Owner":
  id: uuid pk
  name: str(100) required

entity Stack "Stack":
  id: uuid pk
  title: str(200) required
  status: enum[draft, marked]=draft
  photo_url: str(500)
  owner: ref Owner
"""

_APP = (
    _HEAD
    + """
surface stack_list "Stacks":
  uses entity Stack
  mode: list
  page_size: 25
  section main:
    field title "Title" width: 34%
    field owner "Owner" truncate: false
    field status "Status" truncate

workspace desk "Desk":
  stacks:
    source: Stack
    display: list
    columns: title(width: 34%), photo_url, status(width: 8rem, truncate: false), owner(truncate)
    page_size: 25
"""
)


def _appspec(text: str) -> ir.AppSpec:
    *_, fragment = parse_dsl(text, Path("t.dsl"))
    module = ir.ModuleIR(name="t", file=Path("t.dsl"), fragment=fragment)
    return build_appspec([module], "t")


def test_region_and_surface_produce_the_same_column_specs() -> None:
    spec = _appspec(_APP)
    region = spec.workspaces[0].regions[0]
    surface = spec.get_surface("stack_list")
    assert surface is not None

    assert region.page_size == 25 and surface.page_size == 25
    assert region.columns == [
        ir.ColumnSpec(field="title", width="34%"),
        ir.ColumnSpec(field="photo_url"),
        ir.ColumnSpec(field="status", width="8rem", truncate=False),
        ir.ColumnSpec(field="owner", truncate=True),
    ]
    assert surface.list_columns() == [
        ir.ColumnSpec(field="title", width="34%"),
        ir.ColumnSpec(field="owner", truncate=False),
        ir.ColumnSpec(field="status", truncate=True),
    ]


@pytest.mark.parametrize(
    ("snippet", "message"),
    [
        ("columns: title(width: 34px)", "must be a number followed by"),
        ("columns: title(width: 120%)", "cannot exceed 100%"),
        ("columns: owner.name", "dotted paths are not supported"),
        ("columns: title(wrap)", "Unknown column modifier"),
        ("page_size: 0", "page_size must be a whole number from 1 to 100"),
        ("page_size: 101", "page_size must be a whole number from 1 to 100"),
    ],
)
def test_region_column_grammar_rejects_bad_values(snippet: str, message: str) -> None:
    text = _HEAD + f'\nworkspace desk "Desk":\n  stacks:\n    source: Stack\n    {snippet}\n'
    with pytest.raises(ParseError, match=message):
        parse_dsl(text, Path("t.dsl"))


@pytest.mark.parametrize(
    ("region_body", "code"),
    [
        ("columns: title, headline", "E_COLUMNS_UNKNOWN_FIELD"),
        ("columns: title, status, title", "E_COLUMNS_DUPLICATE"),
        ("limit: 10\n    page_size: 25", "E_REGION_PAGE_SIZE_LIMIT"),
    ],
)
def test_validator_rejects_bad_region_columns(region_body: str, code: str) -> None:
    text = (
        _HEAD
        + '\nworkspace desk "Desk":\n  stacks:\n    source: Stack\n    display: list\n'
        + f"    {region_body}\n"
    )
    errors, _warnings, _ = lint_appspec(_appspec(text))
    assert any(code in e for e in errors), errors


def test_region_list_renders_only_named_columns_in_order_with_widths() -> None:
    spec = _appspec(_APP)
    region = spec.workspaces[0].regions[0]
    entity = spec.get_entity("Stack")
    columns = build_region_columns(entity, region.columns)

    # Order authoritative; the named image field is opted back in on a list.
    assert [c["key"] for c in columns] == ["title", "photo_url", "status", "owner"]
    items = [
        {
            "id": f"00000000-0000-0000-0000-0000000000{i:02d}",
            "title": f"Stack {i:02d}",
            "photo_url": "",
            "status": "draft",
            "owner": None,
        }
        for i in range(25)
    ]
    ctx = {
        "items": items,
        "columns": columns,
        "total": 40,
        "page": 1,
        "page_size": 25,
        "endpoint": "/api/workspaces/desk/regions/stacks",
        "region_name": "stacks",
    }
    html = FragmentRenderer().render(WorkspaceRegionAdapter().build(region, ctx))

    assert (
        '<colgroup><col data-dz-col="title" style="width: 34%">'
        '<col data-dz-col="photo_url">'
        '<col data-dz-col="status" style="width: 8rem">'
        '<col data-dz-col="owner"></colgroup>'
    ) in html
    assert 'style="table-layout: fixed"' in html
    # 40 matches at 25 per page → a pager whose buttons re-fetch the rows
    # (#1821: `part=rows`, swapped over the list itself).
    assert "data-dz-pagination" in html
    assert "/api/workspaces/desk/regions/stacks?part=rows&amp;page=2&amp;page_size=25" in html


def test_list_surface_field_width_and_page_size_reach_the_list_page() -> None:
    spec = _appspec(_APP)
    surface = spec.get_surface("stack_list")
    assert surface is not None
    page_ctx = compile_surface_to_context(surface, spec.get_entity("Stack"))
    dispatch = _build_dispatch_ctx(page_ctx, surface)
    html = FragmentRenderer().render(FragmentSurfaceAdapter().build(surface, dispatch))

    assert '<col data-dz-col="title" style="width: 34%">' in html
    assert '<th data-dz-col="title" style="width: 34%"' in html
    # #1822: partial hints — unhinted columns stay style-less (the HM
    # `col:not([style])` floor targets them) and every header carries its full
    # label in title= so a clipped header stays readable.
    assert '<col data-dz-col="owner">' in html
    assert 'scope="col" title="Owner" class="dz-table-th"' in html
    # The declared page size rides the first fetch and every grid refresh.
    assert "page_size=25" in html.split("data-dz-grid-src=", 1)[1].split('"')[1]
    assert '<input type="hidden" data-dz-grid-page-size value="25">' in html


def test_list_rows_honour_the_truncate_opt_out() -> None:
    spec = _appspec(
        _HEAD
        + """
surface stack_list "Stacks":
  uses entity Stack
  mode: list
  section main:
    field title "Title" truncate: false
    field photo_url "Photo"
"""
    )
    columns = build_surface_columns(spec.get_entity("Stack"), spec.get_surface("stack_list"))
    long_title = "AQA GCSE English Literature Paper 1 Section A — Macbeth, extract question"
    item = {"id": "00000000-0000-0000-0000-000000000001", "title": long_title, "photo_url": "x"}
    rows = render_data_table_rows(
        build_data_table({"columns": columns, "table_id": "stack_list"}, [item])
    )

    # `truncate: false` → the title renders whole instead of clipped to 50 chars.
    assert long_title in rows
    assert '<span class="dz-tr-cell-truncate">AQA GCSE' not in rows
