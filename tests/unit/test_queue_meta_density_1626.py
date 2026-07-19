"""#1626 — queue rows surface amount/supplier meta, not title-only cards."""

from __future__ import annotations

from dazzle.render.fragment.region._builders_tables import (
    _format_queue_meta_value,
)
from dazzle.render.fragment.region._dispatcher import WorkspaceRegionAdapter


class _FakeRegion:
    name = "awaiting_approval"
    title = "Awaiting approval"
    empty_message = "empty"


def test_format_queue_meta_currency() -> None:
    assert _format_queue_meta_value(1200.5, {"type": "currency", "format": "currency:GBP"}) == (
        "GBP 1,200.50"
    )


def test_queue_row_includes_amount_and_supplier_meta() -> None:
    adapter = WorkspaceRegionAdapter()
    region = _FakeRegion()
    ctx = {
        "items": [
            {
                "id": "inv-1",
                "invoice_number": "INV-1001",
                "amount": 450.0,
                "supplier_display": "Acme Supplies",
                "supplier": "sup-1",
                "status": "submitted",
            }
        ],
        "columns": [
            {"key": "invoice_number", "label": "Number", "type": "text"},
            {"key": "supplier", "label": "Supplier", "type": "text"},
            {
                "key": "amount",
                "label": "Amount",
                "type": "currency",
                "format": "currency:GBP",
            },
            {"key": "status", "label": "Status", "type": "badge"},
        ],
        "total": 1,
        "display_key": "invoice_number",
        "queue_status_field": "status",
        "queue_api_endpoint": "/api/invoices",
        "queue_transitions": [],
        "region_name": "awaiting_approval",
    }
    surface = adapter._build_queue(region, ctx)  # type: ignore[arg-type]
    # Surface → Region → QueueRegion
    queue = surface.body.body
    assert queue.rows
    row = queue.rows[0]
    assert row.title == "INV-1001"
    meta_labels = {m.label: m.value for m in row.meta_columns}
    assert "Supplier" in meta_labels
    assert meta_labels["Supplier"] == "Acme Supplies"
    assert "Amount" in meta_labels
    assert "450" in meta_labels["Amount"] or "450.00" in meta_labels["Amount"]
