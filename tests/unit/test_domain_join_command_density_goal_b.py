"""Post-5.8 Goal B command_density — domain_join_co Home/Board dual attention (cycle 1831)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOMAIN = ROOT / "examples/domain_join_co/dsl/domain.dsl"


def _workspace_block(name: str) -> str:
    text = DOMAIN.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        return text[start:]
    return text[start : start + 1 + nxt]


def test_home_dual_attention_before_conversation() -> None:
    """Peer team homes put post queue + readiness above discussion trail."""
    block = _workspace_block("home")
    assert "team_pulse:" in block
    assert "announcement_queue:" in block
    assert "join_readiness:" in block
    assert "live_conversation:" in block
    assert block.index("team_pulse:") < block.index("announcement_queue:")
    assert block.index("announcement_queue:") < block.index("join_readiness:")
    assert block.index("join_readiness:") < block.index("live_conversation:")
    assert (
        "focus: handbook_covers, team_pulse, announcement_queue, join_readiness, "
        "composition, live_conversation" in block
    )
    assert "Multi-panel" in block or "multi-panel" in block.lower()


def test_announce_dual_attention_before_conversation() -> None:
    block = _workspace_block("announce")
    assert "board_pulse:" in block
    assert "feed_queue:" in block
    assert "join_context:" in block
    assert "live_conversation:" in block
    assert block.index("board_pulse:") < block.index("feed_queue:")
    assert block.index("feed_queue:") < block.index("join_context:")
    assert block.index("join_context:") < block.index("live_conversation:")
    assert (
        "focus: handbook_covers, board_pulse, feed_queue, join_context, "
        "composition, live_conversation" in block
    )


def test_attention_queues_capped_for_fold_share() -> None:
    home = _workspace_block("home")
    announce = _workspace_block("announce")
    assert "limit: 4" in home
    assert "limit: 4" in announce
    # Conversation uses Message chrome (not queue meta).
    assert "display: conversation" in home
    assert "display: conversation" in announce
