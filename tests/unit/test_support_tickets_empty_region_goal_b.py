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
    assert "focus: my_assigned, needs_reply, awaiting_customer, pending_resolution" in block
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


def test_agent_console_omits_twin_open_queue_and_comment_trail() -> None:
    """Cycle 2067 empty_region_honesty: recipe agent_console_twin_queue_prune.

    Peer Zendesk/Front agent inspectors: one open plate + one comment trail under
    the people selector — not twin open-ticket cards or dual comment timelines.
    Keep #1304 agent_tickets + agent_ticket_comments and coverage displays.
    """
    block = _workspace_block("agent_console")
    assert "agent_tickets:" in block
    assert "agent_ticket_comments:" in block
    assert "agent_priority_queue:" in block
    assert "agent_ticket_cards:" not in block
    assert "agent_comment_trail:" not in block
    # Single timeline (agent_ticket_comments) — not twin trails.
    assert block.count("display: timeline") == 1
    assert (
        "focus: agent_priority_queue, agent_ticket_comments, "
        "agent_lifecycle_progress, agent_category_chart" in block
    )
    assert "as manager:" in block
    assert "as agent:" in block
    assert "as admin:" in block


def test_agent_console_selector_lists_agents_only() -> None:
    """Cycle 2086 empty_region_honesty: recipe agent_only_selector.

    Peer Zendesk/Front inspectors pick a staff agent — not a customer
    requester. Default first option used to be Trial parent → two giant
    empty voids above fold. L1 + department != External fills the plate
    (``role =`` is reserved for role() checks).
    """
    text = APP.read_text()
    marker = 'workspace agent_console "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    block = text[start : start + 1 + nxt]
    assert "context_selector:" in block
    assert "filter: support_tier = l1 and department != External" in block
    assert "entity: User" in block


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
        "focus: media_shelf, team_metrics, open_stage_queue, in_progress_stage_queue, at_risk_queue, breached_queue, critical_queue, unassigned_queue, needs_reply, live_conversation"
    ) in block
    assert "as manager:" in block
    assert "at_risk_queue:" in block
    assert "breached_queue:" in block
    assert "breach_risk:" not in block


def test_people_desk_omits_twin_roster_dump() -> None:
    """Cycle 2052: no twin roster dump; cycle 2073 focus is L1→L2→L3 tier ladder.

    Recipe people_desk_roster_twin_prune — flat roster queue was scroll theater.
    Cycle 2056 support_tier_density + cycle 2073 l3_lead_density put L1/L2/L3
    people queues in focus (still no roster: region; load stays under fold).
    """
    block = _workspace_block("people_desk")
    assert "by_role:" in block
    assert "by_department:" in block
    assert "group_by: department" in block
    assert "l1_frontline:" in block
    assert "l2_escalation:" in block
    assert "l3_lead:" in block
    assert "unassigned_work:" in block
    assert "plate_by_person:" in block
    assert "roster:" not in block
    assert "display: bar_chart" not in block
    assert "focus: people_pulse, billing_staff, escalations_staff, unassigned_work" in block
    assert block.index("billing_staff:") < block.index("unassigned_work:")
    assert block.index("unassigned_work:") < block.index("plate_by_person:")
