"""Pre-flip adversarial-review fixes (ADR-0049 Phase 1, Task 5 Step 0).

The independent review of the canonical substrate list found that
`_build_dispatch_ctx` was an incomplete adapter for what `_build_list`
consumes, and that `_build_list` could 500 on degenerate columns — both would
break default lists fleet-wide at the flip (D4 removes the legacy fallback).
These tests pin the fixes before the flip.
"""

from __future__ import annotations

from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.http.runtime.page_routes import _build_dispatch_ctx
from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
from dazzle.render.context import ColumnContext, TableContext
from dazzle.render.fragment import FragmentRenderer


class _Surface:
    name = "task_list"
    title = "Tasks"
    mode = SurfaceMode.LIST
    entity_ref = "Task"


class _RC:
    def __init__(self, table: TableContext) -> None:
        self.table = table
        self.form = None
        self.detail = None


def _tc(**over: object) -> TableContext:
    base: dict = {
        "entity_name": "Task",
        "title": "Tasks",
        "columns": [ColumnContext(key="name", label="Name")],
        "api_endpoint": "/api/task",
        "table_id": "task",
    }
    base.update(over)
    return TableContext(**base)


def _render(ctx: dict) -> str:
    return FragmentRenderer().render(FragmentSurfaceAdapter()._build_list(_Surface(), ctx))


# ── SEV-1/2: dispatch ctx now threads everything _build_list reads ──


class TestDispatchCtxCompleteness:
    def test_ctx_threads_per_column_filter_type_and_ref(self) -> None:
        tc = _tc(
            columns=[
                ColumnContext(key="owner", label="Owner", filterable=True, filter_type="text"),
                ColumnContext(
                    key="client",
                    label="Client",
                    filterable=True,
                    filter_type="select",
                    filter_ref_entity="Client",
                    filter_ref_api="/client",
                ),
            ]
        )
        ctx = _build_dispatch_ctx(_RC(tc), _Surface())
        owner = next(c for c in ctx["columns"] if c["key"] == "owner")
        client = next(c for c in ctx["columns"] if c["key"] == "client")
        assert owner["filter_type"] == "text"
        assert client["filter_ref_entity"] == "Client"
        assert client["filter_ref_api"] == "/client"

    def test_ctx_threads_inline_refresh_pagination_searchfirst(self) -> None:
        tc = _tc(
            inline_editable=["name"],
            refresh_interval=30,
            pagination_mode="infinite",
            search_first=True,
        )
        ctx = _build_dispatch_ctx(_RC(tc), _Surface())
        assert ctx["inline_editable"] == ["name"]
        assert ctx["refresh_interval"] == 30
        assert ctx["pagination_mode"] == "infinite"
        assert ctx["search_first"] is True


# ── SEV-2 end-to-end: the threaded fields actually drive the chrome ──


class TestThreadedFieldsDriveChrome:
    def _ctx(self, **over: object) -> dict:
        return _build_dispatch_ctx(_RC(_tc(**over)), _Surface())

    def test_text_filter_renders_input_not_empty_select(self) -> None:
        html = _render(
            self._ctx(
                columns=[
                    ColumnContext(key="owner", label="Owner", filterable=True, filter_type="text")
                ]
            )
        )
        assert 'type="text" name="filter[owner]"' in html
        assert "dz-filter-input" in html

    def test_ref_filter_renders_ref_select(self) -> None:
        html = _render(
            self._ctx(
                columns=[
                    ColumnContext(
                        key="client",
                        label="Client",
                        filterable=True,
                        filter_type="select",
                        filter_ref_entity="Client",
                        filter_ref_api="/client",
                    )
                ]
            )
        )
        assert 'data-ref-api="/client"' in html
        assert 'x-init="dzFilterRefSelect($el)"' in html

    def test_inline_editable_mount_carries_no_config(self) -> None:
        """C2.4: the dzTable config JSON is gone — inline-editable columns
        reach the rows as per-cell seam spans (`data-dz-grid-edit`, threaded
        through list_handlers), and the mount only carries the commit base
        (`data-dz-grid-edit-url`)."""
        html = _render(self._ctx(inline_editable=["name"]))
        assert "inlineEditable" not in html
        assert "data-dz-grid-edit-url" in html

    def test_refresh_interval_polls(self) -> None:
        # Convergence C1.1: dz-grid:refresh always joins the trigger list,
        # after the load trigger and before the poll.
        html = _render(self._ctx(refresh_interval=15))
        assert 'hx-trigger="load, dz-grid:refresh, every 15s"' in html

    def test_infinite_pagination_has_no_footer(self) -> None:
        html = _render(self._ctx(pagination_mode="infinite"))
        assert "-pagination" not in html

    def test_search_first_omits_load_trigger(self) -> None:
        html = _render(self._ctx(search_first=True, search_enabled=True, search_fields=["name"]))
        # the tbody must not auto-fetch; the search drives the first load
        assert 'hx-trigger="load"' not in html


# ── SEV-1: _build_list tolerates degenerate columns (no 500, no fallback) ──


class TestDegenerateColumns:
    def test_zero_visible_columns_renders_actions_only(self) -> None:
        # all columns hidden → no data columns; must still render a valid table
        ctx = _build_dispatch_ctx(
            _RC(_tc(columns=[ColumnContext(key="secret", label="Secret", hidden=True)])), _Surface()
        )
        html = _render(ctx)  # must not raise
        assert "dz-table-grid" in html
        assert "dz-table-th-actions" in html

    def test_no_columns_at_all_renders(self) -> None:
        ctx = _build_dispatch_ctx(_RC(_tc(columns=[])), _Surface())
        html = _render(ctx)  # must not raise
        assert "dz-table-grid" in html

    def test_keyless_filterable_column_is_skipped_not_crashed(self) -> None:
        # a filterable column dict with no key must be skipped, not KeyError
        ctx = _build_dispatch_ctx(_RC(_tc()), _Surface())
        ctx["columns"] = [{"label": "Broken", "filterable": True, "type": "text"}]
        html = _render(ctx)  # must not raise
        assert "dz-table-grid" in html
        assert "dz-filter" not in html  # the keyless filter was dropped


# ── SEV-3: parity polish ──


class TestParityPolish:
    def test_empty_state_title_is_entity_specific(self) -> None:
        html = _render(_build_dispatch_ctx(_RC(_tc(entity_title="To-Do")), _Surface()))
        assert "No to-dos found" in html

    def test_select_all_is_grid_controller_seam(self) -> None:
        # Convergence C1.1: the select-all box is the HM grid controller's
        # `data-dz-grid-select-all` seam — the controller drives its checked/
        # indeterminate tri-state from the row boxes; the Alpine :checked/
        # :indeterminate bindings are gone.
        html = _render(_build_dispatch_ctx(_RC(_tc(bulk_actions=True)), _Surface()))
        assert "data-dz-grid-select-all" in html
        assert 'aria-label="Select all rows"' in html
        assert ":checked=" not in html
        assert ":indeterminate=" not in html
