"""Task 5 pre-flip fix (ADR-0049 Phase 2): substrate detail field-value parity.

The flip review found the substrate detail field values regressed on every
detail page: `ref` rendered the raw UUID (not the display name), `money`/
`currency` rendered raw minor units, `badge` lost the WCAG badge chrome, and
`file` lost the download link. The fix routes detail field values through the
SAME typed-cell core the list rows use (`_render_cell_display`), and threads the
missing ctx fields (type/currency_code/semantic_map + ref `_display`).
"""

from __future__ import annotations

from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.http.runtime.page_routes import _build_dispatch_ctx
from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
from dazzle.render.context import DetailContext, FieldContext
from dazzle.render.fragment import FragmentRenderer


class _Surface:
    name = "task_detail"
    title = "Task"
    mode = SurfaceMode.VIEW
    entity_ref = "Task"
    sections = ()
    related_groups = ()


class _RC:
    def __init__(self, detail: DetailContext) -> None:
        self.table = None
        self.form = None
        self.detail = detail


def _render(fields: list[FieldContext], item: dict) -> str:
    detail = DetailContext(entity_name="Task", title="T", fields=fields, item=item)
    ctx = _build_dispatch_ctx(_RC(detail), _Surface())
    return FragmentRenderer().render(FragmentSurfaceAdapter()._build_view(_Surface(), ctx))


def test_badge_field_renders_wcag_badge() -> None:
    html = _render(
        [FieldContext(name="status", label="Status", type="badge")],
        {"id": "a", "status": "open"},
    )
    assert 'class="dz-badge"' in html
    assert "data-dz-tone=" in html
    assert 'role="status"' in html
    assert "Open" in html


def test_currency_field_renders_formatted() -> None:
    html = _render(
        [
            FieldContext(
                name="amount", label="Amount", type="currency", extra={"currency_code": "USD"}
            )
        ],
        {"id": "a", "amount": 12345},
    )
    # 12345 minor units → $123.45 (not the raw integer)
    assert "123.45" in html
    assert "12345" not in html.split("Amount")[-1][:200]


def test_bool_field_renders_icon_not_text() -> None:
    html = _render(
        [FieldContext(name="done", label="Done", type="bool")],
        {"id": "a", "done": True},
    )
    # _bool_icon_filter returns an icon glyph, not the word "True"
    assert "True" not in html
    assert "Yes" not in html


def test_ref_field_renders_display_name_not_uuid() -> None:
    html = _render(
        [FieldContext(name="owner", label="Owner", type="ref")],
        {"id": "a", "owner": "uuid-999", "owner_display": "Alice Smith"},
    )
    assert "Alice Smith" in html
    assert "uuid-999" not in html


def test_file_field_renders_download_link() -> None:
    html = _render(
        [FieldContext(name="attachment", label="File", type="file")],
        {"id": "a", "attachment": "https://x/report.pdf"},
    )
    assert 'href="https://x/report.pdf"' in html
    assert 'target="_blank"' in html
    assert "report.pdf" in html


def test_money_kind_field_renders_formatted() -> None:
    html = _render(
        [FieldContext(name="price", label="Price", type="money", extra={"currency_code": "GBP"})],
        {"id": "a", "price": 9900},
    )
    assert "99.00" in html  # 9900 minor units → £99.00
