"""Post-5.8 Goal B org_structure — hr_records My Team + Reporting hierarchy.

Cycle 1914 peer-pack upgrade: work_location_grain (BambooHR / Workday place
grain) — Person.work_location + by_location boards + remote/hybrid metrics.
Not headshot_shelf; not media/document/conversation/command_density re-stack.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/hr_records/dsl/app.dsl"
PERSON_SEEDS = ROOT / "examples/hr_records/dsl/seeds/demo_data/Person.jsonl"


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


def test_person_entity_declares_work_location() -> None:
    text = APP.read_text()
    start = text.index('entity Person "Person":')
    end = text.index('entity PersonNote "Person Note":', start)
    block = text[start:end]
    assert (
        "work_location: enum[london_hq,manchester,remote_uk,hybrid,client_site]=london_hq" in block
    )
    assert "work_location" in block.split("repr_fields:")[1].split("]")[0]


def test_my_team_declares_level_dept_location_boards_before_conversation() -> None:
    """Peer HR tools show level/dept/location org shape before conversation thrash."""
    block = _my_team_block()
    assert "by_level:" in block
    assert "display: kanban" in block
    assert "group_by: level" in block
    assert "by_department:" in block
    assert "group_by: department" in block
    assert "by_location:" in block
    assert "group_by: work_location" in block
    assert "live_conversation:" in block
    # Region headers (indent 2) — avoid team_pulse aggregate key "reporting_lines:"
    assert "\n  by_level:" in block
    assert "\n  by_department:" in block
    assert "\n  by_location:" in block
    assert "\n  reporting_lines:" in block
    # Order: pulse → level → department → location → reporting → conversation
    assert block.index("team_pulse:") < block.index("\n  by_level:")
    assert block.index("\n  by_level:") < block.index("\n  by_department:")
    assert block.index("\n  by_department:") < block.index("\n  by_location:")
    assert block.index("\n  by_location:") < block.index("\n  reporting_lines:")
    assert block.index("\n  reporting_lines:") < block.index("live_conversation:")


def test_my_team_ux_focus_org_before_load() -> None:
    block = _my_team_block()
    assert (
        "focus: team_pulse, by_level, by_department, by_location, reporting_lines, composition, live_conversation"
        in block
    )
    # Cycle 1819 empty_region: no under-fold bar theater (kanbans own org shape)
    assert "dept_mix:" not in block
    assert "role_mix_chart:" not in block
    assert "display: bar_chart" not in block
    assert "multi-panel" in block.lower() or "dual attention" in block.lower()
    assert "work_location" in block or "by_location" in block
    assert "remote_uk: count(Person where work_location = remote_uk" in block
    assert "hybrid: count(Person where work_location = hybrid" in block


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
    assert "\n  by_location:" in block
    assert "group_by: work_location" in block
    assert "display: kanban" in block
    assert "\n  active_links:" in block
    # People hierarchy before flat queue / dept-name bar theater
    assert block.index("reporting_pulse:") < block.index("\n  span_of_control:")
    assert block.index("\n  span_of_control:") < block.index("\n  by_department:")
    assert block.index("\n  by_department:") < block.index("\n  by_location:")
    assert block.index("\n  by_location:") < block.index("\n  active_links:")
    assert "dept_mix:" not in block
    assert "bar_chart" not in block


def test_reporting_desk_ux_focus_org_people() -> None:
    block = _reporting_desk_block()
    assert (
        "focus: reporting_pulse, span_of_control, by_department, by_location, active_links" in block
    )
    assert "span of control" in block.lower() or "Span of control" in block
    assert "remote_uk: count(Person where work_location = remote_uk" in block


def test_person_surfaces_expose_work_location() -> None:
    text = APP.read_text()
    assert 'field work_location "Work location"' in text
    # list + detail + create + edit
    assert text.count('field work_location "Work location"') >= 4


def test_person_seeds_span_work_locations() -> None:
    """Buyer-true org place grain needs HQ / remote / hybrid — not monoculture HQ."""
    rows = [json.loads(line) for line in PERSON_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 8
    locs = {str(r.get("work_location") or "") for r in rows}
    assert "london_hq" in locs
    assert "remote_uk" in locs
    assert "hybrid" in locs
    assert len(locs) >= 4
    for row in rows:
        assert row.get("work_location"), row
