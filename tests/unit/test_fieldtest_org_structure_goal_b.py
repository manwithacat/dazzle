"""Post-5.8 Goal B org_structure — fieldtest_hub Tester Roster hierarchy."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/fieldtest_hub/dsl/app.dsl"
TESTER_SEEDS = ROOT / "examples/fieldtest_hub/dsl/seeds/demo_data/Tester.jsonl"


def _tester_roster_block() -> str:
    text = APP.read_text()
    start = text.index('workspace tester_roster "Tester Roster":')
    end = text.index('workspace device_fleet "Device Fleet":', start)
    return text[start:end]


def test_tester_roster_declares_skill_and_location_before_flat() -> None:
    """Peer field-test tools show skill/region org shape before flat roster dump."""
    block = _tester_roster_block()
    assert "by_skill:" in block
    assert "display: kanban" in block
    assert "group_by: skill_level" in block
    assert "by_location:" in block
    assert "active_testers:" in block
    assert block.index("roster_metrics:") < block.index("by_skill:")
    assert block.index("by_skill:") < block.index("by_location:")
    assert block.index("by_location:") < block.index("active_testers:")
    assert block.index("active_testers:") < block.index("unassigned_devices:")


def test_tester_roster_ux_focus_org_before_load() -> None:
    block = _tester_roster_block()
    assert "focus: roster_metrics, by_skill, by_location, active_testers" in block
    assert "org structure" in block.lower() or "skill and region" in block.lower()
    # Prefer skill board over under-fold skill_mix bar theater
    assert "skill_mix:" not in block
    assert "display: bar_chart" not in block


def test_tester_seeds_span_skills_and_locations() -> None:
    """Buyer-true field org needs skill tiers and multiple regions."""
    rows = [json.loads(line) for line in TESTER_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 6
    skills = {str(r.get("skill_level") or "") for r in rows}
    locations = {str(r.get("location") or "") for r in rows}
    assert "engineer" in skills
    assert "enthusiast" in skills
    assert "casual" in skills
    assert len(locations) >= 4
    for row in rows:
        assert row.get("name")
        assert row.get("location")
        assert row.get("skill_level")


def _device_fleet_block() -> str:
    text = APP.read_text()
    start = text.index('workspace device_fleet "Device Fleet":')
    end = text.index('workspace draft_releases "Draft Releases":', start)
    return text[start:end]


def test_device_fleet_declares_model_and_lifecycle_before_queues() -> None:
    """Cycle 1938: peer fleet desks show lifecycle kanban + model roster before dumps."""
    block = _device_fleet_block()
    assert "by_status:" in block
    assert "group_by: status" in block
    assert "display: kanban" in block
    assert "by_model:" in block
    assert "sort: model asc" in block
    assert "unassigned_devices:" in block
    assert "active_devices:" in block
    # Order: pulse → hardware identity → lifecycle board → model roster → capacity.
    assert block.index("fleet_metrics:") < block.index("hardware_identity:")
    assert block.index("hardware_identity:") < block.index("by_status:")
    assert block.index("by_status:") < block.index("by_model:")
    assert block.index("by_model:") < block.index("unassigned_devices:")
    assert block.index("unassigned_devices:") < block.index("active_devices:")
    assert "focus: fleet_metrics, hardware_identity, by_status, by_model" in block
    assert "unassigned: count(Device where assigned_tester_id = null)" in block
    assert "org" in block.lower() or "lifecycle" in block.lower() or "model" in block.lower()


def test_device_seeds_span_models_for_org_boards() -> None:
    rows = [
        json.loads(line)
        for line in (ROOT / "examples/fieldtest_hub/dsl/seeds/demo_data/Device.jsonl")
        .read_text()
        .splitlines()
        if line.strip()
    ]
    models = {str(r.get("model") or "") for r in rows}
    statuses = {str(r.get("status") or "") for r in rows}
    assert len(models) >= 3
    assert "active" in statuses
    assert "prototype" in statuses or "recalled" in statuses
