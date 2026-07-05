"""Task 4 (ADR-0049 Phase 1): substrate-canonical comprehensive list chrome.

Re-scope (James, 2026-06-29): substrate-canonical — accept the FTS-dropdown
search divergence, deliver the rest of the legacy list-chrome surface in the
substrate in one pass. This file pins each canonical chrome element. See the
plan's Task-4 element ledger for the per-element disposition.

Sub-steps: 4a Table-skeleton (caption + actions-th + grid class), 4b
DataListScroll (scroll/loading/empty/loading-sr), 4c ColumnVisibilityMenu,
4d working list filters, 4e _build_list canonical composition.
"""

from __future__ import annotations

from dazzle.render.fragment import FragmentRenderer
from dazzle.render.fragment.primitives import Table


def _render(frag: object) -> str:
    return FragmentRenderer().render(frag)  # type: ignore[arg-type]


# ── 4a: Table skeleton — grid class + sr caption + trailing actions th ──


class TestSkeletonTableChrome:
    def test_skeleton_uses_grid_class(self) -> None:
        html = _render(Table(columns=("Name",), rows=(), skeleton=True, hx_endpoint="/api/task"))
        assert '<table class="dz-table-grid">' in html
        assert '<table class="dz-table">' not in html

    def test_skeleton_emits_visually_hidden_caption(self) -> None:
        html = _render(
            Table(
                columns=("Name",), rows=(), skeleton=True, hx_endpoint="/api/task", caption="Tasks"
            )
        )
        assert '<caption class="visually-hidden">Tasks</caption>' in html

    def test_skeleton_caption_escaped(self) -> None:
        html = _render(
            Table(columns=("Name",), rows=(), skeleton=True, hx_endpoint="/x", caption="A & B")
        )
        assert "A &amp; B" in html

    def test_skeleton_emits_trailing_actions_th_when_has_actions(self) -> None:
        html = _render(
            Table(columns=("Name",), rows=(), skeleton=True, hx_endpoint="/x", has_actions=True)
        )
        assert '<th scope="col" class="dz-table-th-actions">' in html
        assert '<span class="visually-hidden">Actions</span>' in html
        # actions th comes AFTER the data header (matches render_data_row cell order)
        assert html.index("Name") < html.index("dz-table-th-actions")

    def test_skeleton_no_actions_th_by_default(self) -> None:
        html = _render(Table(columns=("Name",), rows=(), skeleton=True, hx_endpoint="/x"))
        assert "dz-table-th-actions" not in html

    def test_skeleton_actions_th_after_select_and_data(self) -> None:
        html = _render(
            Table(
                columns=("Name",),
                rows=(),
                skeleton=True,
                hx_endpoint="/x",
                bulk_select=True,
                has_actions=True,
            )
        )
        # column order: select-th, data-th, actions-th
        assert (
            html.index("dz-table-th-select")
            < html.index("Name")
            < html.index("dz-table-th-actions")
        )

    def test_non_skeleton_table_unchanged_by_caption_field(self) -> None:
        # caption/has_actions only affect skeleton mode
        html = _render(Table(columns=("Name",), rows=(("Ada",),), caption="X", has_actions=True))
        assert "<caption" not in html
        assert "dz-table-th-actions" not in html
        assert '<table class="dz-table">' in html


# ── 4b: DataListScroll — scroll/loading/scroll-x/empty/loading-sr shell ──


class TestDataListScroll:
    def _shell(self, **over: object):
        from dazzle.render.fragment.primitives import DataListScroll, Table

        base: dict = {
            "table": Table(
                columns=("Name",), rows=(), skeleton=True, hx_endpoint="/api/task", caption="Tasks"
            ),
            "table_id": "task",
            "page_size": 25,
            "aria_label": "Tasks",
            "empty_title": "No tasks found",
        }
        base.update(over)
        return DataListScroll(**base)

    def test_emits_dz_table_wrapper_for_css_scoping(self) -> None:
        # the .dz-table ancestor is what activates the table.css loading +
        # empty-sibling + scroll rules.
        html = _render(self._shell())
        assert '<div class="dz-table">' in html

    def test_scroll_sets_list_rows_var(self) -> None:
        html = _render(self._shell(page_size=25))
        assert 'class="dz-table-scroll"' in html
        assert "--dz-list-rows: 25" in html

    def test_loading_spinner_overlay(self) -> None:
        html = _render(self._shell())
        assert 'aria-hidden="true" class="dz-table-loading"' in html
        assert "dz-table-loading-spinner" in html

    def test_scroll_x_region_is_focusable_landmark(self) -> None:
        html = _render(self._shell(aria_label="Tasks"))
        assert 'class="dz-table-scroll-x" role="region"' in html
        assert 'aria-label="Tasks table"' in html
        assert 'tabindex="0"' in html

    def test_table_child_rendered_inside_scroll_x(self) -> None:
        html = _render(self._shell())
        # the skeleton grid is present, inside the scroll-x, before the empty sibling
        assert "dz-table-grid" in html
        assert html.index("dz-table-grid") < html.index("dz-table-empty")

    def test_empty_sibling_follows_grid(self) -> None:
        html = _render(self._shell(empty_title="No tasks found"))
        assert 'id="task-empty" role="status" class="dz-table-empty"' in html
        assert '<p class="dz-table-empty-title">No tasks found</p>' in html
        # the empty div is a FOLLOWING sibling of the grid (CSS selector needs this)
        assert html.index("</table>") < html.index('id="task-empty"')

    def test_empty_optional_cta(self) -> None:
        html = _render(
            self._shell(empty_action_href="/app/task/create", empty_action_label="New Task")
        )
        assert 'href="/app/task/create"' in html
        assert "New Task" in html

    def test_empty_no_cta_by_default(self) -> None:
        html = _render(self._shell())
        assert "dz-button-primary" not in html

    def test_loading_sr_indicator(self) -> None:
        html = _render(self._shell())
        assert (
            '<div id="task-loading-sr" class="htmx-indicator visually-hidden" '
            'role="status" aria-label="Loading data">Loading…</div>'
        ) in html
        # loading-sr is OUTSIDE the scroll (after it)
        assert html.index('class="dz-table-scroll"') < html.index("task-loading-sr")


# ── 4c: ColumnVisibilityMenu — header checkbox grid bound to dzTable ──


class TestColumnVisibilityMenu:
    def _menu(self, cols):
        from dazzle.render.fragment.primitives import ColumnVisibilityMenu

        return ColumnVisibilityMenu(columns=cols)

    def test_trigger_button_a11y(self) -> None:
        html = _render(self._menu((("name", "Name"), ("status", "Status"))))
        assert 'class="dz-table-col-menu"' in html
        assert '@click.outside="colMenuOpen = false"' in html
        assert 'aria-label="Toggle column visibility"' in html
        assert 'aria-haspopup="menu"' in html
        assert ':aria-expanded="colMenuOpen"' in html

    def test_panel_is_a_menu(self) -> None:
        html = _render(self._menu((("name", "Name"),)))
        assert 'role="menu" class="dz-table-col-menu-panel"' in html
        assert 'x-show="colMenuOpen"' in html

    def test_per_column_checkbox_bound_to_controller(self) -> None:
        html = _render(self._menu((("name", "Name"), ("status", "Status"))))
        assert "isColumnVisible('name')" in html
        assert "toggleColumn('name')" in html
        assert "isColumnVisible('status')" in html
        assert "<span>Name</span>" in html
        assert 'aria-label="Show Status column"' in html

    def test_escapes_keys_and_labels(self) -> None:
        html = _render(self._menu((("a&b", "A & B"),)))
        assert "A &amp; B" in html


# ── 4d: ListFilterBar — list filters that actually filter the tbody ──


class TestListFilterBar:
    def _bar(self, columns):
        from dazzle.render.fragment import URL
        from dazzle.render.fragment.primitives import ListFilterBar

        return ListFilterBar(
            tbody_id="task-body",
            endpoint=URL("/api/task"),
            loading_indicator="#task-loading-sr",
            columns=columns,
        )

    def _select_col(self, **over):
        from dazzle.render.fragment.primitives import FilterColumn

        base = {"key": "status", "label": "Status", "options": (("open", "Open"), ("done", "Done"))}
        base.update(over)
        return FilterColumn(**base)

    def test_select_carries_grid_filter_key(self) -> None:
        # Convergence C1.1: filters are the HM grid controller's seam — each
        # control carries data-dz-grid-filter with the bracketed wire key the
        # /api list handler parses; the per-control hx-get/hx-target/hx-include
        # wiring is gone (the controller composes one query from DOM state).
        html = _render(self._bar((self._select_col(),)))
        assert 'name="filter[status]"' in html
        assert 'data-dz-grid-filter="filter[status]"' in html
        assert "hx-get=" not in html
        assert "hx-target=" not in html
        assert "hx-include=" not in html
        assert "#region-" not in html

    def test_select_renders_options_and_all(self) -> None:
        html = _render(self._bar((self._select_col(selected="done"),)))
        assert '<option value="">All</option>' in html
        assert '<option value="open">Open</option>' in html
        assert '<option value="done" selected>Done</option>' in html

    def test_text_filter_input(self) -> None:
        html = _render(
            self._bar(
                (self._select_col(key="owner", label="Owner", filter_type="text", options=()),)
            )
        )
        assert 'name="filter[owner]"' in html
        assert 'type="text"' in html
        # Convergence C1.1: the text input applies via the grid controller's
        # data-dz-grid-filter seam, not a per-control hx-trigger.
        assert 'data-dz-grid-filter="filter[owner]"' in html
        assert "hx-trigger=" not in html

    def test_ref_select_carries_ref_api_and_init(self) -> None:
        html = _render(
            self._bar(
                (
                    self._select_col(
                        key="client",
                        label="Client",
                        filter_type="ref",
                        options=(),
                        ref_api="/client",
                    ),
                )
            )
        )
        assert 'name="filter[client]"' in html
        assert 'data-ref-api="/client"' in html
        assert 'x-init="dzFilterRefSelect($el)"' in html

    def test_labels_present(self) -> None:
        html = _render(self._bar((self._select_col(),)))
        assert '<label class="dz-filter-label">Status</label>' in html


# ── 4e support: data-dz-col on thead, pagination footer, live region ──


class TestColumnVisibilityWiring:
    def test_skeleton_th_carries_data_dz_col_when_keys_given(self) -> None:
        html = _render(
            Table(
                columns=("Name", "Status"),
                rows=(),
                skeleton=True,
                hx_endpoint="/x",
                column_keys=("name", "status"),
            )
        )
        # the JS hides columns by style.display on [data-dz-col]; the thead
        # cells need it too or the header/cell columns desync. Non-sortable
        # canonical headers carry the dz-table-th class.
        assert '<th data-dz-col="name" scope="col" class="dz-table-th">Name</th>' in html
        assert '<th data-dz-col="status" scope="col" class="dz-table-th">Status</th>' in html

    def test_skeleton_sortable_header_is_grid_sort_button(self) -> None:
        html = _render(
            Table(
                columns=("Name",),
                rows=(),
                skeleton=True,
                hx_endpoint="/x",
                column_keys=("name",),
                sortable_keys=("name",),
            )
        )
        # Convergence C1.1: sortable headers drive the HM grid controller —
        # data-dz-grid-sort button, static aria-sort="none" (dz-grid.js cycles
        # it), CSS caret keyed off aria-sort (chevron-UP path). No Alpine.
        assert '<th data-dz-col="name" aria-sort="none" scope="col" class="dz-table-th">' in html
        assert 'data-dz-grid-sort="name"' in html
        assert 'class="dz-table-sort-button"' in html
        assert 'class="dz-table-sort-icon"' in html
        assert '<path d="M2 7.5l4-4 4 4"' in html
        assert 'aria-label="Sort by Name"' in html
        assert "toggleSort" not in html
        assert "sortIcon" not in html
        assert ":aria-sort=" not in html

    def test_skeleton_th_plain_without_keys(self) -> None:
        html = _render(Table(columns=("Name",), rows=(), skeleton=True, hx_endpoint="/x"))
        assert "<th>Name</th>" in html
        assert "data-dz-col" not in html


class TestPaginationFooter:
    def _shell(self, **over):
        from dazzle.render.fragment.primitives import DataListScroll, Table

        base = {
            "table": Table(columns=("Name",), rows=(), skeleton=True, hx_endpoint="/x"),
            "table_id": "task",
            "empty_title": "No tasks found",
        }
        base.update(over)
        return DataListScroll(**base)

    def test_pagination_footer_container_present_by_default(self) -> None:
        html = _render(self._shell())
        # the OOB pagination swap from /api targets #{table_id}-pagination
        assert '<div id="task-pagination" class="dz-table-footer"></div>' in html

    def test_no_pagination_footer_when_infinite(self) -> None:
        html = _render(self._shell(paginated=False))
        assert "task-pagination" not in html


class TestRegionLiveRegion:
    def test_mounted_region_appends_live_region(self) -> None:
        from dazzle.render.fragment import DzTableMount, Region, Text

        html = _render(
            Region(
                kind="list",
                body=Text("x"),
                data_table="Task",
                mount=DzTableMount(table_id="task", endpoint="/api/task"),
            )
        )
        assert (
            '<div id="dz-live-region" aria-live="polite" aria-atomic="true" '
            'class="visually-hidden"></div>'
        ) in html

    def test_unmounted_region_has_no_live_region(self) -> None:
        from dazzle.render.fragment import Region, Text

        html = _render(Region(kind="list", body=Text("x")))
        assert "dz-live-region" not in html
