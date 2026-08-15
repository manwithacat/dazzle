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


def test_conversation_roles_map_note_phase_and_page_channel() -> None:
    """Ops PagerDuty trail — note_phase → tone; page_channel → channel (cycle 1917)."""
    roles = conversation_roles(("body", "author", "note_phase", "page_channel", "created_at"))
    assert roles == ["text", "author", "tone", "channel", "time"]


def test_conversation_roles_map_note_kind_as_channel() -> None:
    """QA/lab note_kind is channel-mapped (suffix), not a second trail (cycle 2083)."""
    roles = conversation_roles(("body", "author", "note_kind", "created_at"))
    assert roles == ["text", "author", "channel", "time"]


def test_related_conversation_note_kind_repro_suffix_and_danger() -> None:
    """TestRail/Jira repro notes label the same trail; default note stays unsuffixed."""
    tab = RelatedTab(
        tab_id="discussion",
        label="Discussion",
        headers=("body", "author", "note_kind", "created_at"),
        rows=(
            (
                "Battery 40% drop reproduces on continuous sample.",
                "engineer",
                "repro",
                "2026-07-28T09:15:00",
            ),
            (
                "Prioritise fix ahead of mechanical polish.",
                "manager",
                "note",
                "2026-07-26T15:30:00",
            ),
        ),
        row_drill=("", ""),
    )
    msgs = related_conversation_messages(tab)
    assert len(msgs) == 2
    assert msgs[0].author == "engineer · repro"
    assert msgs[0].bubble.tone == "danger"
    assert msgs[1].author == "manager"
    assert msgs[1].bubble.tone == ""


def test_conversation_bubble_tone_danger_values() -> None:
    assert conversation_bubble_tone("frustrated") == "danger"
    assert conversation_bubble_tone("urgent") == "danger"
    assert conversation_bubble_tone("raised") == "danger"
    assert conversation_bubble_tone("critical") == "danger"
    assert conversation_bubble_tone("escalate") == "danger"
    assert conversation_bubble_tone("mitigate") == "danger"
    assert conversation_bubble_tone("repro") == "danger"
    assert conversation_bubble_tone("neutral") == ""
    assert conversation_bubble_tone("thankful") == ""
    assert conversation_bubble_tone("none") == ""
    assert conversation_bubble_tone("observe") == ""
    assert conversation_bubble_tone("ack") == ""
    assert conversation_bubble_tone("resolve") == ""


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


def test_related_conversation_ops_phase_and_page_channel() -> None:
    """Ops desk: note_phase escalate → danger; page_channel slack suffixes author."""
    tab = RelatedTab(
        tab_id="discussion",
        label="Discussion",
        headers=("body", "author", "note_phase", "page_channel", "created_at"),
        rows=(
            (
                "Finance on bridge — escalate to PSP status.",
                "admin",
                "escalate",
                "slack",
                "2026-07-22T09:18:00",
            ),
            (
                "Ack'd — holding page if error_rate stays high.",
                "ops_engineer",
                "ack",
                "bridge",
                "2026-07-22T10:12:00",
            ),
        ),
        row_drill=("", ""),
    )
    msgs = related_conversation_messages(tab)
    assert len(msgs) == 2
    assert msgs[0].bubble.tone == "danger"
    assert msgs[0].author == "admin · slack"
    assert msgs[1].bubble.tone == ""
    # bridge is ops default path — no author suffix (portal parity).
    assert msgs[1].author == "ops_engineer"
