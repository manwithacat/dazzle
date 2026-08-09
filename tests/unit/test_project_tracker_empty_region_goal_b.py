"""Post-5.8 Goal B empty_region_honesty — project_tracker primary desks."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/project_tracker/dsl/app.dsl"


def _workspace_block(name: str) -> str:
    text = APP.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        return text[start:]
    return text[start : start + 1 + nxt]


def test_dashboard_omits_priority_mix_bar_chart() -> None:
    """PM home: dual attention + conversation + kanban — not priority chart void."""
    block = _workspace_block("dashboard")
    assert "portfolio_metrics:" in block
    assert "composition:" in block
    assert "live_conversation:" in block
    assert "open_task_queue:" in block
    assert "project_overview:" in block
    assert "task_flow:" in block
    assert "priority_mix:" not in block
    assert "display: bar_chart" not in block
    assert (
        "focus: portfolio_metrics, open_task_queue, composition, live_conversation, "
        "project_overview, task_flow" in block
    )
    assert "ux:" in block


def test_project_board_omits_status_mix_bar_chart() -> None:
    """Board desk: metrics + kanban + unassigned + milestones — not status chart."""
    block = _workspace_block("project_board")
    assert "board_metrics:" in block
    assert "task_board:" in block
    assert "unassigned_queue:" in block
    assert "milestones:" in block
    assert "project_status_mix:" not in block
    assert "display: bar_chart" not in block
    assert "focus: board_metrics, task_board, unassigned_queue, milestones" in block


def test_my_tasks_omits_chart_and_twin_comment_dump() -> None:
    """Member desk: load + dual attention + conversation — not chart/twin timelines."""
    block = _workspace_block("my_tasks")
    assert "load:" in block
    assert "live_conversation:" in block
    assert "assigned_queue:" in block
    assert "board:" in block
    assert "my_priority_mix:" not in block
    assert "recent_discussion:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block
    assert "focus: load, assigned_queue, board, live_conversation" in block
    assert "as member:" in block


def test_project_tracker_keeps_bar_chart_on_secondary_desks() -> None:
    """Hero prune must not leave display: bar_chart fleet-uncovered in this app."""
    text = APP.read_text()
    assert "display: bar_chart" in text
    assert text.count("display: bar_chart") >= 2
