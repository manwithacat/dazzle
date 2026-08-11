"""Related conversation maps customer_tone / escalation → Bubble danger."""

from __future__ import annotations

from dazzle.render.fragment.primitives import RelatedTab
from dazzle.render.fragment.renderer._related_conversation import (
    conversation_bubble_tone,
    conversation_roles,
    related_conversation_messages,
)


def test_conversation_roles_map_customer_tone() -> None:
    roles = conversation_roles(("content", "author", "customer_tone", "created_at", "is_internal"))
    assert roles == ["text", "author", "tone", "time", "orient"]


def test_conversation_roles_map_channel_and_escalation() -> None:
    roles = conversation_roles(
        ("content", "author", "customer_tone", "channel", "escalation", "created_at", "is_internal")
    )
    assert roles == ["text", "author", "tone", "channel", "tone", "time", "orient"]


def test_conversation_bubble_tone_danger_values() -> None:
    assert conversation_bubble_tone("frustrated") == "danger"
    assert conversation_bubble_tone("urgent") == "danger"
    assert conversation_bubble_tone("raised") == "danger"
    assert conversation_bubble_tone("critical") == "danger"
    assert conversation_bubble_tone("neutral") == ""
    assert conversation_bubble_tone("thankful") == ""
    assert conversation_bubble_tone("none") == ""


def test_related_conversation_messages_apply_danger_tone() -> None:
    tab = RelatedTab(
        tab_id="discussion",
        label="Discussion",
        headers=("content", "author", "customer_tone", "created_at", "is_internal"),
        rows=(
            (
                "Still blocked on login.",
                "Casey Customer",
                "frustrated",
                "2026-07-12T10:15:00",
                "no",
            ),
            ("Temp password reissued.", "Alex Agent", "neutral", "2026-07-12T10:42:00", "yes"),
        ),
        row_drill=("", ""),
    )
    msgs = related_conversation_messages(tab)
    assert len(msgs) == 2
    assert msgs[0].bubble.tone == "danger"
    assert msgs[0].bubble.from_ == "in"
    assert msgs[1].bubble.tone == ""
    assert msgs[1].bubble.from_ == "out"


def test_related_conversation_messages_channel_suffix_and_escalation() -> None:
    """Peer pack: channel labels author; escalation alone can danger the bubble."""
    tab = RelatedTab(
        tab_id="discussion",
        label="Discussion",
        headers=(
            "content",
            "author",
            "customer_tone",
            "channel",
            "escalation",
            "created_at",
            "is_internal",
        ),
        rows=(
            (
                "Need refund before Friday close.",
                "Casey Customer",
                "neutral",
                "phone",
                "critical",
                "2026-07-10T11:05:00",
                "no",
            ),
            (
                "Refund initiated.",
                "Alex Agent",
                "neutral",
                "email",
                "none",
                "2026-07-10T14:20:00",
                "yes",
            ),
        ),
        row_drill=("", ""),
    )
    msgs = related_conversation_messages(tab)
    assert len(msgs) == 2
    assert msgs[0].author == "Casey Customer · phone"
    assert msgs[0].bubble.tone == "danger"
    assert msgs[0].media_label == "CC"
    assert msgs[1].author == "Alex Agent · email"
    assert msgs[1].bubble.tone == ""
    assert msgs[1].bubble.from_ == "out"


def test_related_conversation_skips_portal_channel_suffix() -> None:
    tab = RelatedTab(
        tab_id="discussion",
        label="Discussion",
        headers=("content", "author", "channel", "created_at", "is_internal"),
        rows=(
            ("Portal note.", "Casey", "portal", "2026-07-12T10:15:00", "no"),
            ("Chat note.", "Casey", "chat", "2026-07-12T10:16:00", "no"),
        ),
        row_drill=("", ""),
    )
    msgs = related_conversation_messages(tab)
    assert msgs[0].author == "Casey"
    assert msgs[1].author == "Casey · chat"
