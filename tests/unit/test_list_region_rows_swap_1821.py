"""#1821: a workspace list region's filter controls swap the rows, never the bar.

Before, the find-by box (and the filter selects) targeted the whole region and
the response re-rendered the bar with ``value=""`` — every keystroke lost the
box's focus, caret and text, and the page jumped. Now each control fetches
``part=rows`` into the ``[data-dz-list-region]`` that follows the bar, and the
region endpoint answers that request with the list alone.

Renders through the public region-render path (DSL → AppSpec → region →
``render_region_html``) with a request double carrying query params.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.datastructures import Headers, QueryParams

from dazzle.core import ir
from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.linker import build_appspec
from dazzle.http.runtime.workspace_region_render import RegionRenderInputs, render_region_html

_APP = """
module t
app t "T"

entity Stack "Stack":
  id: uuid pk
  title: str(200) required
  status: enum[draft,open]=draft

workspace desk "Desk":
  my_stacks:
    source: Stack
    display: list
"""


def _region() -> ir.WorkspaceRegion:
    *_, fragment = parse_dsl(_APP, Path("t.dsl"))
    module = ir.ModuleIR(name="t", file=Path("t.dsl"), fragment=fragment)
    return build_appspec([module], "t").workspaces[0].regions[0]


async def _render(query: str) -> str:
    region = _region()
    ctx = SimpleNamespace(
        ctx_region=SimpleNamespace(
            name="my_stacks",
            display="LIST",
            endpoint="/api/workspaces/desk/regions/my_stacks",
            empty_message=None,
        ),
        ir_region=region,
        source="Stack",
        entity_spec=None,
        search_fields=["title"],
        surface_empty_message=None,
    )
    request = SimpleNamespace(
        query_params=QueryParams(query), headers=Headers({"hx-request": "true"})
    )
    inputs = RegionRenderInputs(
        items=[{"id": "1", "title": "Y10 Geography", "status": "open"}],
        columns=[
            {"key": "title", "label": "Title", "type": "text"},
            {"key": "status", "label": "Status", "type": "text"},
        ],
        total=1,
        filter_columns=[
            {
                "key": "status",
                "label": "Status",
                "options": [("draft", "Draft"), ("open", "Open")],
            }
        ],
        active_filters={"status": "open"},
    )
    return await render_region_html(request, ctx, SimpleNamespace(), inputs, None, "asc")


@pytest.mark.asyncio
async def test_full_render_echoes_the_filters_and_every_control_targets_the_rows() -> None:
    html = await _render("q=Y10+Geo&filter_status=open")

    # The active search and select are visible in the re-rendered controls.
    assert 'name="q"' in html and 'value="Y10 Geo"' in html
    assert 'value="open" selected>' in html
    # Every filter control swaps the list that follows its bar — never the
    # region (which would re-render, and so reset, the bar itself).
    targets = re.findall(r'hx-target="([^"]*)"', html)
    assert targets.count("next [data-dz-list-region]") == 2  # find-by box + select
    assert "closest [data-dz-region]" not in targets
    assert html.count("?part=rows") == 2
    # The bars come before (outside) the swapped list, and a clear control
    # sits beside the box.
    assert html.index("data-dz-list-filters") < html.index("data-dz-list-region")
    assert "data-dz-list-search-clear" in html


@pytest.mark.asyncio
async def test_rows_request_returns_the_list_without_the_filter_bar() -> None:
    html = await _render("part=rows&q=Y10&filter_status=open")

    assert html.startswith('<div class="dz-list-region"')
    assert "Y10 Geography" in html
    for chrome in ("data-dz-list-filters", "dz-list-q-", 'name="q"', "filter_status"):
        assert chrome not in html, chrome
