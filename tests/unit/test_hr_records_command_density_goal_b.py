"""Post-5.8 Goal B command_density — hr_records dual attention (cycle 1837)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/hr_records/dsl/app.dsl"


def _workspace_block(name: str) -> str:
    text = APP.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        return text[start:]
    return text[start : start + 1 + nxt]


def test_staff_directory_dual_attention_before_conversation() -> None:
    """Peer HR dens put active roster + starters above people-notes trail.

    Order: headcount → current_staff → recent_starters → composition → live_conversation.
    """
    block = _workspace_block("staff_directory")
    assert "headcount:" in block
    assert "current_staff:" in block
    assert "recent_starters:" in block
    assert "composition:" in block
    assert "live_conversation:" in block
    assert block.index("headcount:") < block.index("current_staff:")
    assert block.index("current_staff:") < block.index("recent_starters:")
    assert block.index("recent_starters:") < block.index("composition:")
    assert block.index("composition:") < block.index("live_conversation:")
    assert "Multi-panel" in block or "multi-panel" in block.lower()
    # Cycle 1950: focus ≤4 for fold thrash; dual attention still before docs/notes order.
    assert "focus: media_shelf, headcount, current_staff, recent_starters" in block


def test_my_team_dual_attention_before_conversation() -> None:
    """Manager home: level + department dual attention before notes trail."""
    block = _workspace_block("my_team")
    assert "team_pulse:" in block
    assert "\n  by_level:" in block
    assert "\n  by_department:" in block
    assert "composition:" in block
    assert "live_conversation:" in block
    assert block.index("team_pulse:") < block.index("\n  by_level:")
    assert block.index("\n  by_level:") < block.index("\n  by_department:")
    assert block.index("\n  by_department:") < block.index("live_conversation:")
    assert "Multi-panel" in block or "multi-panel" in block.lower()
    assert "focus: team_pulse, office_sites, remote_flex, by_department" in block


def test_attention_queues_capped_for_fold_share() -> None:
    staff = _workspace_block("staff_directory")
    team = _workspace_block("my_team")
    # Tight caps so dual attention shares the above-fold dens with notes.
    assert "limit: 4" in staff
    assert "limit: 4" in team
    assert "filter: ended_at = null" in staff
    assert "filter: end_date = null" in team
