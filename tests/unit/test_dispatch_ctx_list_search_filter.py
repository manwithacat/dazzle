"""Issue #1029 phase 5 (v0.66.137): regression tests for the LIST
adapter's search box + filter bar toolbar.

Pre-fix, list surfaces declaring `search:` or `filter:` blocks in
their `ux:` block rendered nothing — the toolbar primitives existed
but weren't wired into the LIST adapter. Fix: thread `search_enabled`,
`search_fields`, `filter_values`, and per-column `filter_options`
into ctx; adapter composes `SearchBox` (when search is configured)
and `FilterBar` (when any column is `filterable`) prepended to the
list region body."""

from __future__ import annotations

from dazzle.back.runtime.page_routes import _build_dispatch_ctx
from dazzle.back.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.render.context import ColumnContext, TableContext
from dazzle.render.fragment import FragmentRenderer


class _Surface:
    name = "contact_list"
    title = "Contacts"
    mode = SurfaceMode.LIST
    entity_ref = "Contact"


class _RC:
    def __init__(self, table: TableContext) -> None:
        self.table = table
        self.form = None
        self.detail = None


def _table(**overrides) -> TableContext:
    base: dict = {
        "entity_name": "Contact",
        "title": "Contacts",
        "columns": [ColumnContext(key="name", label="Name")],
        "api_endpoint": "/api/contacts",
        "rows": [{"id": "1", "name": "Alice"}],
        "total": 1,
        "table_id": "contact_table",
    }
    base.update(overrides)
    return TableContext(**base)


def _render_list(ctx: dict) -> str:
    adapter = FragmentSurfaceAdapter()
    return FragmentRenderer().render(adapter._build_list(_Surface(), ctx))


# ── Dispatch ctx threading ──


def test_dispatch_ctx_threads_search_and_filter_state() -> None:
    """`search_enabled`, `search_fields`, `filter_values` all reach
    the adapter. Pre-fix only `search_enabled` (default True) was
    accidentally available; everything else was dropped."""
    table = _table(
        search_enabled=True,
        search_fields=["first_name", "last_name", "email"],
        filter_values={"status": "active"},
    )
    ctx = _build_dispatch_ctx(_RC(table), object())
    assert ctx["search_enabled"] is True
    assert ctx["search_fields"] == ["first_name", "last_name", "email"]
    assert ctx["filter_values"] == {"status": "active"}


def test_dispatch_ctx_threads_filterable_column_options() -> None:
    """Per-column `filter_options` flatten from list[dict] to a
    tuple-of-tuples ready for `FilterColumn.options`."""
    table = _table(
        columns=[
            ColumnContext(key="name", label="Name"),
            ColumnContext(
                key="status",
                label="Status",
                filterable=True,
                filter_type="select",
                filter_options=[
                    {"value": "active", "label": "Active"},
                    {"value": "inactive", "label": "Inactive"},
                ],
            ),
        ],
    )
    ctx = _build_dispatch_ctx(_RC(table), object())
    status_col = ctx["columns"][1]
    assert status_col["filterable"] is True
    assert status_col["filter_options"] == [
        ("active", "Active"),
        ("inactive", "Inactive"),
    ]


# ── End-to-end render ──


def test_list_emits_search_box_when_search_configured() -> None:
    """Search-enabled surface with `search_fields` → SearchBox in
    the toolbar pointing at the FTS endpoint."""
    table = _table(
        search_enabled=True,
        search_fields=["first_name", "last_name", "email"],
    )
    ctx = _build_dispatch_ctx(_RC(table), object())
    html = _render_list(ctx)
    assert "/_dazzle/fts/Contact" in html
    assert "contact_table_search" in html


def test_list_omits_search_box_when_search_disabled() -> None:
    """Search-disabled surface → no SearchBox emitted (pure data list)."""
    table = _table(search_enabled=False, search_fields=[])
    ctx = _build_dispatch_ctx(_RC(table), object())
    html = _render_list(ctx)
    assert "/_dazzle/fts/" not in html


def test_list_omits_search_box_when_search_fields_empty() -> None:
    """`search_enabled=True` but no `search_fields` → no SearchBox.
    Defensive — DSL author forgot to declare which fields to search."""
    table = _table(search_enabled=True, search_fields=[])
    ctx = _build_dispatch_ctx(_RC(table), object())
    html = _render_list(ctx)
    assert "/_dazzle/fts/" not in html


def test_list_emits_filter_bar_when_any_column_filterable() -> None:
    """At least one filterable column → FilterBar emitted with that
    column as a select/dropdown. The FilterBar's hx-target hits the
    region's body so changes refresh the list in place."""
    table = _table(
        columns=[
            ColumnContext(key="name", label="Name"),
            ColumnContext(
                key="status",
                label="Status",
                filterable=True,
                filter_type="select",
                filter_options=[
                    {"value": "active", "label": "Active"},
                    {"value": "archived", "label": "Archived"},
                ],
            ),
        ],
    )
    ctx = _build_dispatch_ctx(_RC(table), object())
    html = _render_list(ctx)
    assert "filter-bar" in html or "dz-filter-bar" in html
    # Filter options round-trip into the rendered <select>.
    assert "Active" in html


def test_list_filter_bar_preselects_active_filter_values() -> None:
    """When `filter_values` carries an active value for a column,
    that option is the `selected` one in the rendered <select>."""
    table = _table(
        columns=[
            ColumnContext(key="name", label="Name"),
            ColumnContext(
                key="status",
                label="Status",
                filterable=True,
                filter_type="select",
                filter_options=[
                    {"value": "active", "label": "Active"},
                    {"value": "archived", "label": "Archived"},
                ],
            ),
        ],
        filter_values={"status": "archived"},
    )
    ctx = _build_dispatch_ctx(_RC(table), object())
    html = _render_list(ctx)
    # The active value reaches the selected attribute.
    assert 'value="archived"' in html


def test_list_omits_filter_bar_when_no_filterable_columns() -> None:
    """No `filterable=True` columns → no FilterBar (avoids empty
    toolbar shell)."""
    table = _table(
        columns=[ColumnContext(key="name", label="Name")],
    )
    ctx = _build_dispatch_ctx(_RC(table), object())
    html = _render_list(ctx)
    assert "filter-bar" not in html
    assert "dz-filter-bar" not in html


def test_list_search_and_filter_can_coexist() -> None:
    """Surface with both search AND filterable columns emits both
    primitives; SearchBox first, then FilterBar (the legacy template's
    visual order)."""
    table = _table(
        search_enabled=True,
        search_fields=["name"],
        columns=[
            ColumnContext(
                key="status",
                label="Status",
                filterable=True,
                filter_type="select",
                filter_options=[{"value": "active", "label": "Active"}],
            ),
        ],
        filter_values={},
    )
    ctx = _build_dispatch_ctx(_RC(table), object())
    html = _render_list(ctx)
    search_pos = html.find("/_dazzle/fts/")
    filter_pos = html.find("filter-bar") if "filter-bar" in html else html.find("dz-filter-bar")
    assert search_pos > -1
    assert filter_pos > -1
    assert search_pos < filter_pos


# ── Issue #1205 regression ──


def test_dispatch_ctx_region_name_uses_surface_name_not_table_id() -> None:
    """Issue #1205: `region_name` must match the workspace region
    container id (`region-<surface.name>`), not the renderer's `table_id`
    (which gets a `dt-` prefix). Pre-fix the FilterBar emitted
    `hx-target="#region-dt-device_list"` while the container was
    `#region-device_list` — one-prefix mismatch fired htmx:targetError
    on every filter change."""
    table = _table(table_id="dt-device_list")
    ctx = _build_dispatch_ctx(_RC(table), _Surface())
    # Must prefer the surface name (no `dt-` prefix), not table_id.
    assert ctx["region_name"] == "contact_list"
    assert ctx["region_name"] != "dt-device_list"


def test_dispatch_ctx_region_name_falls_back_to_table_id_without_surface_name() -> None:
    """Defensive: if surface has no name (shouldn't happen in practice),
    we fall back to table_id to preserve pre-fix behaviour rather than
    emitting `region-` with an empty suffix."""
    table = _table(table_id="dt-device_list")
    # object() has no `.name` attribute — fall back to table_id.
    ctx = _build_dispatch_ctx(_RC(table), object())
    assert ctx["region_name"] == "dt-device_list"


def test_list_filter_bar_hx_target_uses_surface_region_id() -> None:
    """End-to-end: rendered FilterBar `hx-target` points at the
    workspace region container (`#region-<surface.name>`), not at the
    renderer's table_id with `dt-` prefix. Closes #1205."""
    table = _table(
        table_id="dt-contact_list",
        columns=[
            ColumnContext(key="name", label="Name"),
            ColumnContext(
                key="status",
                label="Status",
                filterable=True,
                filter_type="select",
                filter_options=[
                    {"value": "active", "label": "Active"},
                    {"value": "archived", "label": "Archived"},
                ],
            ),
        ],
    )
    ctx = _build_dispatch_ctx(_RC(table), _Surface())
    html = _render_list(ctx)
    # FilterBar hx-target must hit the workspace region container.
    assert "#region-contact_list" in html
    assert "#region-dt-contact_list" not in html


def test_list_omits_filter_bar_when_endpoint_missing() -> None:
    """Without `endpoint` we can't build hx-get URLs for the filter
    selects — omit the FilterBar rather than emit broken bindings."""
    table = _table(
        columns=[
            ColumnContext(
                key="status",
                label="Status",
                filterable=True,
                filter_type="select",
                filter_options=[{"value": "active", "label": "Active"}],
            ),
        ],
        api_endpoint="",
    )
    ctx = _build_dispatch_ctx(_RC(table), object())
    html = _render_list(ctx)
    assert "filter-bar" not in html
    assert "dz-filter-bar" not in html
