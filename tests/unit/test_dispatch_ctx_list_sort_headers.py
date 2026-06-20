"""Issue #1029 phase 6 (v0.66.138): regression tests for the LIST
adapter's SortHeader column wiring.

Pre-fix, list-surface column headers were always plain `<th>` strings
with no click-to-sort. Fix: extend `Table.columns` to accept
`str | SortHeader`; per-column `sortable=True` produces a SortHeader
in the columns tuple, the renderer dispatches per-cell. ctx threads
`sort_field` + `sort_dir` so the active column shows its current
direction (▲/▼) and its next-click flips."""

from __future__ import annotations

from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.http.runtime.page_routes import _build_dispatch_ctx
from dazzle.http.runtime.renderers.fragment_adapter import (
    FragmentSurfaceAdapter,
    _build_column_header,
)
from dazzle.render.context import ColumnContext, TableContext
from dazzle.render.fragment import (
    URL,
    FragmentRenderer,
    SortHeader,
    Table,
)


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
        "columns": [
            ColumnContext(key="name", label="Name", sortable=True),
            ColumnContext(key="score", label="Score"),  # not sortable
        ],
        "api_endpoint": "/api/contacts",
        "rows": [{"id": "1", "name": "Alice", "score": 90}],
        "total": 1,
        "table_id": "contact_table",
    }
    base.update(overrides)
    return TableContext(**base)


def _render_list(ctx: dict) -> str:
    adapter = FragmentSurfaceAdapter()
    return FragmentRenderer().render(adapter._build_list(_Surface(), ctx))


# ── Dispatch ctx threading ──


def test_dispatch_ctx_threads_sort_state() -> None:
    """`sort_field` + `sort_dir` reach the adapter so SortHeader can
    wire its current-direction indicator."""
    table = _table(sort_field="name", sort_dir="desc")
    ctx = _build_dispatch_ctx(_RC(table), object())
    assert ctx["sort_field"] == "name"
    assert ctx["sort_dir"] == "desc"


def test_dispatch_ctx_defaults_sort_dir_to_asc() -> None:
    """Unset `sort_dir` defaults to `"asc"` matching the framework
    convention."""
    ctx = _build_dispatch_ctx(_RC(_table()), object())
    assert ctx["sort_dir"] == "asc"


# ── _build_column_header helper ──


def test_build_column_header_returns_sort_header_for_sortable_col() -> None:
    """Sortable column with endpoint + region_name → SortHeader."""
    col = {"key": "name", "label": "Name", "sortable": True}
    h = _build_column_header(
        col=col,
        endpoint="/api/x",
        region_name="r",
        current_sort="",
        current_direction="asc",
    )
    assert isinstance(h, SortHeader)
    assert h.label == "Name"
    assert h.column_key == "name"


def test_build_column_header_returns_string_for_non_sortable_col() -> None:
    """`sortable=False` → plain string label."""
    col = {"key": "name", "label": "Name", "sortable": False}
    h = _build_column_header(
        col=col,
        endpoint="/api/x",
        region_name="r",
        current_sort="",
        current_direction="asc",
    )
    assert h == "Name"


def test_build_column_header_falls_back_when_endpoint_missing() -> None:
    """Without endpoint we can't build hx-get URLs — defensive
    fallback to plain string."""
    col = {"key": "name", "label": "Name", "sortable": True}
    h = _build_column_header(
        col=col,
        endpoint="",
        region_name="r",
        current_sort="",
        current_direction="asc",
    )
    assert h == "Name"


def test_build_column_header_threads_current_sort_state() -> None:
    """When the column is the active sort, `current_sort` matches
    its key and `current_direction` reflects state."""
    col = {"key": "name", "label": "Name", "sortable": True}
    h = _build_column_header(
        col=col,
        endpoint="/api/x",
        region_name="r",
        current_sort="name",
        current_direction="desc",
    )
    assert isinstance(h, SortHeader)
    assert h.current_sort == "name"
    assert h.current_direction == "desc"


# ── Table primitive accepts mixed columns ──


def test_table_accepts_sort_header_in_columns_tuple() -> None:
    """`Table.columns` is now `tuple[str | SortHeader, ...]` —
    backwards-compatible with the legacy str-only shape."""
    sh = SortHeader(
        label="Name",
        column_key="name",
        endpoint=URL("/api/x"),
        region_name="r",
    )
    t = Table(
        columns=(sh, "Score"),
        rows=(("Alice", "90"),),
    )
    assert isinstance(t.columns[0], SortHeader)
    assert t.columns[1] == "Score"


def test_renderer_emits_sort_header_inside_th_for_sortable_columns() -> None:
    """The renderer wraps each SortHeader in `<th>{...}</th>` while
    plain string columns stay as `<th>{label}</th>`."""
    sh = SortHeader(
        label="Name",
        column_key="name",
        endpoint=URL("/api/x"),
        region_name="r",
    )
    t = Table(columns=(sh, "Score"), rows=(("Alice", "90"),))
    html = FragmentRenderer().render(t)
    # Both wrapped in <th>.
    assert html.count("<th>") == 2
    # SortHeader's link emits hx-get + sort param.
    assert "sort=name" in html
    # Plain string column stays plain.
    assert "<th>Score</th>" in html


# ── End-to-end ──


def test_list_renders_sort_header_for_sortable_column_only() -> None:
    """End-to-end: sortable=True column → SortHeader in the header
    row; sortable=False column → plain `<th>` label."""
    table = _table()
    ctx = _build_dispatch_ctx(_RC(table), object())
    html = _render_list(ctx)
    # Sortable Name column has hx-get with sort param.
    assert "sort=name" in html
    # Non-sortable Score column stays plain.
    assert "<th>Score</th>" in html


def test_list_active_sort_column_carries_current_direction() -> None:
    """When `sort_field == column_key`, the SortHeader's
    `current_direction` reflects the active state — affects the
    direction indicator + next-click direction flip."""
    table = _table(sort_field="name", sort_dir="desc")
    ctx = _build_dispatch_ctx(_RC(table), object())
    html = _render_list(ctx)
    # Active descending sort: next click should ask for asc.
    assert "dir=asc" in html


def test_list_with_no_sortable_columns_emits_plain_headers() -> None:
    """List of all-non-sortable columns renders the legacy plain
    `<th>` shape — no sort affordance noise."""
    table = _table(
        columns=[ColumnContext(key="name", label="Name", sortable=False)],
    )
    ctx = _build_dispatch_ctx(_RC(table), object())
    html = _render_list(ctx)
    assert "<th>Name</th>" in html
    assert "sort=" not in html
