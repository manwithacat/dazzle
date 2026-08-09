"""Post-5.8 Goal B empty_region_honesty — domain_join_co Team Board / home."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOMAIN = ROOT / "examples/domain_join_co/dsl/domain.dsl"


def _workspace_block(name: str) -> str:
    text = DOMAIN.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    # next workspace header or EOF
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        return text[start:]
    return text[start : start + 1 + nxt]


def test_announce_leads_with_conversation_not_duplicate_queues() -> None:
    """Buyer board: pulse → feed → context → conversation; no empty twin queues/charts."""
    block = _workspace_block("announce")
    assert "board_pulse:" in block
    assert "live_conversation:" in block
    assert "feed_queue:" in block
    assert "join_context:" in block
    # command_density order: dual attention before conversation trail
    assert block.index("board_pulse:") < block.index("feed_queue:")
    assert block.index("feed_queue:") < block.index("live_conversation:")
    # Removed empty-region theater
    assert "feed_cards:" not in block
    assert "post_mix:" not in block
    assert "workspace_cards:" not in block
    assert "focus: board_pulse, feed_queue, join_context, live_conversation" in block


def test_home_omits_duplicate_board_dumps() -> None:
    block = _workspace_block("home")
    assert "live_conversation:" in block
    assert "join_readiness:" in block
    assert "announcement_queue:" in block
    assert "board_cards:" not in block
    assert "post_mix:" not in block
    assert "focus: team_pulse, announcement_queue, join_readiness, live_conversation" in block


def test_publish_desk_drops_empty_chart() -> None:
    block = _workspace_block("publish_desk")
    assert "draft_queue:" in block
    assert "live_cards:" in block
    assert "post_mix:" not in block
    assert "focus: publish_pulse, draft_queue, live_cards, readiness" in block
