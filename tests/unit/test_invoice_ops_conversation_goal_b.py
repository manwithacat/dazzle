"""Post-5.8 Goal B conversation — invoice_ops AP discussion on finance desks."""

from __future__ import annotations

import json
from pathlib import Path

from tests.unit.dsl_source_lookup import declaration_block

ROOT = Path(__file__).resolve().parents[2]
ENTITIES = ROOT / "examples/invoice_ops/dsl/entities.dsl"
NOTE_SEEDS = ROOT / "examples/invoice_ops/dsl/seeds/demo_data/InvoiceNote.jsonl"


def test_invoice_note_display_field_is_body() -> None:
    text = ENTITIES.read_text()
    assert "entity InvoiceNote" in text
    assert "display_field: body" in text
    assert "body: text required" in text


def test_finance_desks_declare_live_conversation_spine() -> None:
    # Goal B interesting_product: hero live threads use Message/Bubble chrome
    # (not queue meta) after the HTTP CONVERSATION wire-up.
    for ws in ("finance_ops", "approval_desk", "pay_desk"):
        block = declaration_block("invoice_ops", "workspace", ws)
        assert "live_conversation:" in block
        region = block.split("live_conversation:", 1)[1][:400]
        assert "display: conversation" in region, ws
        assert "source: InvoiceNote" in region


def test_invoice_detail_discussion_uses_conversation_chrome() -> None:
    """Invoice hub Discussion is Message/Bubble trail (not queue meta) — cycle 1899."""
    block = declaration_block("invoice_ops", "surface", "invoice_detail")
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
