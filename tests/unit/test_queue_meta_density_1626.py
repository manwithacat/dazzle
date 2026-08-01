"""#1626 — queue rows surface amount/supplier meta, not title-only cards."""

from __future__ import annotations

from pathlib import Path

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


def test_format_queue_meta_never_emits_dict_or_uuid_repr() -> None:
    """#1626 T1 — device/entity FK dicts must not leak Python repr into chrome."""
    from uuid import UUID

    raw = {"id": UUID("d1000000-0000-4000-8000-000000000001"), "name": "FT-PROBE-A12"}
    out = _format_queue_meta_value(raw, {"type": "ref", "key": "device_id", "label": "Device"})
    assert out == "FT-PROBE-A12"
    assert "UUID(" not in out
    assert "{'id'" not in out
    assert '{"id"' not in out


def test_format_queue_meta_id_only_dict_is_clean_uuid_string() -> None:
    from uuid import UUID

    uid = UUID("d1000000-0000-4000-8000-000000000002")
    out = _format_queue_meta_value(
        {"id": uid}, {"type": "ref", "key": "device_id", "label": "Device"}
    )
    assert out == str(uid)
    assert "UUID(" not in out
    assert "{" not in out


def test_queue_meta_prefers_display_when_dict_is_id_only() -> None:
    """Id-only join + device_display must surface story code, not UUID dict."""
    from uuid import UUID

    from dazzle.render.fragment.region._builders_tables import _queue_row_meta_columns

    item = {
        "id": "iss-1",
        "title": "Probe drift",
        "status": "open",
        "device_id": {"id": UUID("d1000000-0000-4000-8000-000000000001")},
        "device_id_display": "FT-PROBE-A12",
    }
    cols = [
        {"key": "title", "label": "Title", "type": "text"},
        {"key": "status", "label": "Status", "type": "badge"},
        {"key": "device_id", "label": "Device", "type": "ref", "ref_entity": "Device"},
    ]
    meta = _queue_row_meta_columns(item, cols, display_key="title", queue_status_field="status")
    by_label = {m.label: m.value for m in meta}
    assert by_label.get("Device") == "FT-PROBE-A12"
    assert "UUID(" not in str(by_label)


def test_queue_meta_named_device_dict_uses_name() -> None:
    from uuid import UUID

    from dazzle.render.fragment.region._builders_tables import _queue_row_meta_columns

    item = {
        "id": "iss-1",
        "title": "Probe drift",
        "status": "open",
        "device_id": {
            "id": UUID("d1000000-0000-4000-8000-000000000001"),
            "name": "FT-SENSOR-NORTH",
        },
    }
    cols = [
        {"key": "title", "label": "Title", "type": "text"},
        {"key": "status", "label": "Status", "type": "badge"},
        {"key": "device_id", "label": "Device", "type": "ref", "ref_entity": "Device"},
    ]
    meta = _queue_row_meta_columns(item, cols, display_key="title", queue_status_field="status")
    by_label = {m.label: m.value for m in meta}
    assert by_label.get("Device") == "FT-SENSOR-NORTH"


def test_queue_meta_folds_currency_into_amount() -> None:
    """#1626 R1 — Amount + Currency columns must not glue as separate chips."""
    from dazzle.render.fragment.region._builders_tables import _queue_row_meta_columns

    item = {
        "invoice_number": "NW-1",
        "amount": 12550.0,
        "currency": "GBP",
        "status": "submitted",
    }
    cols = [
        {"key": "invoice_number", "label": "Number", "type": "text"},
        {"key": "amount", "label": "Amount", "type": "number"},
        {"key": "currency", "label": "Currency", "type": "text"},
        {"key": "status", "label": "Status", "type": "badge"},
    ]
    meta = _queue_row_meta_columns(
        item, cols, display_key="invoice_number", queue_status_field="status"
    )
    labels = [m.label for m in meta]
    assert "Currency" not in labels
    assert "Amount" in labels
    assert meta[0].value.startswith("GBP")
    assert "12,550" in meta[0].value


def test_queue_row_html_joins_meta_chips_with_sep() -> None:
    """#1626 R1 — rendered queue meta chips use mid-dot separators for OCR/humans."""
    # Contract string from _render_tables queue path — keep in lockstep.
    sep = '<span class="dz-queue-row-meta-sep" aria-hidden="true"> · </span>'
    chips = sep.join(
        [
            '<span class="dz-queue-row-meta">Assigned To: Support Agent</span>',
            '<span class="dz-queue-row-date">Created At: 2d ago</span>',
        ]
    )
    assert "dz-queue-row-meta-sep" in chips
    assert " · " in chips
    assert chips.index("Support Agent") < chips.index("meta-sep")
    src = (
        Path(__file__).resolve().parents[2]
        / "src/dazzle/render/fragment/renderer/_render_tables.py"
    ).read_text(encoding="utf-8")
    assert "dz-queue-row-meta-sep" in src


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
