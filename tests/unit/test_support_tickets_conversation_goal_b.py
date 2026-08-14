"""Post-5.8 Goal B conversation — support_tickets live thread on triage/ops desks."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/support_tickets/dsl/app.dsl"
NOTE_SEEDS = ROOT / "examples/support_tickets/dsl/seeds/demo_data/Comment.jsonl"
TICKET_SEEDS = ROOT / "examples/support_tickets/dsl/seeds/demo_data/Ticket.jsonl"


def test_comment_display_field_is_content() -> None:
    text = APP.read_text()
    assert "entity Comment" in text
    assert "display_field: content" in text
    assert "content: text required" in text


def test_hero_desks_declare_live_conversation_spine() -> None:
    text = APP.read_text()
    assert "workspace ticket_queue" in text
    assert "workspace manager_ops" in text
    assert "workspace agent_dashboard" in text
    assert "live_conversation:" in text
    assert "source: Comment" in text
    assert "conversation: count(Comment)" in text
    assert "my_conversation:" in text
    # Manager ops command home carries the same conversation metric + spine
    manager = text.split("workspace manager_ops", 1)[1].split("workspace agent_dashboard", 1)[0]
    assert "conversation: count(Comment)" in manager
    assert "live_conversation:" in manager
    # Goal B interesting_product: manager ops uses Message/Bubble conversation
    # chrome (not raw is_internal queue meta) after dual attention panels.
    live = manager.split("live_conversation:", 1)[1].split("\n  ux:", 1)[0]
    assert "display: conversation" in live
    assert "source: Comment" in live


def test_ticket_queue_live_conversation_uses_message_chrome() -> None:
    text = APP.read_text()
    block = text.split("workspace ticket_queue", 1)[1].split("workspace manager_ops", 1)[0]
    live = block.split("live_conversation:", 1)[1].split("\n  open_queue:", 1)[0]
    assert "display: conversation" in live
    assert "source: Comment" in live


def test_comment_declares_customer_tone() -> None:
    """Peer pack conversation upgrade — customer tone on the speech entity."""
    text = APP.read_text()
    block = text.split('entity Comment "Comment":', 1)[1].split("entity ", 1)[0]
    assert "customer_tone: enum[neutral,frustrated,urgent,thankful]=neutral" in block
    assert "customer_tone" in block.split("fitness:", 1)[1].split("\n\n", 1)[0]


def test_comment_declares_channel_and_escalation() -> None:
    """Peer pack conversation upgrade (cycle 1907) — channel + escalation."""
    text = APP.read_text()
    block = text.split('entity Comment "Comment":', 1)[1].split("entity ", 1)[0]
    assert "channel: enum[portal,email,chat,phone]=portal" in block
    assert "escalation: enum[none,raised,critical]=none" in block
    fitness = block.split("fitness:", 1)[1].split("\n\n", 1)[0]
    assert "channel" in fitness
    assert "escalation" in fitness


def test_ticket_hub_discussion_is_content_first_not_internal_meta() -> None:
    """Peer pack: discussion trail is Message chrome — is_internal orients only."""
    text = APP.read_text()
    block = text.split('surface ticket_detail "Ticket Detail":', 1)[1].split(
        'surface ticket_create "Create Ticket":', 1
    )[0]
    discussion = block.split('related discussion "Discussion":', 1)[1].split("related waivers", 1)[
        0
    ]
    assert "display: conversation" in discussion
    assert "show: Comment" in discussion
    assert (
        "columns: content, author, customer_tone, channel, escalation, ball_in_court, sla_pressure, case_priority, created_at, is_internal"
        in discussion
    )
    # is_internal is orient-only (not queue meta thrash column lead).
    assert discussion.index("content") < discussion.index("is_internal")
    assert discussion.index("customer_tone") < discussion.index("is_internal")
    assert discussion.index("channel") < discussion.index("is_internal")
    assert discussion.index("escalation") < discussion.index("is_internal")
    assert discussion.index("ball_in_court") < discussion.index("is_internal")
    assert discussion.index("case_priority") < discussion.index("is_internal")
    assert discussion.index("sla_pressure") < discussion.index("case_priority")


def test_user_hub_comments_uses_conversation_chrome() -> None:
    """User hub Comments is Message/Bubble trail (not queue meta) — cycle 1899."""
    text = APP.read_text()
    # User detail surface hosts related Comments on the person hub.
    assert 'related comments "Comments"' in text
    # Prefer user_detail / user view surface block.
    for marker in (
        'surface user_detail "User Detail"',
        'surface user_detail "User"',
        'surface user_view "User"',
        "surface user_detail",
    ):
        if marker in text:
            block = text.split(marker, 1)[1]
            block = block.split("surface user_create", 1)[0]
            if 'related comments "Comments"' not in block:
                continue
            related = block.split('related comments "Comments"', 1)[1][:280]
            assert "display: conversation" in related
            assert "show: Comment" in related
            assert "customer_tone" in related
            assert "display: queue" not in related
            return
    # Fallback: last related Comments before user_create is the hub.
    before = text.split('surface user_create "Create User"', 1)[0]
    related = before.rsplit('related comments "Comments"', 1)[1][:280]
    assert "display: conversation" in related
    assert "show: Comment" in related
    assert "customer_tone" in related


def test_comment_declares_ball_in_court() -> None:
    """Peer pack conversation upgrade (cycle 1922) — needs-reply ball grain."""
    text = APP.read_text()
    block = text.split('entity Comment "Comment":', 1)[1].split("entity ", 1)[0]
    assert "ball_in_court: enum[agent,customer,none]=none" in block
    fitness = block.split("fitness:", 1)[1].split("\n\n", 1)[0]
    assert "ball_in_court" in fitness


def test_hero_desks_declare_needs_reply_ball() -> None:
    """Front / Intercom needs-reply region on triage + agent + manager homes."""
    text = APP.read_text()
    for ws, nxt in (
        ("workspace ticket_queue", "workspace manager_ops"),
        ("workspace manager_ops", "workspace agent_dashboard"),
        ("workspace agent_dashboard", "workspace my_tickets"),
    ):
        block = text.split(ws, 1)[1].split(nxt, 1)[0]
        assert "\n  needs_reply:\n" in block, ws
        assert "ball_in_court = agent" in block, ws
        # Region body (skip metric keys named needs_reply: count(...)).
        region = block.split("\n  needs_reply:\n", 1)[1][:500]
        assert "display: conversation" in region, ws
        assert "source: Comment" in region, ws
    assert "needs_reply: count(Comment where ball_in_court = agent)" in text


def test_comment_seeds_have_domain_true_support_copy() -> None:
    rows = [json.loads(line) for line in NOTE_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 10
    tones = set()
    channels = set()
    escalations = set()
    balls = set()
    for row in rows:
        body = str(row.get("content") or "")
        assert len(body) >= 24, body
        assert " " in body
        tone = str(row.get("customer_tone") or "neutral")
        assert tone in {"neutral", "frustrated", "urgent", "thankful"}, tone
        tones.add(tone)
        channel = str(row.get("channel") or "portal")
        assert channel in {"portal", "email", "chat", "phone"}, channel
        channels.add(channel)
        esc = str(row.get("escalation") or "none")
        assert esc in {"none", "raised", "critical"}, esc
        escalations.add(esc)
        ball = str(row.get("ball_in_court") or "none")
        assert ball in {"agent", "customer", "none"}, ball
        balls.add(ball)
    # Peer pack: mix includes lean-in tones (not all neutral).
    assert tones & {"frustrated", "urgent"}
    # Channel + escalation peer mix (not all portal / none).
    assert channels - {"portal"}
    assert escalations & {"raised", "critical"}
    # Needs-reply ball: customer speech waiting on agents + agent replies.
    assert "agent" in balls
    assert "customer" in balls
    agent_public = [
        r for r in rows if r.get("ball_in_court") == "agent" and r.get("is_internal") is False
    ]
    assert len(agent_public) >= 3


def test_comment_declares_case_priority() -> None:
    """Denormalized ticket priority on speech (entity field; not a coat slice)."""
    text = APP.read_text()
    block = text.split('entity Comment "Comment":', 1)[1].split("entity ", 1)[0]
    assert "case_priority: enum[low,medium,high,critical]=medium" in block
    assert "case_priority" in block.split("fitness:", 1)[1].split("\n\n", 1)[0]


TQ_FOCUS = "focus: media_shelf, queue_metrics, needs_reply, live_conversation"
MO_FOCUS = (
    "focus: media_shelf, team_metrics, open_stage_queue, in_progress_stage_queue, "
    "at_risk_queue, breached_queue, critical_queue, unassigned_queue, "
    "needs_reply, live_conversation"
)
AD_FOCUS = "focus: my_assigned, needs_reply, awaiting_customer, pending_resolution"

# Coat synonym slices distilled in cycle 2077 (Goal C honest grain).
_COAT_REGIONS = (
    "medium_needs_reply",
    "priority_needs_reply",
    "at_risk_needs_reply",
    "breached_needs_reply",
    "breach_needs_reply",
    "thankful_needs_reply",
    "hot_speech",
    "urgent_speech",
    "frustrated_speech",
    "chat_live",
    "email_needs_reply",
    "portal_needs_reply",
    "internal_notes",
    "critical_escalations",
    "raised_escalations",
)


def _ticket_queue() -> str:
    text = APP.read_text()
    return text.split("workspace ticket_queue", 1)[1].split("workspace manager_ops", 1)[0]


def _manager_ops() -> str:
    text = APP.read_text()
    return text.split("workspace manager_ops", 1)[1].split("workspace agent_dashboard", 1)[0]


def _agent_dashboard() -> str:
    text = APP.read_text()
    return text.split("workspace agent_dashboard", 1)[1].split("workspace my_tickets", 1)[0]


def test_ticket_queue_honest_grain_is_needs_reply_plus_live() -> None:
    """Goal C: one pressure trail + one live thread on the triage desk."""
    block = _ticket_queue()
    assert "\n  needs_reply:\n" in block
    assert "\n  live_conversation:\n" in block
    assert TQ_FOCUS in block
    needs = block.split("\n  needs_reply:\n", 1)[1].split("\n  live_conversation:", 1)[0]
    assert "ball_in_court = agent" in needs
    assert "display: conversation" in needs
    live = block.split("\n  live_conversation:\n", 1)[1].split("\n  composition:", 1)[0]
    assert "display: conversation" in live
    assert "source: Comment" in live
    assert "filter:" not in live
    for name in _COAT_REGIONS:
        assert f"\n  {name}:\n" not in block, name


def test_manager_ops_honest_grain_is_needs_reply_plus_live() -> None:
    """Goal C: same pair on the manager command home — no cartesian speech wall."""
    block = _manager_ops()
    assert "\n  needs_reply:\n" in block
    assert "\n  live_conversation:\n" in block
    assert MO_FOCUS in block
    for name in _COAT_REGIONS:
        assert f"\n  {name}:\n" not in block, name


def test_agent_dashboard_honest_pair_is_needs_reply_and_awaiting() -> None:
    """Agent WIP keeps both-ball pair (0 cartesian) — not tone/channel re-stack."""
    block = _agent_dashboard()
    assert "\n  needs_reply:\n" in block
    assert "\n  awaiting_customer:\n" in block
    assert AD_FOCUS in block
    assert "\n  urgent_speech:\n" not in block
    assert "\n  thankful_recovery:\n" not in block
    assert "\n  internal_notes:\n" not in block
    assert "\n  critical_escalations:\n" not in block


def test_hero_desks_have_no_cartesian_conversation_slices() -> None:
    """enum × ball_in_court conversation filters are the Goal C delete target."""
    text = APP.read_text()
    for ws, nxt in (
        ("workspace ticket_queue", "workspace manager_ops"),
        ("workspace manager_ops", "workspace agent_dashboard"),
        ("workspace agent_dashboard", "workspace my_tickets"),
    ):
        block = text.split(ws, 1)[1].split(nxt, 1)[0]
        assert "sla_pressure =" not in block or "display: conversation" in block
        # No remaining region filter combines ball with enum coat keys.
        assert "sla_pressure =" not in block
        assert "case_priority =" not in block
        assert "customer_tone =" not in block
        assert "channel =" not in block
        assert "escalation =" not in block
