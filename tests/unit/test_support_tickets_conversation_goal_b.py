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
    region = block.split("\n  hot_speech:\n", 1)[1].split("\n  frustrated_speech:", 1)[0]
    assert "source: Comment" in region
    assert "customer_tone = frustrated" in region
    assert "customer_tone = urgent" in region
    assert "escalation != none" in region
    assert "display: conversation" in region
    assert "hot_speech: count(Comment" in block
    needs = block.index("\n  needs_reply:\n")
    awaiting = block.index("\n  awaiting_customer:\n")
    hot = block.index("\n  hot_speech:\n")
    frustrated = block.index("\n  frustrated_speech:\n")
    urgent = block.index("\n  urgent_speech:\n")
    live = block.index("\n  live_conversation:\n")
    thankful = block.index("\n  thankful_recovery:\n")
    chat = block.index("\n  chat_live:\n")
    critical = block.index("\n  critical_escalations:\n")
    raised = block.index("\n  raised_escalations:\n")
    internal = block.index("\n  internal_notes:\n")
    assert (
        needs
        < awaiting
        < hot
        < frustrated
        < urgent
        < critical
        < raised
        < thankful
        < chat
        < internal
        < live
    )
    assert (
        "focus: media_shelf, queue_metrics, needs_reply, email_live, urgent_speech, live_conversation"
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
        "focus: my_assigned, needs_reply, urgent_speech, awaiting_customer, pending_resolution"
        in agent
    )


def test_ticket_queue_thankful_recovery_trail() -> None:
    """Cycle 1958: Intercom/Zendesk warm recovery trail complements hot_speech."""
    text = APP.read_text()
    block = text.split("workspace ticket_queue", 1)[1].split("workspace manager_ops", 1)[0]
    assert "thankful_recovery: count(Comment where customer_tone = thankful" in block
    region = block.split("\n  thankful_recovery:\n", 1)[1].split("\n  chat_live:", 1)[0]
    assert "source: Comment" in region
    assert "customer_tone = thankful" in region
    assert "display: conversation" in region
    agent = text.split("workspace agent_dashboard", 1)[1].split("workspace my_tickets", 1)[0]
    assert "\n  thankful_recovery:\n" in agent
    assert (
        "focus: my_assigned, needs_reply, urgent_speech, awaiting_customer, pending_resolution"
        in agent
    )


def test_ticket_queue_chat_live_trail() -> None:
    """Cycle 1960: Intercom/Front live chat channel trail."""
    text = APP.read_text()
    block = text.split("workspace ticket_queue", 1)[1].split("workspace manager_ops", 1)[0]
    assert "chat_live: count(Comment where channel = chat" in block
    region = block.split("\n  chat_live:\n", 1)[1].split("\n  phone_live:", 1)[0]
    assert "source: Comment" in region
    assert "channel = chat" in region
    assert "display: conversation" in region
    manager = text.split("workspace manager_ops", 1)[1].split("workspace agent_dashboard", 1)[0]
    assert "\n  chat_live:\n" in manager
    assert "channel = chat" in manager


def test_ticket_queue_phone_live_trail() -> None:
    """Cycle 1963: Zendesk phone-channel trail."""
    text = APP.read_text()
    block = text.split("workspace ticket_queue", 1)[1].split("workspace manager_ops", 1)[0]
    assert "phone_live: count(Comment where channel = phone" in block
    region = block.split("\n  phone_live:\n", 1)[1].split("\n  email_live:", 1)[0]
    assert "source: Comment" in region
    assert "channel = phone" in region
    assert "display: conversation" in region
    manager = text.split("workspace manager_ops", 1)[1].split("workspace agent_dashboard", 1)[0]
    assert "\n  phone_live:\n" in manager


def test_ticket_queue_email_live_trail() -> None:
    """Cycle 1982: Zendesk/Front email-channel trail (async path)."""
    text = APP.read_text()
    block = text.split("workspace ticket_queue", 1)[1].split("workspace manager_ops", 1)[0]
    assert "email_live: count(Comment where channel = email" in block
    region = block.split("\n  email_live:\n", 1)[1].split("\n  internal_notes:", 1)[0]
    assert "source: Comment" in region
    assert "filter: channel = email and is_internal = false" in region
    assert "display: conversation" in region
    # Pure channel filter — not tone/escalation re-stack.
    assert "customer_tone" not in region
    assert "escalation" not in region
    manager = text.split("workspace manager_ops", 1)[1].split("workspace agent_dashboard", 1)[0]
    assert "\n  email_live:\n" in manager
    assert "channel = email" in manager
    assert "email_live" in manager.split("focus:", 1)[1].split("\n", 1)[0]
    rows = [json.loads(line) for line in NOTE_SEEDS.read_text().splitlines() if line.strip()]
    email_public = [
        r for r in rows if r.get("channel") == "email" and r.get("is_internal") is not True
    ]
    assert len(email_public) >= 3


def test_ticket_queue_internal_collab_trail() -> None:
    """Cycle 1966: Zendesk/Front internal collab notes (non-channel conversation)."""
    text = APP.read_text()
    block = text.split("workspace ticket_queue", 1)[1].split("workspace manager_ops", 1)[0]
    assert "internal_notes: count(Comment where is_internal = true)" in block
    region = block.split("\n  internal_notes:\n", 1)[1].split("\n  live_conversation:", 1)[0]
    assert "source: Comment" in region
    assert "is_internal = true" in region
    assert "display: conversation" in region
    manager = text.split("workspace manager_ops", 1)[1].split("workspace agent_dashboard", 1)[0]
    assert "\n  internal_notes:\n" in manager
    assert "is_internal = true" in manager
    agent = text.split("workspace agent_dashboard", 1)[1].split("workspace my_tickets", 1)[0]
    assert "\n  internal_notes:\n" in agent
    rows = [json.loads(line) for line in NOTE_SEEDS.read_text().splitlines() if line.strip()]
    internal = [r for r in rows if r.get("is_internal") is True]
    assert len(internal) >= 3
    for r in internal:
        body = str(r.get("content") or "")
        assert len(body) >= 24


def test_ticket_queue_critical_escalation_trail() -> None:
    """Cycle 1969: Zendesk/Service Cloud P1 critical escalation speech (non-channel)."""
    text = APP.read_text()
    block = text.split("workspace ticket_queue", 1)[1].split("workspace manager_ops", 1)[0]
    assert "critical_escalations: count(Comment where escalation = critical" in block
    region = block.split("\n  critical_escalations:\n", 1)[1].split("\n  raised_escalations:", 1)[0]
    assert "source: Comment" in region
    assert "escalation = critical" in region
    assert "display: conversation" in region
    manager = text.split("workspace manager_ops", 1)[1].split("workspace agent_dashboard", 1)[0]
    assert "\n  critical_escalations:\n" in manager
    agent = text.split("workspace agent_dashboard", 1)[1].split("workspace my_tickets", 1)[0]
    assert "\n  critical_escalations:\n" in agent
    rows = [json.loads(line) for line in NOTE_SEEDS.read_text().splitlines() if line.strip()]
    crit = [
        r for r in rows if r.get("escalation") == "critical" and r.get("is_internal") is not True
    ]
    assert len(crit) >= 2


def test_ticket_queue_raised_escalation_trail() -> None:
    """Cycle 1972: Zendesk/Service Cloud L2 raised escalation speech (non-channel)."""
    text = APP.read_text()
    block = text.split("workspace ticket_queue", 1)[1].split("workspace manager_ops", 1)[0]
    assert "raised_escalations: count(Comment where escalation = raised" in block
    region = block.split("\n  raised_escalations:\n", 1)[1].split("\n  thankful_recovery:", 1)[0]
    assert "source: Comment" in region
    assert "escalation = raised" in region
    assert "display: conversation" in region
    manager = text.split("workspace manager_ops", 1)[1].split("workspace agent_dashboard", 1)[0]
    assert "\n  raised_escalations:\n" in manager
    agent = text.split("workspace agent_dashboard", 1)[1].split("workspace my_tickets", 1)[0]
    assert "\n  raised_escalations:\n" in agent
    rows = [json.loads(line) for line in NOTE_SEEDS.read_text().splitlines() if line.strip()]
    raised = [
        r for r in rows if r.get("escalation") == "raised" and r.get("is_internal") is not True
    ]
    assert len(raised) >= 2


def test_ticket_queue_frustrated_tone_trail() -> None:
    """Cycle 1977: Zendesk/Intercom pure frustrated tone (not hot_speech OR umbrella)."""
    text = APP.read_text()
    block = text.split("workspace ticket_queue", 1)[1].split("workspace manager_ops", 1)[0]
    assert "frustrated_speech: count(Comment where customer_tone = frustrated" in block
    region = block.split("\n  frustrated_speech:\n", 1)[1].split(
        "\n  # Peer-pack conversation upgrade (cycle 1979)", 1
    )[0]
    assert "source: Comment" in region
    assert "filter: customer_tone = frustrated and is_internal = false" in region
    assert "display: conversation" in region
    # Pure tone filter — not the hot_speech OR umbrella (urgent / escalation).
    assert "customer_tone = urgent" not in region
    assert "escalation !=" not in region
    assert "escalation =" not in region
    manager = text.split("workspace manager_ops", 1)[1].split("workspace agent_dashboard", 1)[0]
    assert "\n  frustrated_speech:\n" in manager
    assert "frustrated_speech: count(Comment where customer_tone = frustrated" in manager
    agent = text.split("workspace agent_dashboard", 1)[1].split("workspace my_tickets", 1)[0]
    assert "\n  frustrated_speech:\n" in agent
    rows = [json.loads(line) for line in NOTE_SEEDS.read_text().splitlines() if line.strip()]
    frustrated = [
        r
        for r in rows
        if r.get("customer_tone") == "frustrated" and r.get("is_internal") is not True
    ]
    assert len(frustrated) >= 3


def test_ticket_queue_urgent_tone_trail() -> None:
    """Cycle 1979: Zendesk/Intercom pure urgent tone (not hot_speech OR umbrella)."""
    text = APP.read_text()
    block = text.split("workspace ticket_queue", 1)[1].split("workspace manager_ops", 1)[0]
    assert "urgent_speech: count(Comment where customer_tone = urgent" in block
    region = block.split("\n  urgent_speech:\n", 1)[1].split(
        "\n  # Peer-pack conversation upgrade (cycle 1969)", 1
    )[0]
    assert "source: Comment" in region
    assert "filter: customer_tone = urgent and is_internal = false" in region
    assert "display: conversation" in region
    # Pure tone filter — not the hot_speech OR umbrella (frustrated / escalation).
    assert "customer_tone = frustrated" not in region
    assert "escalation !=" not in region
    assert "escalation =" not in region
    manager = text.split("workspace manager_ops", 1)[1].split("workspace agent_dashboard", 1)[0]
    assert "\n  urgent_speech:\n" in manager
    assert "urgent_speech: count(Comment where customer_tone = urgent" in manager
    # Focus later prefers email_live (cycle 1982); region + metric remain.
    agent = text.split("workspace agent_dashboard", 1)[1].split("workspace my_tickets", 1)[0]
    assert "\n  urgent_speech:\n" in agent
    assert "urgent_speech" in agent.split("focus:", 1)[1].split("\n", 1)[0]
    rows = [json.loads(line) for line in NOTE_SEEDS.read_text().splitlines() if line.strip()]
    urgent_public = [
        r for r in rows if r.get("customer_tone") == "urgent" and r.get("is_internal") is not True
    ]
    assert len(urgent_public) >= 3
    # Pure tone grain must not be only critical re-stack.
    pure = [r for r in urgent_public if r.get("escalation") in (None, "none")]
    assert len(pure) >= 1
