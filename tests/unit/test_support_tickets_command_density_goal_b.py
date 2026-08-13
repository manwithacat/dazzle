"""Post-5.8 Goal B command_density — support_tickets Manager Ops dual attention + SLA pressure."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/support_tickets/dsl/app.dsl"
TICKET_SEEDS = ROOT / "examples/support_tickets/dsl/seeds/demo_data/Ticket.jsonl"


def _manager_ops_block() -> str:
    text = APP.read_text()
    start = text.index('workspace manager_ops "Manager Ops":')
    end = text.index("workspace agent_dashboard", start)
    return text[start:end]


def test_manager_ops_declares_dual_attention_before_conversation() -> None:
    """Peer support ops homes put ≥2 attention panels above a conversation trail.

    Goal B document: composition sits after dual attention, before conversation.
    Cycle 1913: breach_risk (live sla_state) joins dual attention before critical.
    """
    block = _manager_ops_block()
    assert "team_metrics:" in block
    assert "sla_readiness:" in block
    assert "breach_risk:" in block
    assert "critical_queue:" in block
    assert "unassigned_queue:" in block
    assert "composition:" in block
    assert "live_conversation:" in block
    # Order: metrics → breach risk (live) → SLA strip → critical → unassigned → composition → conversation.
    assert block.index("team_metrics:") < block.index("breach_risk:")
    assert block.index("breach_risk:") < block.index("sla_readiness:")
    assert block.index("sla_readiness:") < block.index("critical_queue:")
    assert block.index("critical_queue:") < block.index("unassigned_queue:")
    assert block.index("unassigned_queue:") < block.index("composition:")
    assert block.index("composition:") < block.index("live_conversation:")


def test_manager_ops_caps_attention_queues_for_fold_share() -> None:
    block = _manager_ops_block()
    # Caps keep dual panels + composition + conversation sharing the fold.
    assert "limit: 4" in block
    assert (
        "focus: media_shelf, team_metrics, breach_risk, critical_queue, "
        "unassigned_queue, needs_reply, urgent_needs_reply, raised_needs_reply, critical_needs_reply, live_conversation"
        in block
    )
    assert "Multi-panel support ops" in block or "multi-panel" in block.lower()
    assert (
        "sla_breach_pressure" in block
        or "SLA breach pressure" in block
        or "breach risk" in block.lower()
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


def test_breach_risk_queue_filters_sla_pressure() -> None:
    block = _manager_ops_block()
    start = block.index("\n  breach_risk:")
    end = block.index("\n  critical_queue:", start)
    region = block[start:end]
    assert "sla_state = at_risk" in region or "sla_state = breached" in region
    assert "status != closed" in region
    assert "display: queue" in region
    assert "limit: 4" in region


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
