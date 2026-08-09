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
        "focus: portfolio_metrics, open_task_queue, composition, live_conversation, "
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
