"""Task 3a (ADR-0049 Phase 2): substrate renders related-groups real content.

The substrate `_build_view` originally rendered related groups as `Skeleton`
placeholders; the (now-deleted) legacy `render_detail_view` rendered real inline
content across 4 display modes (table / status_cards / file_list / queue), used by 4+
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
        assert "New Task" in html
        assert "New Tasks" not in html
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


def test_status_cards_preview_url_is_thumb_not_primary() -> None:
    """Campaign-style related cards: preview_url is a thumb, name is title."""
    url = "https://placehold.co/320x200/0F172A/F59E0B/png?text=NW+LOGO+v3"
    tab = _tab(
        columns=[
            ColumnContext(key="preview_url", label="Preview"),
            ColumnContext(key="title", label="Name"),
            ColumnContext(key="version", label="Version"),
        ],
        rows=[
            {
                "id": "t1",
                "preview_url": url,
                "title": "Primary logo (SVG)",
                "version": "3",
            }
        ],
    )
    html = _render(
        RelatedGroupContext(
            group_id="g1", label="Campaign assets", display="status_cards", tabs=[tab]
        )
    )
    assert "dz-media-thumb" in html
    assert "dz-related-status-card-media" in html
    assert 'class="dz-related-status-card-primary">Primary logo (SVG)<' in html
    assert f'class="dz-related-status-card-primary">{url}' not in html
    assert url in html  # src= on the thumb
    assert "Primary logo (SVG)" in html


def test_status_cards_leftover_preview_stays_put() -> None:
    tab = _tab(
        columns=[
            ColumnContext(key="preview_url", label="Preview"),
            ColumnContext(key="title", label="Name"),
        ],
        rows=[{"id": "t1", "preview_url": "zzz", "title": "Primary logo (SVG)"}],
    )
    html = _render(
        RelatedGroupContext(
            group_id="g1", label="Campaign assets", display="status_cards", tabs=[tab]
        )
    )
    assert "dz-media-thumb" not in html
    assert "zzz" in html
    assert "Primary logo (SVG)" in html


def test_status_cards_mode_multi_tab_uses_hm_tabs() -> None:
    """Cycle 1510 — multi related status_cards use HM tabs (not stacked h4s)."""
    g = RelatedGroupContext(
        group_id="g1",
        label="Milestones",
        display="status_cards",
        tabs=[
            _tab(tab_id="open", label="Open"),
            _tab(tab_id="done", label="Done", entity_name="Milestone"),
        ],
    )
    html = _render(g)
    assert 'class="dz-tabs" data-dz-tabs' in html or "data-dz-tabs" in html
    assert 'class="dz-tabs__tab"' in html
    assert 'data-dz-tab-target="dz-related-tab-open"' in html
    assert 'id="dz-related-tab-done"' in html
    assert "dz-related-tab-count" in html
    assert "dz-related-tab-label" not in html
    assert "dz-related-status-card" in html
    assert "Design" in html


# ── file_list mode ──


def test_file_list_mode_renders_files() -> None:
    g = RelatedGroupContext(group_id="g1", label="Files", display="file_list", tabs=[_tab()])
    html = _render(g)
    assert "dz-skeleton" not in html
    assert "dz-related-file" in html
    assert "Design" in html


def test_file_list_mode_multi_tab_uses_hm_tabs() -> None:
    """Cycle 1510 — multi related file_list use HM tabs (not stacked h4s)."""
    g = RelatedGroupContext(
        group_id="g1",
        label="Attachments",
        display="file_list",
        tabs=[
            _tab(tab_id="docs", label="Docs"),
            _tab(tab_id="imgs", label="Images", entity_name="File"),
        ],
    )
    html = _render(g)
    assert 'class="dz-tabs" data-dz-tabs' in html or "data-dz-tabs" in html
    assert 'class="dz-tabs__tab"' in html
    assert 'data-dz-tab-target="dz-related-tab-docs"' in html
    assert 'id="dz-related-tab-imgs"' in html
    assert "dz-related-tab-count" in html
    assert "dz-related-tab-label" not in html
    assert "dz-related-file" in html
    assert "Design" in html


# ── queue mode (cycle 1494) ──


def test_queue_mode_renders_queue_rows() -> None:
    g = RelatedGroupContext(group_id="g1", label="Tasks", display="queue", tabs=[_tab()])
    html = _render(g)
    assert "dz-skeleton" not in html
    assert "dz-queue-region" in html
    assert "dz-queue-rows" in html
    assert "Design" in html


def _conversation_tab(**over: object) -> RelatedTabContext:
    base: dict = {
        "tab_id": "comments",
        "label": "Discussion",
        "entity_name": "Comment",
        "api_endpoint": "/api/comment",
        "filter_field": "ticket",
        "columns": [
            ColumnContext(key="content", label="Content"),
            ColumnContext(key="author", label="Author"),
            ColumnContext(key="created_at", label="Created At", type="datetime"),
            ColumnContext(key="is_internal", label="Is Internal", type="bool"),
        ],
        "rows": [
            {
                "id": "c1",
                "content": "Still blocked after the reset email.",
                "author": "Casey Customer",
                "created_at": "2026-07-12T10:15:00",
                "is_internal": False,
            },
            {
                "id": "c2",
                "content": "Internal: force-expire both sessions.",
                "author": "Alex Agent",
                "created_at": "2026-07-12T10:44:00",
                "is_internal": True,
            },
        ],
        "total": 2,
        "detail_url_template": "/comment/{id}",
        "create_url": "/comment/create",
    }
    base.update(over)
    return RelatedTabContext(**base)


def test_conversation_mode_renders_message_chrome() -> None:
    """Cycle 1893 — related display:conversation → Message/Bubble chrome."""
    g = RelatedGroupContext(
        group_id="g1",
        label="Discussion",
        display="conversation",
        tabs=[_conversation_tab()],
    )
    html = _render(g)
    assert "dz-skeleton" not in html
    assert "dz-message-scroller" in html
    assert 'class="dz-message"' in html or 'class="dz-message" ' in html
    assert "dz-bubble" in html
    assert "Still blocked after the reset email." in html
    assert "Internal: force-expire both sessions." in html
    # is_internal orients outbound internal notes; does not dump Yes/No as speech.
    assert "force-expire" in html
    assert 'data-dz-from="out"' in html
    assert 'data-dz-from="in"' in html


def test_queue_mode_labels_meta_with_column_headers() -> None:
    """Cycle 1498 — meta cells include header labels (Status: …)."""
    g = RelatedGroupContext(group_id="g1", label="Tasks", display="queue", tabs=[_tab()])
    html = _render(g)
    assert "dz-queue-row-meta" in html
    # Badge/type format may title-case values; label prefix is the contract.
    assert "Status: " in html
    assert "Design" in html


def test_queue_mode_overflow_when_total_exceeds_rows() -> None:
    """Cycle 1516 — related queue shows total + overflow when fetch is capped."""
    g = RelatedGroupContext(
        group_id="g1",
        label="Tasks",
        display="queue",
        tabs=[_tab(total=12)],
    )
    html = _render(g)
    assert 'class="dz-queue-count">12</span>' in html or ">12</span>" in html
    assert "Showing 2 of 12" in html
    assert "dz-queue-overflow" in html


def test_related_tab_count_uses_total_when_capped() -> None:
    """Cycle 1524 — multi-tab badges show full total, not only fetched rows."""
    g = RelatedGroupContext(
        group_id="g1",
        label="Work",
        display="queue",
        tabs=[
            _tab(tab_id="tasks", label="Tasks", total=12),
            _tab(tab_id="bugs", label="Bugs", entity_name="Bug", total=5),
        ],
    )
    html = _render(g)
    assert "dz-related-tab-count" in html
    assert ">12</span>" in html
    assert ">5</span>" in html


def test_status_cards_overflow_when_total_exceeds_rows() -> None:
    """Cycle 1524 — status_cards show Showing N of M when fetch is capped."""
    g = RelatedGroupContext(
        group_id="g1",
        label="Milestones",
        display="status_cards",
        tabs=[_tab(total=9)],
    )
    html = _render(g)
    assert "Showing 2 of 9" in html
    assert "dz-related-overflow" in html


def test_file_list_overflow_when_total_exceeds_rows() -> None:
    """Cycle 1524 — file_list overflow parity with queue/table."""
    g = RelatedGroupContext(
        group_id="g1",
        label="Files",
        display="file_list",
        tabs=[_tab(total=7)],
    )
    html = _render(g)
    assert "Showing 2 of 7" in html
    assert "dz-related-overflow" in html


def test_table_mode_overflow_when_total_exceeds_rows() -> None:
    """Cycle 1524 — related table overflow when fetch is capped."""
    g = RelatedGroupContext(
        group_id="g1",
        label="Tasks",
        display="table",
        tabs=[_tab(total=11)],
    )
    html = _render(g)
    assert "Showing 2 of 11" in html
    assert "dz-related-overflow" in html


def test_queue_mode_multi_tab_uses_hm_tabs() -> None:
    """Cycle 1505 — multi related-queue strips use HM tabs (not stacked h4s)."""
    g = RelatedGroupContext(
        group_id="g1",
        label="Work",
        display="queue",
        tabs=[
            _tab(tab_id="tasks", label="Tasks"),
            _tab(tab_id="bugs", label="Bugs", entity_name="Bug"),
        ],
    )
    html = _render(g)
    assert 'class="dz-tabs" data-dz-tabs' in html or "data-dz-tabs" in html
    assert 'class="dz-tabs__tab"' in html
    assert 'data-dz-tab-target="dz-related-tab-tasks"' in html
    assert 'id="dz-related-tab-bugs"' in html
    assert "dz-related-tab-count" in html
    assert "dz-related-tab-label" not in html  # no stacked h4 labels
    assert "dz-queue-region" in html
    assert "Design" in html
