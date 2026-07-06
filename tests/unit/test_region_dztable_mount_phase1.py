"""The list Region's grid mount (ADR-0049 D3 → convergence C2.4).

History: D3 originally mounted the `dzTable` Alpine controller here. The
HM grid primitive + its extensions (dz-grid.js / dz-grid-cols.js /
dz-grid-resize.js / dz-grid-edit.js — all delegated, state-in-DOM) now own
every behaviour dzTable carried, so C2.4 retires the `x-data` mount: the
region root is an HM grid root and nothing else. C3 deletes the dzTable
controller code itself.

The pinned contract: the mount emits the grid-root attributes
(`data-dz-grid`, `data-dz-grid-url`, `data-dz-grid-edit-url`,
`data-dz-bulk-count`) and NO Alpine bindings — a reintroduced `x-data`
would resurrect the two-controller split the convergence removed.
"""

from __future__ import annotations

from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.render.fragment import DzTableMount, FragmentRenderer, Region, Text


def _render(frag: object) -> str:
    return FragmentRenderer().render(frag)  # type: ignore[arg-type]


# ── Region renderer: the mount emits the HM grid root, no Alpine ──


class TestRegionMount:
    def test_mount_emits_hm_grid_root(self) -> None:
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
        assert "data-dz-grid data-dz-grid-url" in html
        assert 'data-dz-grid-edit-url="/api/task"' in html
        assert 'data-dz-bulk-count="0"' in html
        # data-dazzle-table + region kind class preserved
        assert 'data-dazzle-table="Task"' in html
        assert "dz-region--kind-list" in html

    def test_mount_emits_no_alpine_bindings(self) -> None:
        """C2.4: the dzTable Alpine mount is retired — the delegated HM
        controllers own sort/selection/bulk/cols/resize/edit. Any Alpine
        binding here would re-split state ownership."""
        html = _render(
            Region(
                kind="list",
                body=Text("rows"),
                mount=DzTableMount(table_id="t", endpoint="/api/t"),
            )
        )
        assert "x-data" not in html
        assert "dzTable" not in html
        assert "aria-busy" not in html
        # the dzTable announcer target is gone too (dz-grid.js announces via
        # [data-dz-grid-announce]; dashboard-builder self-creates its own)
        assert "dz-live-region" not in html

    def test_no_mount_emits_no_controller(self) -> None:
        html = _render(Region(kind="list", body=Text("rows"), data_table="Task"))
        assert "x-data" not in html
        assert "dzTable" not in html
        assert "data-dz-grid" not in html
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
    def test_build_list_mounts_grid_root(self) -> None:
        html = _build_list_html(
            bulk_actions=True,
            sort_field="name",
            sort_dir="desc",
            inline_editable=["name"],
        )
        assert "data-dz-grid data-dz-grid-url" in html
        assert 'data-dz-grid-edit-url="/api/task"' in html
        assert "dzTable(" not in html
        # the grid id matches the region/tbody convention (region_name)
        assert 'id="task"' in html

    def test_build_list_plain_list_still_mounts_grid_root(self) -> None:
        # Every full-page list is a grid root (the tbody hydrate + loading
        # overlay ride the HM contract, not just sort/bulk).
        html = _build_list_html()
        assert "data-dz-grid data-dz-grid-url" in html
        assert "dzTable(" not in html
