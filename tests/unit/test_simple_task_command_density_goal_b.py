"""Post-5.8 Goal B command_density — simple_task hero desks dual attention (cycle 1835)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/simple_task/dsl/app.dsl"


def _workspace_block(name: str) -> str:
    text = APP.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        return text[start:]
    return text[start : start + 1 + nxt]


def test_admin_dashboard_dual_attention_before_conversation() -> None:
    """Peer admin ops homes put urgent + overdue pressure above discussion trail.

    Cycle 2058: conversation dual (open_blockers/open_questions) is focus-eager;
    task dual attention + composition remain authored regions in order.
    """
    block = _workspace_block("admin_dashboard")
    assert "media_shelf:" in block
    assert "metrics:" in block
    assert "urgent_tasks:" in block
    assert "overdue_tasks:" in block
    assert "composition:" in block
    assert "open_blockers:" in block
    assert "open_questions:" in block
    assert "live_conversation:" in block
    assert block.index("media_shelf:") < block.index("metrics:")
    assert block.index("metrics:") < block.index("urgent_tasks:")
    assert block.index("urgent_tasks:") < block.index("overdue_tasks:")
    assert block.index("overdue_tasks:") < block.index("composition:")
    assert block.index("composition:") < block.index("open_blockers:")
    assert block.index("open_questions:") < block.index("open_decisions:")
    assert block.index("open_decisions:") < block.index("composition:")
    assert block.index("composition:") < block.index("open_blockers:")
    assert "focus: open_questions, open_decisions, media_shelf, metrics" in block
    assert "Multi-panel" in block or "multi-panel" in block.lower()


def test_team_overview_dual_attention_before_conversation() -> None:
    block = _workspace_block("team_overview")
    assert "media_shelf:" in block
    assert "metrics:" in block
    assert "needs_review:" in block
    assert "plate_by_person:" in block
    assert "composition:" in block
    assert "live_conversation:" in block
    assert block.index("media_shelf:") < block.index("metrics:")
    assert block.index("metrics:") < block.index("needs_review:")
    assert block.index("needs_review:") < block.index("plate_by_person:")
    assert block.index("plate_by_person:") < block.index("composition:")
    assert block.index("composition:") < block.index("live_conversation:")
    # Cycle 1951: ≤4 focus; cycle 2058 conversation density on lead still.
    assert "focus: open_questions, open_decisions, media_shelf, metrics" in block
    assert "needs_review:" in block
    assert "plate_by_person:" in block
    assert "composition:" in block
    assert "live_conversation:" in block
    assert "team_roster:" in block


def test_my_work_dual_attention_before_conversation() -> None:
    block = _workspace_block("my_work")
    assert "my_summary:" in block
    assert "my_board:" in block
    assert "my_upcoming:" in block
    assert "composition:" in block
    assert "live_conversation:" in block
    assert block.index("my_summary:") < block.index("my_board:")
    assert block.index("my_board:") < block.index("my_upcoming:")
    assert block.index("my_upcoming:") < block.index("composition:")
    assert block.index("composition:") < block.index("live_conversation:")
    assert "focus: my_summary, my_board, my_upcoming, composition, live_conversation" in block


def test_attention_queues_capped_for_fold_share() -> None:
    admin = _workspace_block("admin_dashboard")
    team = _workspace_block("team_overview")
    mine = _workspace_block("my_work")
    assert "limit: 4" in admin
    assert "limit: 4" in team
    assert "limit: 4" in mine
    assert "display: conversation" in admin
    assert "display: conversation" in team
    assert "display: conversation" in mine
