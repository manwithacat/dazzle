"""Related conversation maps customer_tone → Bubble danger (cycle 1902)."""

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


def test_conversation_bubble_tone_danger_values() -> None:
    assert conversation_bubble_tone("frustrated") == "danger"
    assert conversation_bubble_tone("urgent") == "danger"
    assert conversation_bubble_tone("neutral") == ""
    assert conversation_bubble_tone("thankful") == ""


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
