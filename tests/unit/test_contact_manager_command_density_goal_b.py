"""Post-5.8 Goal B command_density — contact_manager Home dual attention (cycle 1830)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/contact_manager/dsl/app.dsl"


def _home_block() -> str:
    text = APP.read_text()
    start = text.index('workspace home "Home":')
    end = text.index('workspace contacts "Contacts":', start)
    return text[start:end]


def test_home_declares_dual_attention_before_conversation() -> None:
    """Peer CRM homes put ≥2 attention panels above a conversation trail.

    Order: metrics → document pulse → favourites → composition → conversation.
    """
    block = _home_block()
    assert "directory_stats:" in block
    assert "engagement_docs:" in block
    assert "favourite_contacts:" in block
    assert "composition:" in block
    assert "live_conversation:" in block
    assert block.index("directory_stats:") < block.index("engagement_docs:")
    assert block.index("engagement_docs:") < block.index("favourite_contacts:")
    assert block.index("favourite_contacts:") < block.index("composition:")
    assert block.index("composition:") < block.index("live_conversation:")


def test_home_caps_attention_queues_for_fold_share() -> None:
    block = _home_block()
    # Caps keep dual panels + composition + conversation sharing the fold.
    assert "limit: 4" in block
    assert (
        "focus: media_shelf, directory_stats, engagement_docs, favourite_contacts, composition, "
        "live_conversation, practice_context" in block
    )
    assert "Multi-panel CRM" in block or "multi-panel" in block.lower()


def test_home_metrics_count_favourites_and_conversation() -> None:
    block = _home_block()
    assert "favourites: count(Contact where is_favorite = true)" in block
    assert "conversation: count(ContactNote)" in block
    assert "awaiting_signature: count(EngagementLetter where status = sent)" in block
    assert "display: conversation" in block
