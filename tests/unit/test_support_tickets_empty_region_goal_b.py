"""Post-5.8 Goal B empty_region_honesty — support_tickets agent + customer desks."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/support_tickets/dsl/app.dsl"


def _workspace_block(name: str) -> str:
    text = APP.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        return text[start:]
    return text[start : start + 1 + nxt]


def test_agent_dashboard_omits_funnel_progress_and_triple_comment_theater() -> None:
    """Peer agent home: WIP kanban + notes + close-out + one trail — not chart voids."""
    block = _workspace_block("agent_dashboard")
    assert "my_assigned:" in block
    assert "my_conversation:" in block
    assert "pending_resolution:" in block
    assert "recent_comments:" in block
    assert "resolution_funnel:" not in block
    assert "backlog_progress:" not in block
    assert "ticket_history:" not in block
    assert "comment_activity:" not in block
    assert "activity_timeline:" not in block
    assert "display: funnel_chart" not in block
    assert "display: progress" not in block
    assert "display: activity_feed" not in block
    assert (
        "focus: my_assigned, needs_reply, urgent_speech, awaiting_customer, pending_resolution"
        in block
    )
    # recent_comments stays on the desk as secondary trail (not focus thrash).
    assert "recent_comments:" in block
    assert "ux:" in block
    assert "as agent:" in block
    # Single comment timeline only
    assert block.count("display: timeline") == 1


def test_my_tickets_drops_bar_chart_and_duplicate_dumps() -> None:
    """Customer portal: counts + open work + one history — not chart/timeline theater."""
    block = _workspace_block("my_tickets")
    assert "my_summary:" in block
    assert "open_cases:" in block
    assert "waiting_on_us:" in block
    assert "all_cases:" in block
    assert "how_it_works:" in block
    assert "my_status_mix:" not in block
    assert "open_cards:" not in block
    assert "resolved_recent:" not in block
    assert "my_trail:" not in block
    assert "display: bar_chart" not in block
    assert "focus: my_summary, open_cases, waiting_on_us, all_cases, how_it_works" in block
    assert "ux:" in block
    assert "as customer:" in block
    assert block.count("display: timeline") == 1


def test_agent_console_hosts_progress_and_activity_feed_coverage() -> None:
    """Hero prune must not leave display: progress / activity_feed fleet-uncovered."""
    block = _workspace_block("agent_console")
    assert "agent_lifecycle_progress:" in block
    assert "display: progress" in block
    assert "agent_comment_activity:" in block
    assert "display: activity_feed" in block
    assert "agent_status_funnel:" in block
    assert "display: funnel_chart" in block
    assert "current_context" in block


def test_manager_ops_omits_funnel_and_secondary_ticket_trail() -> None:
    """Manager Ops: dual queues + docs + conversation — not funnel/trail thrash."""
    block = _workspace_block("manager_ops")
    assert "critical_queue:" in block
    assert "unassigned_queue:" in block
    assert "composition:" in block
    assert "live_conversation:" in block
    assert "resolution_funnel:" not in block
    assert "recent_trail:" not in block
    assert "display: funnel_chart" not in block
    assert "display: timeline" not in block
    assert (
        "focus: media_shelf, team_metrics, breach_risk, critical_queue, "
        "unassigned_queue, needs_reply, frustrated_awaiting_customer, urgent_awaiting_customer, urgent_needs_reply, raised_needs_reply, live_conversation"
    ) in block
    assert "as manager:" in block
    assert "breach_risk:" in block
