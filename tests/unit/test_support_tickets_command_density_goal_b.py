"""Post-5.8 Goal B command_density — support_tickets Manager Ops dual attention + SLA stages."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/support_tickets/dsl/app.dsl"
TICKET_SEEDS = ROOT / "examples/support_tickets/dsl/seeds/demo_data/Ticket.jsonl"

MANAGER_FOCUS = (
    "focus: media_shelf, team_metrics, at_risk_queue, breached_queue, critical_queue, "
    "unassigned_queue, needs_reply, medium_needs_reply, priority_needs_reply, priority_awaiting_customer, "
    "breach_awaiting_customer, breach_needs_reply, thankful_needs_reply, thankful_awaiting_customer, "
    "portal_awaiting_customer, phone_awaiting_customer, chat_awaiting_customer, email_awaiting_customer, "
    "critical_awaiting_customer, raised_awaiting_customer, frustrated_awaiting_customer, live_conversation"
)


def _manager_ops_block() -> str:
    text = APP.read_text()
    start = text.index('workspace manager_ops "Manager Ops":')
    end = text.index("workspace agent_dashboard", start)
    return text[start:end]


def test_manager_ops_declares_dual_attention_before_conversation() -> None:
    """Peer support ops homes put ≥2 attention panels above a conversation trail.

    Goal B document: composition sits after dual attention, before conversation.
    Cycle 1913: live sla_state pressure joined dual attention before critical.
    Cycle 2054: sla_stage_density splits soft at-risk vs hard breached before priority queues.
    """
    block = _manager_ops_block()
    assert "team_metrics:" in block
    assert "sla_readiness:" in block
    assert "at_risk_queue:" in block
    assert "breached_queue:" in block
    assert "critical_queue:" in block
    assert "unassigned_queue:" in block
    assert "composition:" in block
    assert "live_conversation:" in block
    # Order: metrics → soft at-risk → hard breached → readiness → critical → unassigned → composition → conversation.
    assert block.index("team_metrics:") < block.index("at_risk_queue:")
    assert block.index("at_risk_queue:") < block.index("breached_queue:")
    assert block.index("breached_queue:") < block.index("sla_readiness:")
    assert block.index("sla_readiness:") < block.index("critical_queue:")
    assert block.index("critical_queue:") < block.index("unassigned_queue:")
    assert block.index("unassigned_queue:") < block.index("composition:")
    assert block.index("composition:") < block.index("live_conversation:")
    # Combined breach_risk list retired in favor of stage density.
    assert "breach_risk:" not in block


def test_manager_ops_caps_attention_queues_for_fold_share() -> None:
    block = _manager_ops_block()
    # Caps keep dual panels + composition + conversation sharing the fold.
    assert "limit: 4" in block
    assert MANAGER_FOCUS in block
    assert "Multi-panel support ops" in block or "multi-panel" in block.lower()
    assert (
        "sla_stage_density" in block
        or "SLA stage density" in block
        or "at-risk vs breached" in block.lower()
    )


def test_manager_ops_metrics_count_critical_unassigned_and_sla_pressure() -> None:
    block = _manager_ops_block()
    assert "critical_open: count(Ticket where priority = critical" in block
    assert "unassigned: count(Ticket where assigned_to = null and status = open)" in block
    assert "at_risk: count(Ticket where sla_state = at_risk and status != closed)" in block
    assert "breached: count(Ticket where sla_state = breached and status != closed)" in block
    assert "conversation: count(Comment)" in block
    assert "documents: count(SlaWaiver)" in block


def test_ticket_entity_declares_sla_state() -> None:
    text = APP.read_text()
    start = text.index('entity Ticket "Support Ticket":')
    end = text.index('entity Comment "Comment":', start)
    block = text[start:end]
    assert "sla_state: enum[on_track,at_risk,breached]=on_track" in block
    assert "sla_state" in block.split("repr_fields:")[1].split("]")[0]


def test_sla_stage_density_queues_filter_soft_and_hard() -> None:
    """Cycle 2054 recipe sla_stage_density — soft at-risk vs hard breached dual queues."""
    block = _manager_ops_block()
    soft = block.split("\n  at_risk_queue:\n", 1)[1].split("\n  breached_queue:", 1)[0]
    hard = block.split("\n  breached_queue:\n", 1)[1].split("\n  sla_readiness:", 1)[0]
    assert "source: Ticket" in soft
    assert "sla_state = at_risk" in soft
    assert "status != closed" in soft
    assert "display: queue" in soft
    assert "limit: 4" in soft
    assert "source: Ticket" in hard
    assert "sla_state = breached" in hard
    assert "status != closed" in hard
    assert "display: queue" in hard
    assert "limit: 4" in hard
    # Soft and hard are exclusive stage filters (not OR-combined pressure list).
    assert "sla_state = breached" not in soft
    assert "sla_state = at_risk" not in hard


def test_ticket_seeds_span_sla_states() -> None:
    rows = [json.loads(line) for line in TICKET_SEEDS.read_text().splitlines() if line.strip()]
    states = {str(r.get("sla_state") or "") for r in rows}
    assert "on_track" in states
    assert "at_risk" in states
    assert "breached" in states
    pressure = [
        r
        for r in rows
        if r.get("sla_state") in ("at_risk", "breached") and r.get("status") != "closed"
    ]
    assert len(pressure) >= 3, f"expected ≥3 open pressure tickets, got {pressure}"
    soft = [r for r in pressure if r.get("sla_state") == "at_risk"]
    hard = [r for r in pressure if r.get("sla_state") == "breached"]
    assert len(soft) >= 1, "at_risk_queue needs ≥1 open soft-SLA seed"
    assert len(hard) >= 1, "breached_queue needs ≥1 open hard-SLA seed"
