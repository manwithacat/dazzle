"""Post-5.8 Goal B empty_region_honesty — hr_records staff + manager desks (cycle 1819)."""

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


def test_staff_directory_omits_chart_and_dup_card_theater() -> None:
    """Peer HR homes: dual attention + notes — not twin people cards or status bar charts."""
    block = _workspace_block("staff_directory")
    assert "live_conversation:" in block
    assert "headcount:" in block
    assert "current_staff:" in block
    assert "recent_starters:" in block
    assert "department_context:" in block
    assert "role_context:" in block
    assert "directory_readiness:" in block
    assert "people_cards:" not in block
    assert "dept_mix:" not in block
    assert "assignment_status_mix:" not in block
    assert "display: bar_chart" not in block
    assert (
        "focus: headcount, current_staff, recent_starters, composition, live_conversation" in block
    )


def test_my_team_omits_redundant_org_bar_charts() -> None:
    """Org shape is kanban boards — under-fold dept/level bar charts are theater."""
    block = _workspace_block("my_team")
    assert "by_level:" in block
    assert "by_department:" in block
    assert "reporting_lines:" in block
    assert "composition:" in block
    assert "live_conversation:" in block
    assert "dept_mix:" not in block
    assert "role_mix_chart:" not in block
    assert "display: bar_chart" not in block
    assert (
        "focus: team_pulse, by_level, by_department, reporting_lines, composition, live_conversation"
        in block
    )


def test_hr_records_keeps_bar_chart_for_coverage() -> None:
    """Hero prune must not leave display: bar_chart fleet-uncovered."""
    text = APP.read_text()
    assert "display: bar_chart" in text
    assert text.count("display: bar_chart") >= 4
    # Secondary desks still host lifecycle / level mix charts
    assert "workspace org_chart" in text or "role_level_mix:" in text
    assert "workspace compensation_review" in text or "reason_mix:" in text
