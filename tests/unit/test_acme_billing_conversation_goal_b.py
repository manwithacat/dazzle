"""Post-5.8 Goal B conversation — acme_billing invoice notes on billing desks."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTITIES = ROOT / "examples/acme_billing/dsl/entities.dsl"
SURFACES = ROOT / "examples/acme_billing/dsl/surfaces.dsl"
NOTE_SEEDS = ROOT / "examples/acme_billing/dsl/seeds/demo_data/InvoiceNote.jsonl"


def test_invoice_note_display_field_is_body() -> None:
    text = ENTITIES.read_text()
    assert "entity InvoiceNote" in text
    assert "display_field: body" in text
    assert "body: text required" in text


def test_billing_desks_declare_live_conversation_spine() -> None:
    text = SURFACES.read_text()
    assert 'workspace billing "Acme Billing"' in text
    assert 'workspace invoices_home "Invoices"' in text
    assert "live_conversation:" in text
    assert "source: InvoiceNote" in text
    assert "conversation: count(InvoiceNote)" in text
    assert "focus: live_conversation" in text


def test_invoice_note_seeds_have_domain_true_billing_copy() -> None:
    rows = [json.loads(line) for line in NOTE_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 10
    for row in rows:
        body = str(row.get("body") or "")
        assert len(body) >= 24, body
        assert " " in body
