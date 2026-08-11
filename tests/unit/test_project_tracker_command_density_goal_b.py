"""Post-5.8 Goal B command_density — project_tracker Dashboard/My Tasks dual attention (cycle 1833)."""

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


def test_dashboard_dual_attention_before_conversation() -> None:
    """Peer PM homes put open work + deliverables above discussion trail."""
    block = _workspace_block("dashboard")
    assert "portfolio_metrics:" in block
    assert "open_task_queue:" in block
    assert "composition:" in block
    assert "live_conversation:" in block
    assert block.index("portfolio_metrics:") < block.index("open_task_queue:")
    assert block.index("open_task_queue:") < block.index("composition:")
    assert block.index("composition:") < block.index("live_conversation:")
    assert (
        "focus: media_shelf, portfolio_metrics, open_task_queue, composition, live_conversation, "
        "project_overview, task_flow" in block
    )
    assert "Multi-panel" in block or "multi-panel" in block.lower()


def test_my_tasks_dual_attention_before_conversation() -> None:
    block = _workspace_block("my_tasks")
    assert "load:" in block
    assert "assigned_queue:" in block
    assert "board:" in block
    assert "live_conversation:" in block
    assert block.index("load:") < block.index("assigned_queue:")
    assert block.index("assigned_queue:") < block.index("board:")
    assert block.index("board:") < block.index("live_conversation:")
    assert "focus: load, assigned_queue, board, live_conversation" in block


def test_attention_queues_capped_for_fold_share() -> None:
    home = _workspace_block("dashboard")
    mine = _workspace_block("my_tasks")
    assert "limit: 4" in home
    assert "limit: 4" in mine
    assert "display: conversation" in home
    assert "display: conversation" in mine


def test_project_board_dual_attention_unassigned_and_overdue() -> None:
    """Peer Linear/Jira boards: claim work + past-due pressure beside kanban."""
    block = _workspace_block("project_board")
    assert "board_metrics:" in block
    assert "task_board:" in block
    assert "unassigned_queue:" in block
    assert "overdue_queue:" in block
    assert "milestones:" in block
    assert "filter: assigned_to = null and status != done" in block
    assert "filter: due_date < today and status != done" in block
    assert "unassigned: count(Task where assigned_to = null and status != done)" in block
    assert "overdue: count(Task where due_date < today and status != done)" in block
    assert "critical: count(Task where priority = critical and status != done)" in block
    # Order: metrics → kanban → unassigned → overdue → milestones
    assert block.index("board_metrics:") < block.index("task_board:")
    assert block.index("task_board:") < block.index("unassigned_queue:")
    assert block.index("unassigned_queue:") < block.index("overdue_queue:")
    assert block.index("overdue_queue:") < block.index("milestones:")
    assert "focus: board_metrics, task_board, unassigned_queue, overdue_queue, milestones" in block
    assert "Multi-panel" in block or "multi-panel" in block.lower()
    assert "dual attention" in block.lower()
