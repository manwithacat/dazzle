"""Post-5.8 Goal B empty_region_honesty — llm_ticket_classifier dashboards."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/llm_ticket_classifier/dsl/app.dsl"


def _workspace_block(name: str) -> str:
    text = APP.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        return text[start:]
    return text[start : start + 1 + nxt]


def test_support_dashboard_omits_status_board_and_chart_theater() -> None:
    """Peer AI triage home: dual attention + docs + replies, not open kanban / status bar."""
    block = _workspace_block("support_dashboard")
    assert "high_severity:" in block
    assert "open_attention:" in block
    assert "composition:" in block
    assert "live_ai_replies:" in block
    assert "triage_readiness:" in block
    assert "open_board:" not in block
    assert "status_mix:" not in block
    assert "priority_strip:" not in block
    assert "display: kanban" not in block
    assert "display: bar_chart" not in block
    # Purpose language may cite documents; still no chart theater.
    assert "multi-panel" in block.lower() or "case documents" in block.lower()


def test_ticket_management_drops_twin_queues_and_priority_chart() -> None:
    """Agent desk: one worklist + AI trail — not open_only / pipeline / priority_mix."""
    block = _workspace_block("ticket_management")
    assert "live_ai_replies:" in block
    assert "ticket_queue:" in block
    assert "classification_trail:" in block
    assert "desk_readiness:" in block
    assert "open_only:" not in block
    assert "pipeline_board:" not in block
    assert "priority_mix:" not in block
    assert "display: kanban" not in block
    assert "display: bar_chart" not in block
    assert (
        "focus: case_brief_covers, agent_pulse, live_ai_replies, ticket_queue, "
        "classification_trail, desk_readiness" in block
    )


def test_command_density_spine_still_first() -> None:
    """Empty-region prune must not reorder dual attention → docs → conversation."""
    block = _workspace_block("support_dashboard")
    assert block.index("high_severity:") < block.index("open_attention:")
    assert block.index("open_attention:") < block.index("composition:")
    assert block.index("composition:") < block.index("live_ai_replies:")
    assert block.index("live_ai_replies:") < block.index("triage_readiness:")
