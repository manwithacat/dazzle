"""#1798 U15 (AegisMark): a metrics / summary region's `action:` drills the WHOLE tile.

"12 stacks awaiting review" must open the queue it counts. `action:` already
parsed on any region but only ever reached list rows. A tile counts many rows,
so it drills to a set — a workspace or a list/create surface — never to a
row-id template, and the default entity-detail row drill never reaches tiles.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dazzle.core import ir
from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules
from dazzle.page.runtime.workspace_renderer import build_workspace_context
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer

_DSL = """module t
app t "T"

entity Doc "Doc":
  id: uuid pk
  title: str(100) required

surface doc_list "Docs":
  uses entity Doc
  mode: list
  section main:
    field title "Title"

surface doc_create "New Doc":
  uses entity Doc
  mode: create
  section main:
    field title "Title"

surface doc_detail "Doc":
  uses entity Doc
  mode: view
  section main:
    field title "Title"

workspace review_queue "Review queue":
  docs:
    source: Doc
    display: list

workspace board "Board":
  pulse:
    source: Doc
    display: metrics
{action}    aggregate:
      awaiting: count(Doc)
"""


def _appspec(action: str, tmp_path: Path) -> ir.AppSpec:
    dsl_dir = tmp_path / "dsl"
    dsl_dir.mkdir()
    line = f"    action: {action}\n" if action else ""
    (dsl_dir / "app.dsl").write_text(_DSL.replace("{action}", line))
    return build_appspec(parse_modules([dsl_dir / "app.dsl"]), "t")


def _pulse(appspec: ir.AppSpec) -> tuple[ir.WorkspaceRegion, object]:
    board = next(w for w in appspec.workspaces if w.name == "board")
    region_ctx = build_workspace_context(board, app_spec=appspec).regions[0]
    return board.regions[0], region_ctx


@pytest.mark.parametrize(
    ("action", "tile_drill"),
    [
        pytest.param("review_queue", "/app/workspaces/review_queue", id="workspace-no-context-id"),
        pytest.param("doc_list", "/app/doc", id="list-surface"),
        pytest.param("doc_create", "/app/doc/create", id="create-surface"),
        pytest.param("doc_detail", "", id="view-surface-has-no-row-id"),
        pytest.param("", "", id="no-action-default-row-drill-never-reaches-tiles"),
    ],
)
def test_region_action_resolves_tile_drill(action: str, tile_drill: str, tmp_path: Path) -> None:
    _, region_ctx = _pulse(_appspec(action, tmp_path))
    assert region_ctx.tile_drill_url == tile_drill  # type: ignore[attr-defined]
    # The row drill keeps its own resolution (default = entity detail).
    assert region_ctx.action_url  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("action", "present", "absent"),
    [
        pytest.param(
            "review_queue",
            (
                '<a class="dz-metric-tile" data-dz-metric-key="awaiting"',
                "data-dz-metric-drill",
                'href="/app/workspaces/review_queue" hx-get="/app/workspaces/review_queue" '
                'hx-push-url="true" hx-target="#main-content"',
                "</a>",
            ),
            ("context_id",),
            id="drillable-tile-is-a-link",
        ),
        pytest.param(
            "",
            ('<div class="dz-metric-tile" data-dz-metric-key="awaiting">',),
            ("<a ", "data-dz-metric-drill", "hx-get"),
            id="plain-tile-is-a-div",
        ),
    ],
)
def test_metric_tile_drill_markup(
    action: str, present: tuple[str, ...], absent: tuple[str, ...], tmp_path: Path
) -> None:
    region, region_ctx = _pulse(_appspec(action, tmp_path))
    html = FragmentRenderer().render(
        WorkspaceRegionAdapter().build(
            region,
            {
                "metrics": [{"label": "Awaiting", "value": 12}],
                "metrics_drill_url": region_ctx.tile_drill_url,  # type: ignore[attr-defined]
            },
        )
    )
    for fragment in present:
        assert fragment in html, html
    for fragment in absent:
        assert fragment not in html, html
