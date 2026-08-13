"""Post-5.8 Goal B empty_region_honesty — invoice_ops primary desks (cycle 1820)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SURFACES = ROOT / "examples/invoice_ops/dsl/surfaces.dsl"


def _workspace_block(name: str) -> str:
    text = SURFACES.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        return text[start:]
    return text[start : start + 1 + nxt]


def test_finance_ops_omits_funnel_bar_and_paid_timeline() -> None:
    """Admin home: dual attention + named packets + lines + notes — not chart voids."""
    block = _workspace_block("finance_ops")
    assert "ops_metrics:" in block
    assert "document_pulse:" in block
    assert "composition:" in block
    assert "line_composition:" in block
    assert "live_conversation:" in block
    assert "awaiting_approval:" in block
    assert "ready_to_pay:" in block
    assert "disputed_queue:" in block
    assert "ops_board:" in block
    assert "invoice_pipeline:" not in block
    assert "payment_health:" not in block
    assert "recent_paid:" not in block
    assert "display: bar_chart" not in block
    assert "display: funnel_chart" not in block
    assert "display: timeline" not in block
    assert (
        "focus: packet_covers, ops_metrics, document_pulse, draft_packets, period_close_rail, remediation_rail, closeout_rail, first_pay_rail, dispute_rail, vendor_risk_rail, reconcile_rail, tax_identity, bank_rail, adjustment_rail, settle_rail, match_evidence, "
        "compliance_drafts, remittances, form_w9s, packing_slips, composition, past_due, "
        "awaiting_approval" in block
    )


def test_my_invoices_omits_status_mix_and_trail() -> None:
    """Requester home: composition + queues + kanban — not status chart/trail dumps."""
    block = _workspace_block("my_invoices")
    assert "my_pipeline:" in block
    assert "composition:" in block
    assert "drafts:" in block
    assert "in_flight:" in block
    assert "my_status_board:" in block
    assert "my_status_mix:" not in block
    assert "my_trail:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block
    assert (
        "focus: my_pipeline, document_pulse, composition, drafts, in_flight, my_status_board"
        in block
    )


def test_approval_desk_omits_decision_timeline() -> None:
    """Approver home: queue + named packets + conversation — not recently_decided dump."""
    block = _workspace_block("approval_desk")
    assert "live_conversation:" in block
    assert "awaiting_approval:" in block
    assert "composition:" in block
    assert "approval_board:" in block
    assert "recently_decided:" not in block
    assert "display: timeline" not in block
    assert (
        "focus: approval_load, document_pulse, match_evidence, goods_receipts, po_packets, composition, "
        "awaiting_approval, live_conversation" in block
    )


def test_pay_desk_omits_payment_health_and_dispute_trail() -> None:
    """Settle home: dual attention + packets + conversation — not bar chart / twin trail."""
    block = _workspace_block("pay_desk")
    assert "settle_metrics:" in block
    assert "ready_to_pay:" in block
    assert "disputed_queue:" in block
    assert "composition:" in block
    assert "live_conversation:" in block
    assert "settle_board:" in block
    assert "payment_health:" not in block
    assert "dispute_trail:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block
    assert (
        "focus: settle_metrics, document_pulse, draft_packets, period_close_rail, remediation_rail, closeout_rail, first_pay_rail, dispute_rail, vendor_risk_rail, reconcile_rail, tax_identity, bank_rail, adjustment_rail, settle_rail, match_evidence, compliance_drafts, remittances, form_w9s, packing_slips, "
        "composition, ready_to_pay" in block
    )


def test_invoice_ops_keeps_bar_chart_for_coverage() -> None:
    """Hero prune must not leave display: bar_chart fleet-uncovered in this app."""
    text = SURFACES.read_text()
    assert "display: bar_chart" in text
    assert text.count("display: bar_chart") >= 2
