"""Post-5.8 Goal B document — invoice_ops named AP packets + line composition."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTITIES = ROOT / "examples/invoice_ops/dsl/entities.dsl"
SURFACES = ROOT / "examples/invoice_ops/dsl/surfaces.dsl"
LINE_SEEDS = ROOT / "examples/invoice_ops/dsl/seeds/demo_data/LineItem.jsonl"
DOC_SEEDS = ROOT / "examples/invoice_ops/dsl/seeds/demo_data/InvoiceDocument.jsonl"


def _workspace_block(name: str) -> str:
    text = SURFACES.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        return text[start:]
    return text[start : start + 1 + nxt]


def test_line_item_display_field_is_description() -> None:
    text = ENTITIES.read_text()
    assert 'entity LineItem "Line Item"' in text
    assert "display_field: description" in text
    assert "description: str(200) required" in text
    # finance_admin must list/read composition on finance_ops home
    assert "role(finance_admin)" in text
    assert "finance_admin, auditor, tenant_admin" in text or "finance_admin" in text


def test_invoice_document_entity_is_named_packet_composition() -> None:
    text = ENTITIES.read_text()
    assert 'entity InvoiceDocument "Invoice Document"' in text
    assert "display_field: headline" in text
    assert "headline: str(200) required" in text
    assert (
        "doc_kind: enum[remittance, credit_memo, po_packet, tax_certificate, "
        "payment_confirmation]=remittance" in text
    )
    assert "status: enum[draft, published, archived]=draft" in text
    assert "draft -> published:" in text
    assert "published -> archived:" in text


def test_ops_and_requester_homes_declare_document_composition() -> None:
    """Goal B document: named packets on finance_ops; lines on my_invoices + desk."""
    text = SURFACES.read_text()
    assert "workspace finance_ops" in text
    assert "workspace my_invoices" in text
    assert "workspace line_items_desk" in text
    assert "document_pulse:" in text

    ops = _workspace_block("finance_ops")
    assert "source: InvoiceDocument" in ops
    assert "documents: count(InvoiceDocument)" in ops
    assert "action: invoice_document_detail" in ops
    assert "line_composition:" in ops
    # Order: document pulse → named packets → dual attention → lines → conversation
    assert ops.index("document_pulse:") < ops.index("composition:")
    assert ops.index("composition:") < ops.index("awaiting_approval:")
    assert ops.index("awaiting_approval:") < ops.index("line_composition:")
    assert ops.index("line_composition:") < ops.index("live_conversation:")
    assert (
        "focus: ops_metrics, document_pulse, composition, awaiting_approval, "
        "ready_to_pay, line_composition, live_conversation" in ops
    )

    # Dedicated composition desk still presents LineItem body
    assert "source: LineItem" in text.split("workspace line_items_desk", 1)[1]
    assert "source: LineItem" in text.split("workspace my_invoices", 1)[1]


def test_invoice_document_list_dual_open_and_invoice_hub() -> None:
    text = SURFACES.read_text()
    assert 'surface invoice_document_list "Invoice Documents"' in text
    assert "open: InvoiceDocument via id | Invoice via invoice" in text
    assert 'surface invoice_document_detail "Invoice Document"' in text
    assert 'related documents "Documents"' in text
    assert "show: InvoiceDocument" in text


def test_line_item_seeds_are_domain_true_descriptions() -> None:
    rows = [json.loads(line) for line in LINE_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 12, "Goal B document expects composition lines across invoices"
    for row in rows:
        desc = str(row["description"])
        assert len(desc) >= 12, desc
        assert " " in desc, f"line description should be human prose, not slug: {desc}"
        assert int(row["quantity"]) >= 1
        assert float(row["unit_amount"]) > 0


def test_invoice_document_seeds_are_domain_true_headlines() -> None:
    rows = [json.loads(line) for line in DOC_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 8, "Goal B document expects named packets across invoices"
    kinds: set[str] = set()
    statuses: set[str] = set()
    invoice_ids = {
        "3c000000-0000-4000-8000-000000000001",
        "3c000000-0000-4000-8000-000000000002",
        "3c000000-0000-4000-8000-000000000003",
        "3c000000-0000-4000-8000-000000000004",
        "3c000000-0000-4000-8000-000000000005",
    }
    for row in rows:
        headline = str(row["headline"])
        assert len(headline) >= 16, headline
        assert " " in headline, f"headline should be human prose, not slug: {headline}"
        assert str(row["invoice"]) in invoice_ids
        assert str(row["id"]).startswith("3f000000-")
        assert len(str(row.get("body") or "")) >= 24
        kinds.add(row["doc_kind"])
        statuses.add(row["status"])
    assert kinds >= {
        "remittance",
        "credit_memo",
        "po_packet",
        "tax_certificate",
        "payment_confirmation",
    }
    assert statuses >= {"draft", "published"}
