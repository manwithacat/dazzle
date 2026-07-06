"""Task 3a (ADR-0049 Phase 2): substrate renders related-groups real content.

The substrate `_build_view` originally rendered related groups as `Skeleton`
placeholders; the (now-deleted) legacy `render_detail_view` rendered real inline
content across 3 display modes (table / status_cards / file_list), used by 4+
example apps. The substrate dispatch ctx didn't even carry the fetched data (it
threaded the surface IR config, not `detail.related_groups`). The substrate now
reproduces that content; this pins it.
"""

from __future__ import annotations

from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.http.runtime.page_routes import _build_dispatch_ctx
from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
from dazzle.render.context import (
    ColumnContext,
    DetailContext,
    FieldContext,
    RelatedGroupContext,
    RelatedTabContext,
)
from dazzle.render.fragment import FragmentRenderer


class _Surface:
    name = "project_detail"
    title = "Project"
    mode = SurfaceMode.VIEW
    entity_ref = "Project"
    sections = ()
    related_groups = ()


class _RC:
    def __init__(self, detail: DetailContext) -> None:
        self.table = None
        self.form = None
        self.detail = detail


def _tab(**over: object) -> RelatedTabContext:
    base: dict = {
        "tab_id": "tasks",
        "label": "Tasks",
        "entity_name": "Task",
        "api_endpoint": "/api/task",
        "filter_field": "project",
        "columns": [
            ColumnContext(key="title", label="Title"),
            ColumnContext(key="status", label="Status", type="badge"),
        ],
        "rows": [
            {"id": "t1", "title": "Design", "status": "open"},
            {"id": "t2", "title": "Build", "status": "done"},
        ],
        "total": 2,
        "detail_url_template": "/task/{id}",
        "create_url": "/task/create",
    }
    base.update(over)
    return RelatedTabContext(**base)


def _detail(group: RelatedGroupContext) -> DetailContext:
    return DetailContext(
        entity_name="Project",
        title="Apollo",
        fields=[FieldContext(name="name", label="Name")],
        item={"id": "p1", "name": "Apollo"},
        related_groups=[group],
    )


def _render(group: RelatedGroupContext) -> str:
    ctx = _build_dispatch_ctx(_RC(_detail(group)), _Surface())
    return FragmentRenderer().render(FragmentSurfaceAdapter()._build_view(_Surface(), ctx))


# ── dispatch ctx now carries the fetched related data ──


def test_dispatch_ctx_threads_fetched_related_groups() -> None:
    group = RelatedGroupContext(group_id="g1", label="Tasks", display="table", tabs=[_tab()])
    ctx = _build_dispatch_ctx(_RC(_detail(group)), _Surface())
    rgs = ctx["related_groups"]
    assert rgs and rgs[0]["display"] == "table"
    assert rgs[0]["tabs"][0]["rows"] == [
        {"id": "t1", "title": "Design", "status": "open"},
        {"id": "t2", "title": "Build", "status": "done"},
    ]


# ── table mode ──


class TestTableMode:
    def _g(self, **o) -> RelatedGroupContext:
        base = {"group_id": "g1", "label": "Tasks", "display": "table", "tabs": [_tab()]}
        base.update(o)
        return RelatedGroupContext(**base)

    def test_renders_real_rows_not_skeleton(self) -> None:
        html = _render(self._g())
        assert "dz-skeleton" not in html
        assert "dz-related-table" in html
        # the actual related records render inline
        assert "Design" in html
        assert "Build" in html
        # column headers
        assert "<th" in html and "Title" in html

    def test_rows_drill_to_detail(self) -> None:
        html = _render(self._g())
        assert 'hx-get="/task/t1"' in html
        assert 'hx-get="/task/t2"' in html

    def test_create_row_anchor(self) -> None:
        html = _render(self._g())
        assert 'data-dazzle-action="Task.create"' in html
        assert "New Tasks" in html
        # the create href carries the parent filter
        assert "project=p1" in html

    def test_multi_tab_strip(self) -> None:
        html = _render(
            self._g(
                tabs=[
                    _tab(tab_id="tasks", label="Tasks"),
                    _tab(tab_id="files", label="Files", entity_name="File"),
                ]
            )
        )
        # F4: the tab strip rides the HM tabs Hyperpart (dz-tabs.js) —
        # honest link-strip (aria-current, native hidden), no Alpine, no
        # role=tablist it can't back with arrow-key navigation.
        assert "x-data" not in html
        assert "activeTab" not in html
        assert 'class="dz-tabs__tab"' in html
        assert 'aria-current="true"' in html
        assert 'data-dz-tab-target="dz-related-tab-tasks"' in html
        assert 'id="dz-related-tab-files"' in html
        assert "dz-related-tab-count" in html  # count chip survives
        assert "hidden" in html  # non-first panel starts hidden


# ── status_cards mode ──


def test_status_cards_mode_renders_cards() -> None:
    g = RelatedGroupContext(
        group_id="g1", label="Milestones", display="status_cards", tabs=[_tab()]
    )
    html = _render(g)
    assert "dz-skeleton" not in html
    assert "dz-related-status-card" in html
    assert "Design" in html


# ── file_list mode ──


def test_file_list_mode_renders_files() -> None:
    g = RelatedGroupContext(group_id="g1", label="Files", display="file_list", tabs=[_tab()])
    html = _render(g)
    assert "dz-skeleton" not in html
    assert "dz-related-file" in html
    assert "Design" in html
