"""Post-5.8 Goal B command_density — invoice_ops Pay Desk multi-panel settlement."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SURFACES = ROOT / "examples/invoice_ops/dsl/surfaces.dsl"


def _pay_desk_block() -> str:
    text = SURFACES.read_text()
    start = text.index('workspace pay_desk "Pay Desk":')
    end = text.index('workspace audit_review "Audit Review":', start)
    return text[start:end]


def test_pay_desk_declares_dual_attention_before_conversation() -> None:
    """Peer AP settle homes put packets + ≥2 attention panels above the note trail."""
    block = _pay_desk_block()
    assert "settle_metrics:" in block
    assert "document_pulse:" in block
    assert "ready_to_pay:" in block
    assert "disputed_queue:" in block
    assert "composition:" in block
    assert "live_conversation:" in block
    # Order: metrics → document pulse → packets → ready → disputes → conversation.
    assert block.index("settle_metrics:") < block.index("document_pulse:")
    assert block.index("document_pulse:") < block.index("composition:")
    assert block.index("composition:") < block.index("ready_to_pay:")
    assert block.index("ready_to_pay:") < block.index("disputed_queue:")
    assert block.index("disputed_queue:") < block.index("live_conversation:")


def test_pay_desk_caps_attention_for_fold_share() -> None:
    block = _pay_desk_block()
    assert "limit: 3" in block
    assert (
        "focus: settle_metrics, document_pulse, draft_packets, tax_identity, bank_rail, adjustment_rail, settle_rail, match_evidence, compliance_drafts, remittances, form_w9s, packing_slips, "
        "composition, ready_to_pay" in block
    )
    assert "Multi-panel settlement" in block or "multi-panel" in block.lower()


def test_pay_desk_metrics_count_ready_disputed_and_conversation() -> None:
    block = _pay_desk_block()
    assert "ready: count(Invoice where status = approved)" in block
    assert "disputed: count(Invoice where status = disputed)" in block
    assert "documents: count(InvoiceDocument)" in block
    assert "conversation: count(InvoiceNote)" in block
    assert "filter: status = approved" in block
    assert "filter: status = disputed" in block
