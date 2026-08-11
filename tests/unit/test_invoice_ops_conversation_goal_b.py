"""Post-5.8 Goal B conversation — invoice_ops AP discussion on finance desks."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTITIES = ROOT / "examples/invoice_ops/dsl/entities.dsl"
SURFACES = ROOT / "examples/invoice_ops/dsl/surfaces.dsl"
NOTE_SEEDS = ROOT / "examples/invoice_ops/dsl/seeds/demo_data/InvoiceNote.jsonl"


def test_invoice_note_display_field_is_body() -> None:
    text = ENTITIES.read_text()
    assert "entity InvoiceNote" in text
    assert "display_field: body" in text
    assert "body: text required" in text


def test_finance_desks_declare_live_conversation_spine() -> None:
    text = SURFACES.read_text()
    assert "workspace finance_ops" in text
    assert "workspace approval_desk" in text
    assert "workspace pay_desk" in text
    assert "live_conversation:" in text
    assert "source: InvoiceNote" in text
    assert "conversation: count(InvoiceNote)" in text
    # Goal B interesting_product: hero live threads use Message/Bubble chrome
    # (not queue meta) after the HTTP CONVERSATION wire-up.
    for ws in ("finance_ops", "approval_desk", "pay_desk"):
        block = text.split(f"workspace {ws}", 1)[1]
        region = block.split("live_conversation:", 1)[1][:400]
        assert "display: conversation" in region, ws
        assert "source: InvoiceNote" in region


def test_invoice_detail_discussion_uses_conversation_chrome() -> None:
    """Invoice hub Discussion is Message/Bubble trail (not queue meta) — cycle 1899."""
    text = SURFACES.read_text()
    assert 'surface invoice_detail "Invoice"' in text
    block = text.split('surface invoice_detail "Invoice"', 1)[1]
    block = block.split("surface invoice_create", 1)[0]
    related = block.split('related discussion "Discussion"', 1)[1][:240]
    assert "display: conversation" in related
    assert "show: InvoiceNote" in related
    assert "columns: body, author, created_at" in related
    assert "display: queue" not in related


def test_invoice_note_seeds_have_domain_true_ap_copy() -> None:
    rows = [json.loads(line) for line in NOTE_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 10
    for row in rows:
        body = str(row.get("body") or "")
        assert len(body) >= 24, body
        assert " " in body
