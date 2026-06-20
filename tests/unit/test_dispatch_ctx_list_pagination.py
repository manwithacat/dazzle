"""Issue #1029 phase 2 (v0.66.134): regression tests for the LIST
adapter's pagination footer + the new `Pagination` primitive.

Pre-fix, list surfaces with > 20 rows had no way to reach page 2+.
Fix: when `total > page_size`, the adapter appends a `Pagination`
primitive after the `Table` inside the list region body. The
primitive renders the legacy `table_pagination.html` shape — bounded
ellipsis-collapsed page button row + summary."""

from __future__ import annotations

import pytest

from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
from dazzle.render.fragment import URL, FragmentRenderer, Pagination
from dazzle.render.fragment.renderer._helpers import _pagination_pages


class _Surface:
    name = "contact_list"
    title = "Contacts"
    mode = SurfaceMode.LIST
    entity_ref = "Contact"


def _ctx(total: int = 200, page: int = 1, page_size: int = 20) -> dict:
    return {
        "items": [{"id": str(i), "name": f"Item {i}"} for i in range(min(20, total))],
        "columns": [{"key": "name", "label": "Name", "type": "text"}],
        "endpoint": "/api/contacts",
        "total": total,
        "page": page,
        "page_size": page_size,
        "region_name": "contact_table",
        "empty_message": "No contacts yet",
        "create_url": "",
        "detail_url_template": "",
    }


def _render_list(ctx: dict) -> str:
    adapter = FragmentSurfaceAdapter()
    return FragmentRenderer().render(adapter._build_list(_Surface(), ctx))


def test_list_renders_pagination_when_total_exceeds_page_size() -> None:
    """200 rows / 20 per page → 10 pages → pagination row appears."""
    html = _render_list(_ctx(total=200, page=1, page_size=20))
    assert 'class="dz-pagination"' in html
    assert "200 rows" in html


def test_list_omits_pagination_when_total_fits_page() -> None:
    """≤ page_size rows → no pagination shown (single page is dead UX)."""
    html = _render_list(_ctx(total=15, page=1, page_size=20))
    assert "dz-pagination" not in html


def test_list_omits_pagination_when_endpoint_missing() -> None:
    """Without endpoint we can't build hx-get URLs — omit pagination
    rather than emit broken buttons."""
    ctx = _ctx(total=200)
    ctx["endpoint"] = ""
    html = _render_list(ctx)
    assert "dz-pagination" not in html


def test_list_pagination_active_page_marked_aria_current() -> None:
    """The current page button gets `is-current` class + `aria-current="page"`
    for screen-reader accessibility."""
    html = _render_list(_ctx(total=200, page=5, page_size=20))
    assert 'aria-current="page"' in html
    assert "is-current" in html


def test_list_pagination_emits_hx_get_for_each_page() -> None:
    """Each page button has hx-get with page + page_size params,
    targeted at the table region body."""
    html = _render_list(_ctx(total=200, page=5, page_size=20))
    assert "hx-get" in html
    assert "page=4" in html  # window around page 5
    assert "page=6" in html
    assert 'hx-target="#contact_table-body"' in html
    assert 'hx-swap="innerMorph"' in html  # htmx 4 native morph (was morph:innerHTML)


def test_list_pagination_includes_first_and_last_pages() -> None:
    """The bounded page list always includes page 1 and the last page,
    even with ellipses in between (matches `pagination_pages` helper)."""
    html = _render_list(_ctx(total=10000, page=50, page_size=20))
    # Page 1 (first) and page 500 (last) both present.
    assert ">1<" in html
    assert ">500<" in html
    # Window around page 50.
    assert ">49<" in html
    assert ">50<" in html
    assert ">51<" in html


def test_list_pagination_emits_ellipsis_when_total_pages_large() -> None:
    """Many pages → bounded list with ellipsis markers."""
    html = _render_list(_ctx(total=10000, page=50, page_size=20))
    assert "…" in html
    assert 'class="dz-pagination-ellipsis"' in html


# ── Pagination primitive direct tests ──


def test_pagination_primitive_validates_required_fields() -> None:
    """Empty region_name / page < 1 / page_size < 1 / total < 0 raise."""
    with pytest.raises(ValueError, match="region_name"):
        Pagination(region_name="", endpoint=URL("/x"), total=10, page=1, page_size=10)
    with pytest.raises(ValueError, match="page must be >= 1"):
        Pagination(region_name="t", endpoint=URL("/x"), total=10, page=0, page_size=10)
    with pytest.raises(ValueError, match="page_size must be >= 1"):
        Pagination(region_name="t", endpoint=URL("/x"), total=10, page=1, page_size=0)
    with pytest.raises(ValueError, match="total must be >= 0"):
        Pagination(region_name="t", endpoint=URL("/x"), total=-1, page=1, page_size=10)


def test_pagination_primitive_emits_empty_when_total_below_page_size() -> None:
    """total <= page_size → empty string (single page is dead UX)."""
    p = Pagination(region_name="t", endpoint=URL("/api/x"), total=5, page=1, page_size=20)
    assert FragmentRenderer().render(p) == ""


def test_pagination_primitive_extra_query_appended_to_each_page_link() -> None:
    """Phase 5+6 will use `extra_query` to preserve sort/filter/search
    state across page hops. Pin the threading shape now so future
    phases can rely on it."""
    p = Pagination(
        region_name="t",
        endpoint=URL("/api/x"),
        total=100,
        page=2,
        page_size=10,
        extra_query="&sort=name&dir=asc",
    )
    html = FragmentRenderer().render(p)
    # `&` chars are HTML-escaped inside attribute values (`&amp;`).
    # Every page button carries the extra query params.
    assert "&amp;sort=name&amp;dir=asc" in html
    # Multiple buttons, each with the extra params (count >= 5 — enough
    # to confirm threading on multiple buttons).
    assert html.count("&amp;sort=name&amp;dir=asc") >= 5


def test_pagination_pages_helper_bounded() -> None:
    """The `_pagination_pages` helper returns at most 2*window+5 entries
    regardless of total, so the rendered row width is bounded."""
    pages = _pagination_pages(50, 10000, window=2)
    # Max entries: first + ellipsis + 5 (window=2 gives 2*2+1=5) + ellipsis + last = 9
    assert len(pages) <= 9
    assert pages[0] == 1
    assert pages[-1] == 10000


def test_pagination_pages_no_ellipsis_when_total_small() -> None:
    """Small totals (≤ 2*window+5) emit every page without ellipses."""
    pages = _pagination_pages(3, 5, window=2)
    assert pages == [1, 2, 3, 4, 5]
