"""Bulk confirm must not dump generic 'items' for Invoice (oral #220)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.core.project import load_project
from dazzle.http.runtime.page_routes import _build_dispatch_ctx
from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
from dazzle.render.breadcrumbs import (
    clerk_bulk_selection_noun,
    clerk_entity_confirm_noun,
    clerk_entity_noun,
    entity_path_labels_from_spec,
)
from dazzle.render.context import ColumnContext, TableContext
from dazzle.render.fragment import BulkActionToolbar, FragmentRenderer

ACME = Path("examples/acme_billing")
CONTACT = Path("examples/contact_manager")


class _Surface:
    name = "invoice_list"
    title = "Invoices"
    mode = SurfaceMode.LIST
    entity_ref = "Invoice"


class _RC:
    def __init__(self, table: TableContext) -> None:
        self.table = table
        self.form = None
        self.detail = None


def _table(**overrides: object) -> TableContext:
    base: dict = {
        "entity_name": "Invoice",
        "entity_title": "Invoice",
        "title": "Invoices",
        "columns": [ColumnContext(key="number", label="Number")],
        "api_endpoint": "/api/invoices",
        "rows": [{"id": "abc", "number": "INV-1"}],
        "total": 1,
        "bulk_actions": True,
        "bulk_action_names": ["mark_sensitive"],
        "bulk_include_delete": True,
    }
    base.update(overrides)
    return TableContext(**base)


def _render_list(ctx: dict) -> str:
    adapter = FragmentSurfaceAdapter()
    return FragmentRenderer().render(adapter._build_list(_Surface(), ctx))


def test_acme_invoice_bulk_actions_is_live() -> None:
    block = (ACME / "dsl" / "surfaces.dsl").read_text()
    region = block.split("surface invoice_list", 1)[1].split("surface invoice_detail", 1)[0]
    assert "uses entity Invoice" in region
    assert "bulk_actions:" in region


def test_clerk_bulk_selection_noun_splits_pascal_and_catalog() -> None:
    spec = load_project(ACME)
    invoice = next(e for e in spec.domain.entities if e.name == "Invoice")
    assert invoice.title == "Invoice"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_noun("Invoice", labels) == "Invoice"
    assert clerk_entity_confirm_noun("Invoice", labels) == "invoice"
    assert clerk_bulk_selection_noun("Invoice", labels) == "invoices"
    assert clerk_bulk_selection_noun("Invoice") == "invoices"
    assert clerk_bulk_selection_noun("Invoice", labels, plural=False) == "invoice"


def test_clerk_bulk_selection_noun_leftover_invents_no_collection() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_bulk_selection_noun(junk) == "items"
        assert clerk_bulk_selection_noun(junk, plural=False) == "item"


def test_contact_engagement_letter_bulk_noun_is_live() -> None:
    spec = load_project(CONTACT)
    letter = next(e for e in spec.domain.entities if e.name == "EngagementLetter")
    assert letter.title == "Engagement Letter"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_bulk_selection_noun("EngagementLetter", labels) == "engagement letters"


def test_bulk_toolbar_delete_confirm_is_invoices_not_items() -> None:
    html = FragmentRenderer().render(
        BulkActionToolbar(
            endpoint="/api/invoices",
            entity_name="Invoice",
            entity_title="Invoice",
        )
    )
    assert 'hx-confirm="Delete the selected invoices? This cannot be undone."' in html
    assert "Delete the selected items?" not in html
    assert 'invoice<span class="dz-bulk-plural">' in html
    assert 'item<span class="dz-bulk-plural">' not in html


def test_bulk_toolbar_transition_confirm_uses_entity_noun() -> None:
    html = FragmentRenderer().render(
        BulkActionToolbar(
            endpoint="/api/invoices",
            actions=(("mark_sensitive", "Mark Sensitive"),),
            entity_name="Invoice",
            entity_title="Invoice",
        )
    )
    assert "to the selected invoices?" in html
    assert "to the selected items?" not in html


def test_bulk_toolbar_missing_entity_stays_items() -> None:
    html = FragmentRenderer().render(BulkActionToolbar(endpoint="/api/invoices"))
    assert 'hx-confirm="Delete the selected items? This cannot be undone."' in html


def test_bulk_toolbar_leftover_invents_no_collection() -> None:
    html = FragmentRenderer().render(BulkActionToolbar(endpoint="/api/invoices", entity_name="zzz"))
    assert 'hx-confirm="Delete the selected items? This cannot be undone."' in html
    assert "zzz" not in html


def test_list_adapter_bulk_confirm_uses_invoice_noun() -> None:
    table = _table()
    ctx = _build_dispatch_ctx(_RC(table), object())
    html = _render_list(ctx)
    assert 'hx-confirm="Delete the selected invoices? This cannot be undone."' in html
    assert "Delete the selected items?" not in html
    assert "to the selected invoices?" in html
