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
    """Peer HR tools show IC vs manager career tracks before full level kanban."""
    block = _my_team_block()
    assert "ic_track:" in block
    assert "manager_track:" in block
    assert "by_level:" in block
    assert "display: kanban" in block
    assert "group_by: level" in block
    assert "by_department:" in block
    assert "group_by: department" in block
    assert "by_location:" in block
    assert "group_by: work_location" in block
    assert "live_conversation:" in block
    assert "\n  by_level:" in block
    assert "\n  by_department:" in block
    assert "\n  by_location:" in block
    assert "\n  reporting_lines:" in block
    # Order: career pulse → IC track → manager track → office/remote → level board
    assert block.index("career_pulse:") < block.index("\n  ic_track:")
    assert block.index("\n  ic_track:") < block.index("\n  manager_track:")
    assert block.index("\n  manager_track:") < block.index("\n  office_sites:")
    assert block.index("\n  office_sites:") < block.index("\n  remote_flex:")
    assert block.index("\n  remote_flex:") < block.index("\n  by_level:")
    assert block.index("\n  by_level:") < block.index("\n  by_department:")
    assert block.index("\n  by_department:") < block.index("\n  by_location:")
    assert block.index("\n  by_location:") < block.index("\n  reporting_lines:")
    assert block.index("\n  reporting_lines:") < block.index("live_conversation:")


def test_my_team_ux_focus_org_before_load() -> None:
    block = _my_team_block()
    assert "focus: career_pulse, ic_track, manager_track, by_department" in block
    assert (
        "career_track_density" in block.lower()
        or "ic vs" in block.lower()
        or "people-manager" in block.lower()
    )
    # Cycle 1819 empty_region: no under-fold bar theater (kanbans own org shape)
    assert "dept_mix:" not in block
    assert "role_mix_chart:" not in block
    assert "display: bar_chart" not in block
    assert "work_location" in block or "by_location" in block
    assert "ic_roles: count(Role where" in block
    assert "manager_roles: count(Role where" in block
    rows = [json.loads(line) for line in PERSON_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 5
    # Role seeds span IC + manager tracks
    role_path = ROOT / "examples/hr_records/dsl/seeds/demo_data/Role.jsonl"
    roles = [json.loads(line) for line in role_path.read_text().splitlines() if line.strip()]
    ic = [r for r in roles if str(r.get("level", "")).startswith("ic")]
    mgr = [r for r in roles if str(r.get("level", "")).startswith("m")]
    assert len(ic) >= 3
    assert len(mgr) >= 2


def test_my_team_reporting_lines_are_queue_not_only_timeline() -> None:
    """Buyer-true reporting lines open as a pull queue (ManagerLink detail)."""
    block = _my_team_block()
    start = block.index("\n  reporting_lines:")
    end = block.index("\n  ux:", start) if "\n  ux:" in block[start:] else start + 400
    region = block[start:end]
    assert "display: queue" in region
    assert "action: managerlink_detail" in region


def test_reporting_desk_span_of_control_before_flat_queue() -> None:
    """Peer HR tools show filled report→manager span + placement boards (not empty kanban void)."""
    block = _reporting_desk_block()
    assert "\n  span_of_control:" in block
    assert "\n  by_department:" in block
    assert "\n  by_location:" in block
    assert "group_by: work_location" in block
    assert "group_by: department" in block
    assert "display: kanban" in block
    # Cycle 1946 empty_region: span is a filled ManagerLink queue, not empty group_by:manager kanban
    span_start = block.index("\n  span_of_control:")
    span_end = block.index("\n  by_department:", span_start)
    span = block[span_start:span_end]
    assert "display: queue" in span
    assert "action: managerlink_detail" in span
    assert "group_by: manager" not in span
    assert "filter: end_date = null" in span
    # People hierarchy before dept-name bar theater
    assert block.index("reporting_pulse:") < block.index("\n  office_sites:")
    assert block.index("\n  office_sites:") < block.index("\n  remote_flex:")
    assert block.index("\n  remote_flex:") < block.index("\n  span_of_control:")
    assert block.index("\n  span_of_control:") < block.index("\n  by_department:")
    assert block.index("\n  by_department:") < block.index("\n  by_location:")
    assert "dept_mix:" not in block
    assert "bar_chart" not in block
    assert "\n  active_links:" not in block
    assert "people_cards:" not in block


def test_reporting_desk_ux_focus_org_people() -> None:
    block = _reporting_desk_block()
    assert (
        "focus: reporting_pulse, office_sites, remote_flex, span_of_control, by_department, by_location"
        in block
    )
    assert (
        "span of control" in block.lower()
        or "Span of control" in block
        or "report→manager" in block
    )
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


def test_my_team_and_reporting_office_remote_density() -> None:
    """Cycle 2050: BambooHR/Workday office↔remote dual presence (office_remote_density).

    Not by_location-only work_location_grain re-stack, not department metric tiles alone.
    """
    office_filter = (
        "ended_at = null and (work_location = london_hq or work_location = manchester "
        "or work_location = client_site)"
    )
    remote_filter = "ended_at = null and (work_location = remote_uk or work_location = hybrid)"
    team = _my_team_block()
    assert "\n  office_sites:\n" in team
    assert "\n  remote_flex:\n" in team
    office = team.split("\n  office_sites:\n", 1)[1].split("\n  remote_flex:", 1)[0]
    assert "source: Person" in office
    assert "work_location = london_hq" in office
    assert "display: queue" in office
    assert "limit: 4" in office
    remote = team.split("\n  remote_flex:\n", 1)[1].split("\n  by_level:", 1)[0]
    assert "source: Person" in remote
    assert "work_location = remote_uk" in remote
    assert "work_location = hybrid" in remote
    assert "display: queue" in remote
    assert f"office_sites: count(Person where {office_filter})" in team
    assert f"remote_flex: count(Person where {remote_filter})" in team
    assert team.index("\n  office_sites:\n") < team.index("\n  by_level:\n")

    desk = _reporting_desk_block()
    assert "\n  office_sites:\n" in desk
    assert "\n  remote_flex:\n" in desk
    assert desk.index("\n  office_sites:\n") < desk.index("\n  span_of_control:\n")
    assert f"office_sites: count(Person where {office_filter})" in desk
