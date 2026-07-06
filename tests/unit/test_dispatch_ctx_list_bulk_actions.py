"""Issue #1029 phase 7 (v0.66.139): regression tests for the LIST
adapter's bulk-actions toolbar + per-row checkboxes — closes #1029.

Pre-fix, list surfaces declaring `bulk_actions: true` rendered no
checkbox column and no bulk-action toolbar. Fix:

  - New `BulkActionToolbar` primitive (Delete + Clear-selection
    buttons). Convergence C1.1: the toolbar now rides the HM grid
    controller's seams (`data-dz-grid-bulk-action` / `data-dz-grid-clear`
    + an hx-post to `{endpoint}/bulk`), not Alpine `@click` bindings.
  - `Table.bulk_select` flag + `row_ids` parallel tuple — when set,
    the renderer prepends a select-all `<th>` checkbox to the header
    and a per-row `<td>` checkbox + `data-dz-row-id` attribute on
    each row.
  - `_build_list` checks `ctx["bulk_actions"]`, threads through, and
    prepends the toolbar to the body."""

from __future__ import annotations

import pytest

from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.http.runtime.page_routes import _build_dispatch_ctx
from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
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
    """Convergence C1.1: Delete rides the HM grid controller —
    `data-dz-grid-bulk-action="delete"` posting to `{endpoint}/bulk` behind
    an hx-confirm, with the bulk-count target span the controller mirrors.
    No Alpine `@click` binding."""
    html = FragmentRenderer().render(BulkActionToolbar(endpoint="/api/contacts"))
    assert 'data-dz-grid-bulk-action="delete"' in html
    assert "data-dz-grid-bulk-refresh" in html
    assert 'hx-post="/api/contacts/bulk"' in html
    assert 'hx-confirm="Delete the selected items? This cannot be undone."' in html
    assert 'class="dz-bulk-delete"' in html
    assert "data-dz-bulk-count-target" in html
    assert '@click="bulkDelete()"' not in html


def test_bulk_action_toolbar_emits_clear_selection_button() -> None:
    """Convergence C1.1: Clear-selection is the grid controller's
    `data-dz-grid-clear` seam — no Alpine `@click` binding."""
    html = FragmentRenderer().render(BulkActionToolbar(endpoint="/api/contacts"))
    assert "data-dz-grid-clear" in html
    assert 'class="dz-bulk-clear"' in html
    assert "Clear selection" in html
    assert '@click="clearSelection()"' not in html


def test_bulk_action_toolbar_emits_trash_icon_svg() -> None:
    """Trash-icon SVG is inlined verbatim from the legacy template."""
    html = FragmentRenderer().render(BulkActionToolbar(endpoint="/api/contacts"))
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
    # Select-all header cell. Convergence C1.1: the select-all box is the HM
    # grid controller's `data-dz-grid-select-all` seam (the controller drives
    # its checked/indeterminate tri-state) — no Alpine bindings.
    assert 'class="dz-table-th-select"' in html
    assert "data-dz-grid-select-all" in html
    assert 'aria-label="Select all rows"' in html
    assert "toggleSelectAll" not in html
    # Per-row checkbox cells on the HM selection seam (C2.4: the Alpine
    # toggleRow/selected bindings retired with the dzTable mount).
    assert html.count('class="dz-tr-checkbox"') == 2
    assert "data-dz-grid-select data-dz-grid-row-id='abc'" in html
    assert "data-dz-grid-select data-dz-grid-row-id='def'" in html
    assert "toggleRow" not in html
    # data-dz-row-id on each <tr> for the grid controller's count selector.
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


def test_list_renders_bulk_toolbar_and_select_all_when_bulk_actions_on() -> None:
    """Canonical (ADR-0049 Task 4e): `bulk_actions: true` first-paints the bulk
    toolbar + the select-all header. The per-row checkboxes + data-dz-row-id are
    emitted by render_data_row on the /api hydrate (covered by the data_row
    characterization 'bulk' case), not inline at first paint."""
    table = _table(bulk_actions=True)
    ctx = _build_dispatch_ctx(_RC(table), object())
    html = _render_list(ctx)
    assert "dz-bulk-actions" in html
    # Convergence C1.1: Delete is the grid controller's bulk seam posting to
    # the entity API base (`{endpoint}/bulk`), not an Alpine @click.
    assert 'data-dz-grid-bulk-action="delete"' in html
    assert 'hx-post="/api/contacts/bulk"' in html
    assert "dz-table-th-select" in html
    # per-row checkboxes are not inlined at first paint (rows come from /api).
    assert "dz-tr-checkbox" not in html
    assert 'data-dz-row-id="' not in html


def test_list_omits_bulk_toolbar_when_bulk_actions_off() -> None:
    """`bulk_actions: false` (or unset) → no toolbar, no checkboxes,
    no row ids. List stays clean."""
    table = _table(bulk_actions=False)
    ctx = _build_dispatch_ctx(_RC(table), object())
    html = _render_list(ctx)
    assert "dz-bulk-actions" not in html
    assert "dz-tr-checkbox" not in html
    assert "data-dz-row-id" not in html


def test_list_keeps_bulk_toolbar_for_empty_list_css_gated() -> None:
    """Canonical: the bulk toolbar + select-all header are emitted whenever
    `bulk_actions` is declared — their visibility is CSS-gated on
    `[data-dz-bulk-count] > 0`, not gated on the first-paint item count (the
    list hydrates rows from /api, so item count is unknown at first paint)."""
    table = _table(bulk_actions=True, rows=[], total=0)
    ctx = _build_dispatch_ctx(_RC(table), object())
    html = _render_list(ctx)
    assert "dz-bulk-actions" in html
    assert "dz-table-th-select" in html
