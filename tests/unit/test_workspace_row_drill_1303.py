"""#1303: workspace list/task_inbox rows drill to entity detail.

Standalone `/app/<entity>` lists already emit a per-row drill link; workspace
list regions rendered plain `<tr>` with no link. This pins:

- The list adapter emits an `hx-get` clickable `<tr>` when the region ctx
  carries a `detail_url_template` (threaded by the route builder when the
  source has a VIEW surface and the region didn't `drill: none`).
- The `drill:` keyword parses (detail | none; invalid rejected).
- task_inbox items get a `drill_url` resolved per source from the
  entity → detail-URL map; an empty map (drill-gated) leaves them inert.
- `ListRegion.row_links` arity is validated.
"""

from __future__ import annotations

import pytest

from dazzle.core.dsl_parser_impl import parse_dsl
from dazzle.core.errors import ParseError
from dazzle.http.runtime.workspace_card_data import _build_task_inbox_payload
from dazzle.render.fragment.primitives.data import ListColumn, ListRegion
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeRegion:
    def __init__(self, name: str = "things", display: str = "list") -> None:
        self.name = name
        self.title = None
        self.display = display
        self.empty_message = None
        self.row_action = None


def _build_list_html(ctx: dict) -> str:
    return FragmentRenderer().render(WorkspaceRegionAdapter().build(_FakeRegion(), ctx))


# ── list adapter: per-row drill link ──────────────────────────────────────


def test_list_rows_drill_when_detail_url_template_set() -> None:
    html = _build_list_html(
        {
            "items": [{"id": "row-1", "name": "Alice"}, {"id": "row-2", "name": "Bob"}],
            "columns": [{"key": "name", "label": "Name"}],
            "detail_url_template": "/app/task/{id}",
        }
    )
    assert 'hx-get="/app/task/row-1"' in html
    assert 'hx-get="/app/task/row-2"' in html
    assert html.count("is-clickable") == 2
    assert 'hx-target="#main-content"' in html


def test_list_rows_no_link_without_template() -> None:
    """No detail_url_template → plain rows, no regression."""
    html = _build_list_html(
        {
            "items": [{"id": "row-1", "name": "Alice"}],
            "columns": [{"key": "name", "label": "Name"}],
        }
    )
    assert "hx-get" not in html
    assert "is-clickable" not in html


def test_list_links_stay_aligned_when_non_dict_items_skipped() -> None:
    """Defensive: a non-dict item in `items` is skipped for BOTH the row and
    its link, so links stay index-aligned with the rendered rows (the
    ListRegion arity guard would otherwise fire). No crash."""
    html = _build_list_html(
        {
            "items": [{"id": "a", "name": "A"}, "junk", {"id": "c", "name": "C"}],
            "columns": [{"key": "name", "label": "Name"}],
            "detail_url_template": "/app/task/{id}",
        }
    )
    assert 'hx-get="/app/task/a"' in html
    assert 'hx-get="/app/task/c"' in html
    assert html.count("is-clickable") == 2  # only the two dict rows


def test_list_row_missing_key_gets_no_link() -> None:
    """A row missing the template's key yields no link (not a crash), while
    sibling rows still drill."""
    html = _build_list_html(
        {
            "items": [{"id": "ok", "name": "A"}, {"name": "no-id"}],
            "columns": [{"key": "name", "label": "Name"}],
            "detail_url_template": "/app/task/{id}",
        }
    )
    # Only the row with an id drills.
    assert html.count("is-clickable") == 1
    assert 'hx-get="/app/task/ok"' in html


# ── drill: keyword parsing ────────────────────────────────────────────────

_SRC = """module ops
app taskapp "Task App"

entity Task "Task":
  id: uuid pk
  title: str(200) required

surface task_detail "Task":
  uses entity Task
  mode: view
  section main:
    field title "Title"

workspace dash "Dash":
  tasks:
    source: Task
    display: list
{drill_line}
"""


def _parse_region_drill(drill_line: str) -> object:
    src = _SRC.format(drill_line=drill_line)
    return parse_dsl(src, "t.dsl")[5].workspaces[0].regions[0].drill


def test_drill_keyword_parses() -> None:
    assert _parse_region_drill("    drill: detail") == "detail"
    assert _parse_region_drill("    drill: none") == "none"
    assert _parse_region_drill("") is None  # unset → auto (None)


def test_drill_invalid_value_rejected() -> None:
    with pytest.raises(ParseError, match="drill"):
        _parse_region_drill("    drill: sideways")


# ── task_inbox drill_url ──────────────────────────────────────────────────


class _Tmpl:
    def __init__(self) -> None:
        self.icon = ""
        self.title = "{{ title }}"
        self.meta = ""
        self.via_joins = {}


class _Source:
    def __init__(self, source: str, *, as_task: object = None, count_as: str = "") -> None:
        self.source = source
        self.as_task = as_task
        self.count_as = count_as


class _Config:
    def __init__(self, sources: list[_Source]) -> None:
        self.sources = sources


def test_task_inbox_single_source_populates_drill_url() -> None:
    cfg = _Config([_Source("Task", as_task=_Tmpl())])
    items, _ = _build_task_inbox_payload(
        items=[{"id": "t1", "title": "Do X"}],
        config=cfg,
        entity_detail_urls={"Task": "/app/task/{id}"},
    )
    assert items[0]["drill_url"] == "/app/task/t1"


def test_task_inbox_empty_map_leaves_drill_url_blank() -> None:
    """drill: none → route builder passes an empty map → items stay inert."""
    cfg = _Config([_Source("Task", as_task=_Tmpl())])
    items, _ = _build_task_inbox_payload(
        items=[{"id": "t1", "title": "Do X"}],
        config=cfg,
        entity_detail_urls={},
    )
    assert items[0]["drill_url"] == ""


def test_task_inbox_multi_source_per_source_drill_url() -> None:
    cfg = _Config([_Source("Task", as_task=_Tmpl()), _Source("Bug", as_task=_Tmpl())])
    items, _ = _build_task_inbox_payload(
        items=[],
        config=cfg,
        items_per_source={0: [{"id": "t1", "title": "T"}], 1: [{"id": "b1", "title": "B"}]},
        entity_detail_urls={"Task": "/app/task/{id}", "Bug": "/app/bug/{id}"},
    )
    by_url = sorted(i["drill_url"] for i in items)
    assert by_url == ["/app/bug/b1", "/app/task/t1"]


# ── ListRegion.row_links arity ────────────────────────────────────────────


def test_list_region_row_links_arity_validated() -> None:
    cols = (ListColumn(key="name", label="Name"),)
    with pytest.raises(ValueError, match="row_links arity"):
        ListRegion(columns=cols, rows=(("a",), ("b",)), row_links=("/app/x/a",))  # 1 link, 2 rows
