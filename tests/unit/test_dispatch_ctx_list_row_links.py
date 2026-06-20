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

from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.http.runtime.page_routes import _build_dispatch_ctx
from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
from dazzle.render.context import ColumnContext, TableContext
from dazzle.render.fragment import FragmentRenderer, Table
from dazzle.render.fragment.region._row_links import _resolve_row_links


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


def _render(ctx: dict) -> str:
    adapter = FragmentSurfaceAdapter()
    return FragmentRenderer().render(adapter._build_list(_Surface(), ctx))


def test_dispatch_ctx_threads_detail_url_template() -> None:
    """`_build_dispatch_ctx` exposes `detail_url_template` to the
    adapter — pre-fix it was silently dropped."""
    ctx = _build_dispatch_ctx(_RC(_table(detail_url_template="/contacts/{id}")), object())
    assert ctx["detail_url_template"] == "/contacts/{id}"


def test_dispatch_ctx_omits_detail_url_template_when_unset() -> None:
    """No template on TableContext → empty string (falsy) in ctx so
    the adapter knows to skip row-link wiring."""
    ctx = _build_dispatch_ctx(_RC(_table()), object())
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


def test_renderer_emits_hx_get_per_linked_row() -> None:
    """Each row with a non-None URL becomes
    `<tr hx-get="..." hx-target="body" hx-swap="innerHTML"
    hx-push-url="true" tabindex="0">`."""
    ctx = _build_dispatch_ctx(_RC(_table(detail_url_template="/contacts/{id}")), object())
    html = _render(ctx)
    assert 'hx-get="/contacts/abc-123"' in html
    assert 'hx-get="/contacts/def-456"' in html
    assert 'hx-target="body"' in html
    assert 'hx-push-url="true"' in html
    # Linked rows carry a class so CSS can apply hover/focus styling.
    assert 'class="dz-table__row dz-table__row--linked"' in html


def test_renderer_omits_hx_attrs_when_no_template() -> None:
    """No template → no `hx-get` on any row. Plain table render."""
    ctx = _build_dispatch_ctx(_RC(_table()), object())
    html = _render(ctx)
    assert "hx-get" not in html
    assert "Alice" in html and "Bob" in html


def test_renderer_emits_plain_tr_for_unmappable_row() -> None:
    """Defensive: a row that doesn't have the template's key gets a
    plain `<tr>` instead of crashing."""
    table = TableContext(
        entity_name="X",
        title="X",
        columns=[ColumnContext(key="name", label="Name")],
        api_endpoint="/api/x",
        rows=[
            {"id": "ok", "name": "Mappable"},
            {"slug": "no-id-here", "name": "Unmappable"},
        ],
        total=2,
        detail_url_template="/x/{id}",
    )
    ctx = _build_dispatch_ctx(_RC(table), object())
    html = _render(ctx)
    assert 'hx-get="/x/ok"' in html
    # The unmappable row's <tr> has no hx-get
    assert html.count("hx-get=") == 1
    # Both still appear in the rendered output
    assert "Mappable" in html
    assert "Unmappable" in html


def test_dispatch_ctx_preserves_existing_table_keys() -> None:
    """Phase 1 doesn't break Phase 0 — all the existing ctx keys
    (`items`, `columns`, `endpoint`, `total`, etc.) remain populated."""
    ctx = _build_dispatch_ctx(_RC(_table(detail_url_template="/contacts/{id}")), object())
    assert "items" in ctx
    assert "columns" in ctx
    assert "endpoint" in ctx
    assert "total" in ctx
    assert "page" in ctx
    assert "page_size" in ctx
    assert "region_name" in ctx
    assert "empty_message" in ctx
    assert "create_url" in ctx
