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


def test_ticket_hub_discussion_is_content_first_not_internal_meta() -> None:
    """Peer pack: discussion trail is content/author prose — not is_internal meta."""
    text = APP.read_text()
    block = text.split('surface ticket_detail "Ticket Detail":', 1)[1].split(
        'surface ticket_create "Create Ticket":', 1
    )[0]
    discussion = block.split('related discussion "Discussion":', 1)[1].split("related waivers", 1)[
        0
    ]
    assert "display: queue" in discussion
    assert "show: Comment" in discussion
    assert "columns: content, author, created_at" in discussion
    assert "is_internal" not in discussion


def test_comment_seeds_have_domain_true_support_copy() -> None:
    rows = [json.loads(line) for line in NOTE_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 10
    for row in rows:
        body = str(row.get("content") or "")
        assert len(body) >= 24, body
        assert " " in body
