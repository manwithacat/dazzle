"""Post-5.8 Goal B empty_region_honesty — simple_task desks (cycle 1817 + 1916 peer)."""

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
    # media@1884 + command_density@1835 + cycle 1951 fold thrash cap (≤4 focus)
    assert "focus: open_questions, open_decisions, media_shelf, metrics" in block
    assert "composition:" in block
    assert "live_conversation:" in block
    assert "team_roster:" in block


def test_my_work_omits_twin_comment_timeline() -> None:
    block = _workspace_block("my_work")
    assert "live_conversation:" in block
    assert "composition:" in block
    assert "my_board:" in block
    assert "my_upcoming:" in block
    assert "my_discussion:" not in block
    # command_density@1835: dual attention before conversation trail
    assert "focus: my_summary, my_board, my_upcoming, composition, live_conversation" in block
    assert block.count("display: timeline") == 1


def test_comments_desk_omits_status_mix_bar_chart() -> None:
    """Discussion: pulse + notes trail + WIP queue — not status bar theater (cycle 1916)."""
    block = _workspace_block("comments_desk")
    assert "comment_pulse:" in block
    assert "recent:" in block
    assert "comment_trail:" in block
    assert "active_tasks:" in block
    assert "status_mix:" not in block
    assert "display: bar_chart" not in block
    assert "focus: comment_pulse, recent, comment_trail, active_tasks" in block


def test_people_desk_fills_load_omits_chart_voids() -> None:
    """People: org shape then unassigned + plate — not twin bar / capacity_hint theater."""
    block = _workspace_block("people_desk")
    assert "people_pulse:" in block
    assert "by_role:" in block
    assert "by_department:" in block
    assert "unassigned_work:" in block
    assert "plate_by_person:" in block
    assert "dept_mix:" not in block
    assert "load_mix:" not in block
    assert "capacity_hint:" not in block
    assert "roster:" not in block
    assert "display: bar_chart" not in block
    assert "focus: people_pulse, by_role, by_department, unassigned_work, plate_by_person" in block


def test_admin_dashboard_keeps_bar_chart_coverage_under_fold() -> None:
    """Bars dogfood under admin (not in focus) after secondary-desk prune."""
    block = _workspace_block("admin_dashboard")
    assert "status_mix:" in block
    assert "priority_mix:" in block
    assert block.count("display: bar_chart") >= 2
    assert "focus: open_questions, open_decisions, media_shelf, metrics" in block
    # Bars must not hijack the admin pressure spine.
    assert "status_mix" not in block.split("focus:")[1].split("\n")[0]
    assert "priority_mix" not in block.split("focus:")[1].split("\n")[0]


def test_simple_task_keeps_bar_chart_for_coverage() -> None:
    text = APP.read_text()
    assert "display: bar_chart" in text
    assert text.count("display: bar_chart") >= 2
