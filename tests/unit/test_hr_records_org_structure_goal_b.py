"""Post-5.8 Goal B org_structure — hr_records My Team + Reporting hierarchy."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/hr_records/dsl/app.dsl"


def _my_team_block() -> str:
    text = APP.read_text()
    start = text.index('workspace my_team "My Team":')
    end = text.index('workspace starters_desk "New Starters":', start)
    return text[start:end]


def _reporting_desk_block() -> str:
    text = APP.read_text()
    start = text.index('workspace reporting_desk "Reporting":')
    end = text.index('workspace active_staff "Active Staff":', start)
    return text[start:end]


def test_my_team_declares_level_and_dept_boards_before_conversation() -> None:
    """Peer HR tools show level/dept org shape before conversation thrash."""
    block = _my_team_block()
    assert "by_level:" in block
    assert "display: kanban" in block
    assert "group_by: level" in block
    assert "by_department:" in block
    assert "group_by: department" in block
    assert "live_conversation:" in block
    # Region headers (indent 2) — avoid team_pulse aggregate key "reporting_lines:"
    assert "\n  by_level:" in block
    assert "\n  by_department:" in block
    assert "\n  reporting_lines:" in block
    # Order: pulse → level board → department board → reporting → conversation
    assert block.index("team_pulse:") < block.index("\n  by_level:")
    assert block.index("\n  by_level:") < block.index("\n  by_department:")
    assert block.index("\n  by_department:") < block.index("\n  reporting_lines:")
    assert block.index("\n  reporting_lines:") < block.index("live_conversation:")


def test_my_team_ux_focus_org_before_load() -> None:
    block = _my_team_block()
    # Cycle 1837 command_density: dual attention boards before notes trail.
    assert "focus: team_pulse, by_level, by_department, reporting_lines, live_conversation" in block
    # Cycle 1819 empty_region: no under-fold bar theater (kanbans own org shape)
    assert "dept_mix:" not in block
    assert "role_mix_chart:" not in block
    assert "display: bar_chart" not in block
    assert "multi-panel" in block.lower() or "dual attention" in block.lower()


def test_my_team_reporting_lines_are_queue_not_only_timeline() -> None:
    """Buyer-true reporting lines open as a pull queue (ManagerLink detail)."""
    block = _my_team_block()
    start = block.index("\n  reporting_lines:")
    end = block.index("\n  ux:", start) if "\n  ux:" in block[start:] else start + 400
    region = block[start:end]
    assert "display: queue" in region
    assert "action: managerlink_detail" in region


def test_reporting_desk_span_of_control_before_flat_queue() -> None:
    """Peer HR tools show span-of-control people columns, not only a link table."""
    block = _reporting_desk_block()
    assert "\n  span_of_control:" in block
    assert "group_by: manager" in block
    assert "\n  by_department:" in block
    assert "display: kanban" in block
    assert "\n  active_links:" in block
    # People hierarchy before flat queue / dept-name bar theater
    assert block.index("reporting_pulse:") < block.index("\n  span_of_control:")
    assert block.index("\n  span_of_control:") < block.index("\n  by_department:")
    assert block.index("\n  by_department:") < block.index("\n  active_links:")
    assert "dept_mix:" not in block
    assert "bar_chart" not in block


def test_reporting_desk_ux_focus_org_people() -> None:
    block = _reporting_desk_block()
    assert "focus: reporting_pulse, span_of_control, by_department, active_links" in block
    assert "focus: reporting_pulse, span_of_control, active_links, people_cards" in block
    assert "span of control" in block.lower() or "Span of control" in block
