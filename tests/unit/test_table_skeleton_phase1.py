"""Task 2 (ADR-0049 Phase 1): the `Table` primitive gains a skeleton mode.

D2 — the substrate list first-paint emits chrome + an empty
`<tbody hx-trigger="load">` pointing at `/api`, so rows always come from
`render_data_row` (ADR-0048), never inline. This test pins the skeleton tbody
shape against the legacy `render_filterable_table` tbody (table_renderer.py:431)
so the hydrate is identical. Inline-row rendering (skeleton=False) is unchanged.
"""

import pytest

from dazzle.render.fragment import FragmentRenderer
from dazzle.render.fragment.primitives import Table


def _render(t: Table) -> str:
    return FragmentRenderer().render(t)


class TestSkeletonTbody:
    def test_skeleton_emits_empty_hydrating_tbody(self) -> None:
        html = _render(
            Table(
                columns=("Name",),
                rows=(),
                skeleton=True,
                tbody_id="dt-task-body",
                hx_endpoint="/api/task",
            )
        )
        # hydrating tbody pointing at /api with load trigger + innerMorph swap
        assert '<tbody id="dt-task-body"' in html
        assert 'hx-get="/api/task"' in html
        assert 'hx-trigger="load"' in html
        assert 'hx-swap="innerMorph"' in html
        assert 'hx-headers=\'{"Accept": "text/html"}\'' in html
        assert 'class="dz-table-body"' in html
        # the dzTable loading bindings (mounted on the Region) drive the spinner
        assert '@htmx:before-request="loading = true"' in html
        assert '@htmx:after-settle="loading = false"' in html
        # NO inline rows — rows come from /api → render_data_row only
        assert "<tr>" not in html.split("<tbody")[1]
        assert "<td" not in html
        # thead still renders the column header
        assert "<thead><tr><th>Name</th></tr></thead>" in html

    def test_skeleton_refresh_interval_appends_every(self) -> None:
        html = _render(
            Table(
                columns=("Name",),
                rows=(),
                skeleton=True,
                tbody_id="dt-task-body",
                hx_endpoint="/api/task",
                refresh_interval=30,
            )
        )
        assert 'hx-trigger="load, every 30s"' in html

    def test_skeleton_blank_trigger_suppresses_attr(self) -> None:
        # search_first lists omit the load trigger (the search box drives the
        # first fetch). `_build_list` passes hx_trigger="".
        html = _render(
            Table(
                columns=("Name",),
                rows=(),
                skeleton=True,
                tbody_id="dt-task-body",
                hx_endpoint="/api/task",
                hx_trigger="",
            )
        )
        assert "hx-trigger=" not in html

    def test_skeleton_loading_indicator(self) -> None:
        html = _render(
            Table(
                columns=("Name",),
                rows=(),
                skeleton=True,
                tbody_id="dt-task-body",
                hx_endpoint="/api/task",
                loading_indicator="#dt-task-loading-sr",
            )
        )
        assert 'hx-indicator="#dt-task-loading-sr"' in html

    def test_skeleton_with_bulk_select_keeps_select_all_header(self) -> None:
        html = _render(
            Table(
                columns=("Name",),
                rows=(),
                skeleton=True,
                tbody_id="dt-task-body",
                hx_endpoint="/api/task",
                bulk_select=True,
            )
        )
        # select-all header cell present; tbody still empty
        assert "toggleSelectAll" in html
        assert "<td" not in html

    def test_skeleton_forbids_inline_rows(self) -> None:
        with pytest.raises(ValueError, match="skeleton"):
            Table(columns=("Name",), rows=(("a",),), skeleton=True)


class TestInlineRowsUnchanged:
    def test_non_skeleton_still_renders_inline_rows(self) -> None:
        html = _render(Table(columns=("Name",), rows=(("Ada",), ("Grace",))))
        assert "<td>Ada</td>" in html
        assert "<td>Grace</td>" in html
        # no skeleton attrs leak into the plain table
        assert "hx-trigger" not in html
        assert "dz-table-body" not in html
