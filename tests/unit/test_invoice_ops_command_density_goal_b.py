"""Post-5.8 Goal B command_density — invoice_ops Pay Desk multi-panel settlement."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SURFACES = ROOT / "examples/invoice_ops/dsl/surfaces.dsl"
INVOICE_SEEDS = ROOT / "examples/invoice_ops/dsl/seeds/demo_data/Invoice.jsonl"

PAY_FOCUS = (
    "focus: settle_metrics, draft_invoice_queue, awaiting_approval_queue, document_pulse, "
    "draft_packets, settle_rail, match_evidence, compliance_drafts, composition, "
    "ready_to_pay, past_due"
)


def _pay_desk_block() -> str:
    text = SURFACES.read_text()
    start = text.index('workspace pay_desk "Pay Desk":')
    end = text.index('workspace audit_review "Audit Review":', start)
    return text[start:end]


def test_pay_desk_declares_dual_attention_before_conversation() -> None:
    """Peer AP settle homes put packets + ≥2 attention panels above the note trail.

    Cycle 2055: due_stage_density splits soft on-time ready vs hard past-due approved.
    """
    block = _pay_desk_block()
    assert "settle_metrics:" in block
    assert "document_pulse:" in block
    assert "ready_to_pay:" in block
    assert "past_due:" in block
    assert "disputed_queue:" in block
    assert "composition:" in block
    assert "live_conversation:" in block
    # Order: metrics → document pulse → intake stages → packets → composition → soft ready → hard past-due → disputes → conversation.
    # Use region markers so metric aggregate lines (past_due: count(...)) do not win index().
    assert "draft_invoice_queue:" in block
    assert "awaiting_approval_queue:" in block
    assert block.index("\n  settle_metrics:\n") < block.index("\n  draft_invoice_queue:\n")
    assert block.index("\n  draft_invoice_queue:\n") < block.index("\n  awaiting_approval_queue:\n")
    assert block.index("\n  awaiting_approval_queue:\n") < block.index("\n  document_pulse:\n")
    assert block.index("\n  document_pulse:\n") < block.index("\n  draft_packets:\n")
    assert block.index("\n  draft_packets:\n") < block.index("\n  composition:\n")
    assert block.index("\n  composition:\n") < block.index("\n  ready_to_pay:\n")
    assert block.index("\n  ready_to_pay:\n") < block.index("\n  past_due:\n")
    assert block.index("\n  past_due:\n") < block.index("\n  disputed_queue:\n")
    assert block.index("\n  disputed_queue:\n") < block.index("\n  live_conversation:\n")


def test_pay_desk_caps_attention_for_fold_share() -> None:
    block = _pay_desk_block()
    assert "limit: 3" in block
    assert PAY_FOCUS in block
    assert "Multi-panel settlement" in block or "multi-panel" in block.lower()
    assert (
        "intake_stage_density" in block
        or "intake stage density" in block.lower()
        or "draft vs submitted" in block.lower()
        or "due_stage_density" in block
        or "due stage density" in block.lower()
        or "on-time ready vs hard past-due" in block.lower()
    )


def test_pay_desk_metrics_count_ready_disputed_and_conversation() -> None:
    block = _pay_desk_block()
    assert "ready: count(Invoice where status = approved)" in block
    assert "on_time: count(Invoice where status = approved and due_date >= today)" in block
    assert "past_due: count(Invoice where status = approved and due_date < today)" in block
    assert "invoice_draft: count(Invoice where status = draft)" in block
    assert "awaiting_approval: count(Invoice where status = submitted)" in block
    assert "disputed: count(Invoice where status = disputed)" in block
    assert "conversation: count(InvoiceNote)" in block
    assert "documents: count(InvoiceDocument)" in block


def test_due_stage_density_queues_filter_soft_and_hard() -> None:
    """Cycle 2055 recipe due_stage_density — soft on-time vs hard past-due approved dual queues."""
    block = _pay_desk_block()
    soft = block.split("\n  ready_to_pay:\n", 1)[1].split("\n  past_due:", 1)[0]
    hard = block.split("\n  past_due:\n", 1)[1].split("\n  disputed_queue:", 1)[0]
    assert "source: Invoice" in soft
    assert "status = approved" in soft
    assert "due_date >= today" in soft
    assert "display: queue" in soft
    assert "limit: 3" in soft
    assert "source: Invoice" in hard
    assert "status = approved" in hard
    assert "due_date < today" in hard
    assert "display: queue" in hard
    assert "limit: 3" in hard
    # Soft and hard are exclusive stage filters (not OR-combined ready list).
    assert "due_date < today" not in soft
    assert "due_date >= today" not in hard
    # Hard stage is approved-only (not broader open past-due including submitted).
    assert "status != paid" not in hard
    assert "status != rejected" not in hard
    assert "status != draft" not in hard


def test_invoice_seeds_span_due_stages() -> None:
    """Demo seeds need both on-time and past-due approved rows for dual queues."""
    rows = [json.loads(line) for line in INVOICE_SEEDS.read_text().splitlines() if line.strip()]
    approved = [r for r in rows if r.get("status") == "approved" and r.get("due_date")]
    assert len(approved) >= 2, f"expected ≥2 approved with due_date, got {approved}"
    # Parse as YYYY-MM-DD strings; demo "today" is runtime — span past + future calendar dues.
    dues = sorted(str(r["due_date"]) for r in approved)
    assert dues[0] < dues[-1], f"expected spread of due dates for stage density, got {dues}"
    # At least one due before mid-2026 and one after (soft/hard under typical demo today).
    assert any(d <= "2026-08-01" for d in dues), f"need past-due-ish approved seed, got {dues}"
    assert any(d >= "2026-09-01" for d in dues), f"need on-time-ish approved seed, got {dues}"


def test_intake_stage_density_queues_filter_draft_and_submitted() -> None:
    """Cycle 2071 recipe intake_stage_density — exclusive draft vs submitted boards."""
    block = _pay_desk_block()
    soft = block.split("\n  draft_invoice_queue:\n", 1)[1].split("\n  awaiting_approval_queue:", 1)[
        0
    ]
    hard = block.split("\n  awaiting_approval_queue:\n", 1)[1].split("\n  document_pulse:", 1)[0]
    assert "source: Invoice" in soft
    assert "status = draft" in soft
    assert "display: queue" in soft
    assert "limit: 3" in soft
    assert "source: Invoice" in hard
    assert "status = submitted" in hard
    assert "display: queue" in hard
    assert "limit: 3" in hard
    # Exclusive lifecycle stages (not OR-combined open list).
    assert "status = submitted" not in soft
    assert "status = draft" not in hard
    assert "intake_stage_density" in block or "draft vs submitted" in block.lower()


def test_invoice_seeds_span_intake_stages() -> None:
    rows = [json.loads(line) for line in INVOICE_SEEDS.read_text().splitlines() if line.strip()]
    drafts = [r for r in rows if r.get("status") == "draft"]
    submitted = [r for r in rows if r.get("status") == "submitted"]
    assert len(drafts) >= 1, "draft_invoice_queue needs ≥1 draft seed"
    assert len(submitted) >= 1, "awaiting_approval_queue needs ≥1 submitted seed"
