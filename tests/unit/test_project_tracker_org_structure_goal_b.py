"""Post-5.8 Goal B org_structure — project_tracker People desk hierarchy."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/project_tracker/dsl/app.dsl"
USER_SEEDS = ROOT / "examples/project_tracker/dsl/seeds/demo_data/User.jsonl"


def _people_desk_block() -> str:
    text = APP.read_text()
    start = text.index('workspace people_desk "People":')
    end = text.index('surface project_list "Projects":', start)
    return text[start:end]


def test_people_desk_declares_role_board_and_dept_before_unassigned() -> None:
    """Peer PM tools show role/dept org shape before unassigned task dumps."""
    block = _people_desk_block()
    assert "by_role:" in block
    assert "display: kanban" in block
    assert "group_by: role" in block
    assert "by_department:" in block
    assert "project_owners:" in block
    assert "unassigned:" in block
    # Order: pulse → role board → department queue → owners → unassigned
    assert block.index("team_pulse:") < block.index("by_role:")
    assert block.index("by_role:") < block.index("by_department:")
    assert block.index("by_department:") < block.index("project_owners:")
    assert block.index("project_owners:") < block.index("unassigned:")


def test_people_desk_ux_focus_org_before_load() -> None:
    block = _people_desk_block()
    assert "focus: team_pulse, by_role, by_department, project_owners" in block
    assert "dept_mix:" in block
    assert "group_by: department" in block
    assert "org structure" in block.lower() or "Org structure" in block


def test_user_seeds_span_multiple_departments() -> None:
    """Buyer-true org shape needs people across depts, not a 3-row monoculture."""
    rows = [json.loads(line) for line in USER_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 5
    depts = {str(r.get("department") or "") for r in rows}
    assert "Engineering" in depts
    assert "Ops" in depts
    assert len(depts) >= 3
    # Extra IC rows must use non-STABLE UUIDs (a100…004+ are reserved personas)
    non_stable = [r for r in rows if str(r.get("id", "")).startswith("b2000000")]
    assert len(non_stable) >= 2
    for row in rows:
        assert row.get("name")
        assert row.get("department")
