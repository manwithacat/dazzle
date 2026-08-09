"""Post-5.8 Goal B empty_region_honesty — simple_task primary desks (cycle 1817)."""

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


def test_task_board_omits_status_mix_and_comment_dump() -> None:
    block = _workspace_block("task_board")
    assert "board_pulse:" in block
    assert "tasks:" in block
    assert "by_assignee:" in block
    assert "upcoming_due:" in block
    assert "urgent_queue:" in block
    assert "status_mix:" not in block
    assert "recent_comments:" not in block
    assert "display: bar_chart" not in block
    assert "focus: board_pulse, tasks, by_assignee, upcoming_due, urgent_queue" in block


def test_team_overview_omits_flow_chart_and_twin_comment() -> None:
    block = _workspace_block("team_overview")
    assert "live_conversation:" in block
    assert "composition:" in block
    assert "needs_review:" in block
    assert "plate_by_person:" in block
    assert "flow_chart:" not in block
    assert "recent_discussion:" not in block
    assert "display: bar_chart" not in block
    assert (
        "focus: live_conversation, metrics, composition, needs_review, team_roster, plate_by_person"
        in block
    )


def test_my_work_omits_twin_comment_timeline() -> None:
    block = _workspace_block("my_work")
    assert "live_conversation:" in block
    assert "composition:" in block
    assert "my_board:" in block
    assert "my_upcoming:" in block
    assert "my_discussion:" not in block
    assert "focus: live_conversation, my_summary, composition, my_board, my_upcoming" in block
    assert block.count("display: timeline") == 1


def test_simple_task_keeps_bar_chart_for_coverage() -> None:
    text = APP.read_text()
    assert "display: bar_chart" in text
    assert text.count("display: bar_chart") >= 2
