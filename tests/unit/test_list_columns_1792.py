"""#1792 list-column defects, rendered through the public path (DSL → AppSpec → HTML).

U18 — a ``ref`` cell under the fixed-layout data table carries the same
``dz-tr-cell-truncate`` wrapper as a text cell, with the full display name in
``title=``, so a long name ellipsizes instead of wrapping the row.

U5 — image/file fields are auto-derived into a region's columns only for
card-like displays (``grid`` / ``kanban``); a ``list`` / ``queue`` /
``status_list`` / ``timeline`` region shows them only when the author names them.
"""

from __future__ import annotations

import pytest

from dazzle.core.linker import build_appspec
from dazzle.core.parser import parse_modules
from dazzle.http.runtime.handlers.list_handlers import build_data_table
from dazzle.http.runtime.workspace_columns import (
    build_entity_columns,
    build_surface_columns,
    media_thumbs_for_display,
)
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer
from dazzle.render.fragment.renderer._data_row import render_data_table_rows

_PHOTO = "https://placehold.co/64x64/111111/FFFFFF/png?text=A"
_LONG_TITLE = "AQA GCSE English Literature Paper 1 Section A — Macbeth"

_DSL = """module t
app t "T"

entity MarkScheme "Mark Scheme":
  id: uuid pk
  title: str(300) required

entity Stack "Stack":
  id: uuid pk
  title: str(200) required
  mark_scheme: ref MarkScheme

entity Pupil "Pupil":
  id: uuid pk
  surname: str(100) required
  forename: str(100) required
  photo_url: str(1000)
  year_group: str(10)

  fitness:
    repr_fields: [surname, forename, year_group]

entity Upload "Upload":
  id: uuid pk
  name: str(200) required
  attachment: file

surface stack_list "Stacks":
  uses entity Stack
  mode: list
  section main:
    field title "Title"
    field mark_scheme "Mark Scheme"

workspace desk "Desk":
  pupils_list:
    source: Pupil
    display: list
  pupils_queue:
    source: Pupil
    display: queue
  pupils_status:
    source: Pupil
    display: status_list
  pupils_grid:
    source: Pupil
    display: grid
  pupils_kanban:
    source: Pupil
    display: kanban
    group_by: year_group
  uploads_list:
    source: Upload
    display: list
  uploads_grid:
    source: Upload
    display: grid
"""


@pytest.fixture(scope="module")
def appspec(tmp_path_factory: pytest.TempPathFactory):
    dsl_dir = tmp_path_factory.mktemp("dsl1792")
    (dsl_dir / "app.dsl").write_text(_DSL, encoding="utf-8")
    return build_appspec(parse_modules([dsl_dir / "app.dsl"]), "t")


def _entity(appspec, name: str):
    return next(e for e in appspec.domain.entities if e.name == name)


def _region(appspec, name: str):
    ws = next(w for w in appspec.workspaces if w.name == "desk")
    return next(r for r in ws.regions if r.name == name)


def _region_columns(appspec, region_name: str) -> list[dict]:
    """The column derivation the workspace route builder applies to a region."""
    region = _region(appspec, region_name)
    return build_entity_columns(
        _entity(appspec, region.source),
        media_thumbs=media_thumbs_for_display(region.display),
    )


def test_ref_cell_carries_truncate_wrapper_and_full_title(appspec) -> None:
    """U18: a long ref display name sits in the text-cell truncate wrapper."""
    entity = _entity(appspec, "Stack")
    surface = next(s for s in appspec.surfaces if s.name == "stack_list")
    table = {
        "columns": build_surface_columns(entity, surface),
        "entity_name": "Stack",
        "api_endpoint": "/stacks",
        "table_id": "dt-stack_list",
    }
    item = {
        "id": "s1",
        "title": "Macbeth mock",
        "mark_scheme": {"id": "ms1", "title": _LONG_TITLE},
        "mark_scheme_display": _LONG_TITLE,
    }
    html = render_data_table_rows(build_data_table(table, [item]))
    cell = html.split('data-dz-col="mark_scheme"', 1)[1].split("</td>", 1)[0]
    assert f'<span class="dz-tr-cell-truncate" title="{_LONG_TITLE}">{_LONG_TITLE}</span>' in cell


@pytest.mark.parametrize(
    ("region_name", "media_key", "expected"),
    [
        pytest.param("pupils_list", "photo_url", False, id="list-drops-injected-image"),
        pytest.param("pupils_queue", "photo_url", False, id="queue-drops-injected-image"),
        pytest.param("pupils_status", "photo_url", False, id="status_list-drops-injected-image"),
        pytest.param("pupils_grid", "photo_url", True, id="grid-keeps-image"),
        pytest.param("pupils_kanban", "photo_url", True, id="kanban-keeps-image"),
        pytest.param("uploads_list", "attachment", False, id="list-drops-file"),
        pytest.param("uploads_grid", "attachment", True, id="grid-keeps-file"),
    ],
)
def test_media_columns_only_for_card_displays(
    appspec, region_name: str, media_key: str, expected: bool
) -> None:
    """U5: image/file columns are auto-derived only for card-like displays."""
    keys = [c["key"] for c in _region_columns(appspec, region_name)]
    assert (media_key in keys) is expected
    if region_name.startswith("pupils"):
        # The author's repr projection is untouched either way.
        assert {"surname", "forename", "year_group"} <= set(keys)


@pytest.mark.parametrize(
    ("region_name", "expected"),
    [
        pytest.param("pupils_list", False, id="list"),
        pytest.param("pupils_grid", True, id="grid"),
    ],
)
def test_region_render_shows_thumb_only_for_cards(
    appspec, region_name: str, expected: bool
) -> None:
    """U5 end to end: the rendered list has no photo column; the grid card has its thumb."""
    region = _region(appspec, region_name)
    ctx = {
        "items": [
            {
                "id": "p1",
                "surname": "Lovelace",
                "forename": "Ada",
                "year_group": "y10",
                "photo_url": _PHOTO,
            },
        ],
        "columns": _region_columns(appspec, region_name),
    }
    html = FragmentRenderer().render(WorkspaceRegionAdapter().build(region, ctx))
    assert "Lovelace" in html
    assert ("dz-media-thumb" in html) is expected
