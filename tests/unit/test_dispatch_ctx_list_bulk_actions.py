"""Issue #1029 phase 7 (v0.66.139): regression tests for the LIST
adapter's bulk-actions toolbar + per-row checkboxes — closes #1029.

Pre-fix, list surfaces declaring `bulk_actions: true` rendered no
checkbox column and no bulk-action toolbar. Fix:

  - New `BulkActionToolbar` primitive matching legacy
    `bulk_actions.html` byte-for-byte (Delete + Clear-selection
    buttons, Alpine `@click` bindings to the dzTable controller).
  - `Table.bulk_select` flag + `row_ids` parallel tuple — when set,
    the renderer prepends a select-all `<th>` checkbox to the header
    and a per-row `<td>` checkbox + `data-dz-row-id` attribute on
    each row.
  - `_build_list` checks `ctx["bulk_actions"]`, threads through, and
    prepends the toolbar to the body."""

from __future__ import annotations

import pytest

from dazzle.back.runtime.page_routes import _build_dispatch_ctx
from dazzle.back.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.render.context import ColumnContext, TableContext
from dazzle.render.fragment import (
    BulkActionToolbar,
    FragmentRenderer,
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
        "columns": [ColumnContext(key="name", label="Name")],
        "api_endpoint": "/api/contacts",
        "rows": [
            {"id": "abc", "name": "Alice"},
            {"id": "def", "name": "Bob"},
        ],
        "total": 2,
        "table_id": "contact_table",
    }
    base.update(overrides)
    return TableContext(**base)


def _render_list(ctx: dict) -> str:
    adapter = FragmentSurfaceAdapter()
    return FragmentRenderer().render(adapter._build_list(_Surface(), ctx))


# ── Dispatch ctx threading ──


def test_dispatch_ctx_threads_bulk_actions_flag() -> None:
    """`bulk_actions` boolean reaches the adapter."""
    table = _table(bulk_actions=True)
    ctx = _build_dispatch_ctx(_RC(table), object())
    assert ctx["bulk_actions"] is True


def test_dispatch_ctx_defaults_bulk_actions_to_false() -> None:
    """Unset `bulk_actions` defaults to False — list pages stay
    clean unless the DSL opts in."""
    ctx = _build_dispatch_ctx(_RC(_table()), object())
    assert ctx["bulk_actions"] is False


# ── BulkActionToolbar primitive direct ──


def test_bulk_action_toolbar_emits_delete_button() -> None:
    """Delete button binds `@click="bulkDelete()"` and carries the
    bulk-count target span the dzTable controller mirrors."""
    html = FragmentRenderer().render(BulkActionToolbar())
    assert '@click="bulkDelete()"' in html
    assert 'class="dz-bulk-delete"' in html
    assert "data-dz-bulk-count-target" in html


def test_bulk_action_toolbar_emits_clear_selection_button() -> None:
    """Clear-selection button binds `@click="clearSelection()"`."""
    html = FragmentRenderer().render(BulkActionToolbar())
    assert '@click="clearSelection()"' in html
    assert 'class="dz-bulk-clear"' in html
    assert "Clear selection" in html


def test_bulk_action_toolbar_emits_trash_icon_svg() -> None:
    """Trash-icon SVG is inlined verbatim from the legacy template."""
    html = FragmentRenderer().render(BulkActionToolbar())
    assert '<polyline points="3 6 5 6 21 6">' in html


# ── Table primitive bulk_select ──


def test_table_bulk_select_requires_row_ids_with_matching_arity() -> None:
    """`bulk_select=True` + non-empty rows → row_ids length must
    match. Defensive — without ids the per-row checkbox can't bind
    to Alpine `selected.has(id)`."""
    with pytest.raises(ValueError, match="row_ids length"):
        Table(
            columns=("Name",),
            rows=(("Alice",), ("Bob",)),
            bulk_select=True,
            row_ids=("abc",),  # arity mismatch
        )


def test_table_bulk_select_default_disabled() -> None:
    """Backwards-compat: `bulk_select` default is False, row_ids
    default empty — legacy callers continue to work."""
    t = Table(columns=("A",), rows=(("v",),))
    assert t.bulk_select is False
    assert t.row_ids == ()


def test_table_bulk_select_emits_select_all_th_and_per_row_checkbox() -> None:
    """End-to-end at primitive level: bulk_select adds the select-all
    header cell + a per-row checkbox + data-dz-row-id on each row."""
    t = Table(
        columns=("Name",),
        rows=(("Alice",), ("Bob",)),
        bulk_select=True,
        row_ids=("abc", "def"),
    )
    html = FragmentRenderer().render(t)
    # Select-all header cell.
    assert 'class="dz-table-th-select"' in html
    assert '@change="toggleSelectAll($event.target.checked)"' in html
    # Per-row checkbox cells with Alpine bindings.
    assert html.count('class="dz-tr-checkbox"') == 2
    assert "@change=\"toggleRow('abc')\"" in html
    assert "@change=\"toggleRow('def')\"" in html
    # data-dz-row-id on each <tr> for the dzTable count selector.
    assert 'data-dz-row-id="abc"' in html
    assert 'data-dz-row-id="def"' in html


def test_table_bulk_select_off_emits_no_checkbox_or_row_id() -> None:
    """Bulk-select off → no checkbox column, no data-dz-row-id."""
    t = Table(columns=("Name",), rows=(("Alice",),))
    html = FragmentRenderer().render(t)
    assert "dz-tr-checkbox" not in html
    assert "data-dz-row-id" not in html
    assert "toggleSelectAll" not in html


# ── End-to-end LIST adapter ──


def test_list_renders_bulk_toolbar_and_checkboxes_when_bulk_actions_on() -> None:
    """Surface with `bulk_actions: true` renders the toolbar + the
    per-row checkboxes + select-all header."""
    table = _table(bulk_actions=True)
    ctx = _build_dispatch_ctx(_RC(table), object())
    html = _render_list(ctx)
    assert "dz-bulk-actions" in html
    assert '@click="bulkDelete()"' in html
    assert "dz-tr-checkbox" in html
    assert "dz-table-th-select" in html
    assert 'data-dz-row-id="abc"' in html


def test_list_omits_bulk_toolbar_when_bulk_actions_off() -> None:
    """`bulk_actions: false` (or unset) → no toolbar, no checkboxes,
    no row ids. List stays clean."""
    table = _table(bulk_actions=False)
    ctx = _build_dispatch_ctx(_RC(table), object())
    html = _render_list(ctx)
    assert "dz-bulk-actions" not in html
    assert "dz-tr-checkbox" not in html
    assert "data-dz-row-id" not in html


def test_list_omits_bulk_toolbar_when_no_items() -> None:
    """Empty list with bulk_actions still on → no bulk toolbar
    (nothing to bulk-act on; the empty-state copy is the only body)."""
    table = _table(bulk_actions=True, rows=[], total=0)
    ctx = _build_dispatch_ctx(_RC(table), object())
    html = _render_list(ctx)
    assert "dz-bulk-actions" not in html
