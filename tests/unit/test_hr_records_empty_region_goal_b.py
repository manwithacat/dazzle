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
    # Cycle 1950: focus ≤4 — composition/notes remain regions, not focus-eager.
    assert "focus: media_shelf, headcount, current_staff, recent_starters" in block
    assert "composition:" in block


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
        "focus: team_pulse, by_level, by_department, by_location, reporting_lines, composition, live_conversation"
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


def test_reporting_desk_span_is_filled_queue_not_empty_kanban() -> None:
    """Cycle 1946: Links metric with empty span kanban is dishonest — queue fills when links exist."""
    block = _workspace_block("reporting_desk")
    span_start = block.index("\n  span_of_control:")
    span_end = block.index("\n  by_department:", span_start)
    span = block[span_start:span_end]
    assert "display: queue" in span
    assert "source: ManagerLink" in span
    assert "action: managerlink_detail" in span
    assert "group_by: manager" not in span
    assert "display: kanban" not in span
    # No second primary link region competing for fold as empty twin
    assert "\n  active_links:" not in block
    assert "people_cards:" not in block
    assert "focus: reporting_pulse, span_of_control, by_department, by_location" in block
    # Placement boards still present for org shape (not only metrics)
    assert "\n  by_department:" in block
    assert "\n  by_location:" in block
