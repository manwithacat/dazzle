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
        "focus: media_shelf, portfolio_metrics, open_task_queue, composition, live_conversation"
        in block
    )
    assert "ux:" in block


def test_user_repr_omits_schema_dump_on_people_grids() -> None:
    """Cycle 2091 empty_region_honesty: recipe identity_chip_not_schema.

    Peer Linear/Asana: name/role/dept chips — not Photo Url / Email / Is Active.
    """
    text = APP.read_text()
    start = text.index('entity User "Team Member":')
    end = text.index("entity Project ", start)
    block = text[start:end]
    assert "repr_fields: [name, role, department]" in block


def test_project_board_omits_status_mix_bar_chart() -> None:
    """Board desk: metrics + kanban + dual attention + milestones — not status chart."""
    block = _workspace_block("project_board")
    assert "board_metrics:" in block
    assert "task_board:" in block
    assert "unassigned_queue:" in block
    assert "overdue_queue:" in block
    assert "milestones:" in block
    assert "project_status_mix:" not in block
    assert "display: bar_chart" not in block
    assert "focus: board_metrics, task_board, unassigned_queue, overdue_queue, milestones" in block


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


def test_discussion_desk_omits_twin_dump_kanban_and_priority_chart() -> None:
    """Cycle 1924 empty_region: one conversation spine + open work — not chart theater."""
    block = _workspace_block("discussion_desk")
    assert "discussion_pulse:" in block
    assert "live_conversation:" in block
    assert "open_tasks:" in block
    # Twin dumps / voids pruned
    assert "\n  recent:" not in block
    assert "open_flow:" not in block
    assert "priority_mix:" not in block
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block
    assert "display: kanban" not in block
    # Single conversation chrome + pull queue
    assert block.count("display: conversation") == 1
    assert "focus: discussion_pulse, live_conversation, open_tasks" in block
    assert "as manager:" in block
    assert "as member:" in block


def test_project_tracker_keeps_bar_chart_on_secondary_desks() -> None:
    """Hero prune must not leave display: bar_chart fleet-uncovered in this app."""
    text = APP.read_text()
    assert "display: bar_chart" in text
    assert text.count("display: bar_chart") >= 2
    # Coverage lives on People / Milestone Plan — not the Discussion trail desk.
    people = _workspace_block("people_desk")
    plan = _workspace_block("milestone_plan")
    assert "display: bar_chart" in people or "display: bar_chart" in plan
