"""Post-5.8 Goal B command_density — support_tickets Manager Ops dual attention."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/support_tickets/dsl/app.dsl"


def _manager_ops_block() -> str:
    text = APP.read_text()
    start = text.index('workspace manager_ops "Manager Ops":')
    end = text.index("workspace agent_dashboard", start)
    return text[start:end]


def test_manager_ops_declares_dual_attention_before_conversation() -> None:
    """Peer support ops homes put ≥2 attention panels above a conversation trail.

    Goal B document: composition sits after dual attention, before conversation.
    """
    block = _manager_ops_block()
    assert "team_metrics:" in block
    assert "sla_readiness:" in block
    assert "critical_queue:" in block
    assert "unassigned_queue:" in block
    assert "composition:" in block
    assert "live_conversation:" in block
    # Order: metrics → SLA → critical → unassigned → composition → conversation.
    assert block.index("team_metrics:") < block.index("sla_readiness:")
    assert block.index("sla_readiness:") < block.index("critical_queue:")
    assert block.index("critical_queue:") < block.index("unassigned_queue:")
    assert block.index("unassigned_queue:") < block.index("composition:")
    assert block.index("composition:") < block.index("live_conversation:")


def test_manager_ops_caps_attention_queues_for_fold_share() -> None:
    block = _manager_ops_block()
    # Caps keep dual panels + composition + conversation sharing the fold.
    assert "limit: 4" in block
    assert (
        "focus: team_metrics, sla_readiness, critical_queue, unassigned_queue, "
        "composition, live_conversation" in block
    )
    assert "Multi-panel support ops" in block or "multi-panel" in block.lower()


def test_manager_ops_metrics_count_critical_unassigned_and_conversation() -> None:
    block = _manager_ops_block()
    assert "critical_open: count(Ticket where priority = critical" in block
    assert "unassigned: count(Ticket where assigned_to = null and status = open)" in block
    assert "conversation: count(Comment)" in block
    assert "documents: count(SlaWaiver)" in block
