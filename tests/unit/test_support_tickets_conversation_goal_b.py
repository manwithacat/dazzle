"""Post-5.8 Goal B conversation — support_tickets live thread on triage/ops desks."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/support_tickets/dsl/app.dsl"
NOTE_SEEDS = ROOT / "examples/support_tickets/dsl/seeds/demo_data/Comment.jsonl"


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
        "columns: content, author, customer_tone, channel, escalation, ball_in_court, created_at, is_internal"
        in discussion
    )
    # is_internal is orient-only (not queue meta thrash column lead).
    assert discussion.index("content") < discussion.index("is_internal")
    assert discussion.index("customer_tone") < discussion.index("is_internal")
    assert discussion.index("channel") < discussion.index("is_internal")
    assert discussion.index("escalation") < discussion.index("is_internal")
    assert discussion.index("ball_in_court") < discussion.index("is_internal")


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


def test_ticket_queue_hot_speech_before_live_trail() -> None:
    """Cycle 1940: tone/escalation heat region before full conversation trail."""
    text = APP.read_text()
    block = text.split("workspace ticket_queue", 1)[1].split("workspace manager_ops", 1)[0]
    # Region block (not the metrics aggregate key).
    region = block.split("\n  hot_speech:\n", 1)[1].split("\n  live_conversation:", 1)[0]
    assert "source: Comment" in region
    assert "customer_tone = frustrated" in region
    assert "customer_tone = urgent" in region
    assert "escalation != none" in region
    assert "display: conversation" in region
    assert "hot_speech: count(Comment" in block
    needs = block.index("\n  needs_reply:\n")
    awaiting = block.index("\n  awaiting_customer:\n")
    hot = block.index("\n  hot_speech:\n")
    live = block.index("\n  live_conversation:\n")
    assert needs < awaiting < hot < live
    assert (
        "focus: media_shelf, queue_metrics, needs_reply, awaiting_customer, hot_speech, live_conversation, open_queue"
        in block
    )


def test_ticket_queue_awaiting_customer_trail() -> None:
    """Cycle 1955: Front/Intercom waiting-on-customer ball complements needs_reply."""
    text = APP.read_text()
    block = text.split("workspace ticket_queue", 1)[1].split("workspace manager_ops", 1)[0]
    assert "awaiting_customer: count(Comment where ball_in_court = customer)" in block
    region = block.split("\n  awaiting_customer:\n", 1)[1].split("\n  hot_speech:", 1)[0]
    assert "source: Comment" in region
    assert "ball_in_court = customer" in region
    assert "is_internal = false" in region
    assert "display: conversation" in region
    agent = text.split("workspace agent_dashboard", 1)[1].split("workspace my_tickets", 1)[0]
    assert "\n  awaiting_customer:\n" in agent
    assert "ball_in_court = customer" in agent
    assert (
        "focus: my_assigned, needs_reply, awaiting_customer, my_conversation, pending_resolution"
        in agent
    )
