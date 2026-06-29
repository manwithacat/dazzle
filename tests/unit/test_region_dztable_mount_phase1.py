"""Task 3 (ADR-0049 Phase 1): the list Region mounts the dzTable controller.

D3 — the `dzTable` Alpine controller mounts on the list Region (the container
that knows it's a stateful list). The substrate builder threads the config
(sortField/sortDir/inlineEditable/bulkActions/entityName) so the hydrated
rows' toggleRow/startEdit/isColumnVisible/toggleSort bindings resolve — the
same controller the legacy `render_filterable_table` wrapper mounted.
"""

from __future__ import annotations

import json

from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.render.fragment import DzTableMount, FragmentRenderer, Region, Text


def _render(frag: object) -> str:
    return FragmentRenderer().render(frag)  # type: ignore[arg-type]


# ── Region renderer: the mount emits the dzTable x-data wrapper ──


class TestRegionMount:
    def test_mount_emits_dztable_x_data_with_config(self) -> None:
        html = _render(
            Region(
                kind="list",
                body=Text("rows"),
                data_table="Task",
                mount=DzTableMount(
                    table_id="dt-task",
                    endpoint="/api/task",
                    sort_field="name",
                    sort_dir="asc",
                    inline_editable=("name",),
                    bulk_actions=True,
                    entity_name="Task",
                ),
            )
        )
        assert 'id="dt-task"' in html
        assert 'dzTable("dt-task", "/api/task"' in html
        assert ':aria-busy="loading"' in html
        assert 'data-dz-bulk-count="0"' in html
        # data-dazzle-table + region kind class preserved
        assert 'data-dazzle-table="Task"' in html
        assert "dz-region--kind-list" in html
        # config JSON carries every dzTable key with the legacy shape
        start = html.index("dzTable(")
        cfg_start = html.index("{", start)
        cfg_end = html.index("}", cfg_start) + 1
        config = json.loads(html[cfg_start:cfg_end])
        assert config == {
            "sortField": "name",
            "sortDir": "asc",
            "inlineEditable": ["name"],
            "bulkActions": True,
            "entityName": "Task",
        }

    def test_no_mount_emits_no_controller(self) -> None:
        html = _render(Region(kind="list", body=Text("rows"), data_table="Task"))
        assert "x-data" not in html
        assert "dzTable" not in html
        # the plain region is otherwise unchanged
        assert 'data-dazzle-table="Task"' in html


# ── Adapter: _build_list threads the mount onto the list Region ──


class _Surface:
    name = "task_list"
    title = "Tasks"
    mode = SurfaceMode.LIST
    entity_ref = "Task"


def _build_list_html(**ctx_over: object) -> str:
    from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter

    base: dict = {
        "entity_name": "Task",
        "title": "Tasks",
        "columns": [{"key": "name", "label": "Name", "type": "text"}],
        "endpoint": "/api/task",
        "region_name": "task",
        "items": [{"id": "a", "name": "Ada"}],
        "total": 1,
    }
    base.update(ctx_over)
    return FragmentRenderer().render(FragmentSurfaceAdapter()._build_list(_Surface(), base))


class TestBuildListMount:
    def test_build_list_mounts_dztable_with_interactive_config(self) -> None:
        html = _build_list_html(
            bulk_actions=True,
            sort_field="name",
            sort_dir="desc",
            inline_editable=["name"],
        )
        assert "dzTable(" in html
        start = html.index("dzTable(")
        cfg = json.loads(html[html.index("{", start) : html.index("}", start) + 1])
        assert cfg["bulkActions"] is True
        assert cfg["sortField"] == "name"
        assert cfg["sortDir"] == "desc"
        assert cfg["inlineEditable"] == ["name"]
        assert cfg["entityName"] == "Task"
        # the dzTable id matches the region/tbody convention (region_name)
        assert 'id="task"' in html

    def test_build_list_plain_list_still_mounts_controller(self) -> None:
        # Legacy always mounts dzTable (it owns the loading spinner + tbody
        # hydrate, not just sort/bulk). A non-interactive list mounts it too,
        # with a quiet config.
        html = _build_list_html()
        assert "dzTable(" in html
        start = html.index("dzTable(")
        cfg = json.loads(html[html.index("{", start) : html.index("}", start) + 1])
        assert cfg["bulkActions"] is False
        assert cfg["inlineEditable"] == []
