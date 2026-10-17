"""Issue #1029 phase 1 (v0.66.133): regression tests for row-click
drill-down on the LIST adapter.

Pre-fix, the Fragment LIST adapter rendered a static `<table>` with
no per-row navigation — 55 cyfuture list surfaces had no way to
drill into a record. Fix: thread `detail_url_template` through the
dispatch ctx, extend `Table` with optional `row_links` tuple,
adapter resolves per-row URLs and the renderer emits each row as
an htmx-driven `<tr hx-get="…">`."""

from __future__ import annotations

import pytest

from dazzle.render.context import ColumnContext, TableContext
from dazzle.render.fragment import Table
from dazzle.render.fragment.region._row_links import _resolve_row_links
from tests.unit.helpers.list_surface import list_ctx, render_list


def _table(detail_url_template: str = "") -> TableContext:
    return TableContext(
        entity_name="Contact",
        title="Contacts",
        columns=[
            ColumnContext(key="first_name", label="First Name"),
            ColumnContext(key="last_name", label="Last Name"),
        ],
        api_endpoint="/api/contacts",
        rows=[
            {"id": "abc-123", "first_name": "Alice", "last_name": "Smith"},
            {"id": "def-456", "first_name": "Bob", "last_name": "Jones"},
        ],
        total=2,
        detail_url_template=detail_url_template or None,
    )


def test_dispatch_ctx_threads_detail_url_template() -> None:
    """`_build_dispatch_ctx` exposes `detail_url_template` to the
    adapter — pre-fix it was silently dropped."""
    ctx = list_ctx(_table(detail_url_template="/contacts/{id}"), object())
    assert ctx["detail_url_template"] == "/contacts/{id}"


def test_dispatch_ctx_omits_detail_url_template_when_unset() -> None:
    """No template on TableContext → empty string (falsy) in ctx so
    the adapter knows to skip row-link wiring."""
    ctx = list_ctx(_table(), object())
    assert ctx["detail_url_template"] == ""


def test_resolve_row_links_substitutes_named_placeholders() -> None:
    """`{id}` placeholder substitution from each item dict."""
    items = [{"id": "uuid-1", "name": "Alice"}, {"id": "uuid-2", "name": "Bob"}]
    links = _resolve_row_links(items, "/contacts/{id}")
    assert links == ("/contacts/uuid-1", "/contacts/uuid-2")


def test_resolve_row_links_supports_non_id_placeholders() -> None:
    """Templates may use `{slug}`, `{code}`, or any item-key — not
    just `{id}`."""
    items = [{"slug": "first-record", "code": "C001"}]
    links = _resolve_row_links(items, "/items/{slug}/{code}")
    assert links == ("/items/first-record/C001",)


def test_resolve_row_links_emits_none_for_missing_key() -> None:
    """Defensive: a row missing a key referenced by the template
    yields `None` — the renderer then emits a plain `<tr>` for that
    row instead of crashing."""
    items = [{"id": "ok"}, {"slug": "no-id"}]
    links = _resolve_row_links(items, "/contacts/{id}")
    assert links == ("/contacts/ok", None)


def test_resolve_row_links_empty_template_returns_empty_tuple() -> None:
    """Defensive — caller short-circuits before this, but cover it
    explicitly for safety."""
    assert _resolve_row_links([{"id": "x"}], "") == ()


def test_table_primitive_rejects_row_links_arity_mismatch() -> None:
    """`row_links` length must match `rows` length when set —
    otherwise the renderer would silently misalign URLs to rows."""
    with pytest.raises(ValueError, match="row_links length"):
        Table(
            columns=("a",),
            rows=(("v1",), ("v2",)),
            row_links=("/a", "/b", "/c"),  # 3 != 2
        )


def test_table_primitive_accepts_empty_row_links() -> None:
    """Empty `row_links` tuple is the legacy-shape default — backwards-
    compatible."""
    t = Table(columns=("a",), rows=(("v1",),))
    assert t.row_links == ()


# ── Canonical model (ADR-0049 Phase 1 Task 4e) ───────────────────────────
# `_build_list` no longer renders rows inline — the list first-paints a
# skeleton tbody that hydrates from /api, where `render_data_row` owns the
# per-row drill (covered by tests/unit/test_data_row_characterization_1505.py,
# the "drill" case). The `_resolve_row_links` helper above is unchanged and
# still exercised directly; only `_build_list`'s inline-drill rendering is gone.


def test_list_skeleton_hydrates_rows_from_api_not_inline() -> None:
    """Rows come from /api (render_data_row), not inline — so the first paint
    is a skeleton tbody pointing at the row-data endpoint, with no inline
    `<tr>` drill rows and no row data inlined."""
    ctx = list_ctx(_table(detail_url_template="/contacts/{id}"), object())
    html = render_list(ctx)
    # the empty hydrating tbody points at the row-data endpoint
    assert 'class="dz-table-body"' in html
    assert 'hx-get="/api/contacts' in html
    # Convergence C1.1: the tbody is the grid controller's body seam —
    # dz-grid:refresh always joins the load trigger.
    assert 'hx-trigger="load, dz-grid:refresh"' in html
    # no inline data rows / per-row drill at first paint
    assert 'data-dz-list-kind="embedded"' not in html
    assert "Alice" not in html
    assert "Bob" not in html


def test_dispatch_ctx_preserves_existing_table_keys() -> None:
    """Phase 1 doesn't break Phase 0 — all the existing ctx keys
    (`items`, `columns`, `endpoint`, `total`, etc.) remain populated."""
    ctx = list_ctx(_table(detail_url_template="/contacts/{id}"), object())
    assert "items" in ctx
    assert "columns" in ctx
    assert "endpoint" in ctx
    assert "total" in ctx
    assert "page" in ctx
    assert "page_size" in ctx
    assert "region_name" in ctx
    assert "empty_message" in ctx
    assert "create_url" in ctx
