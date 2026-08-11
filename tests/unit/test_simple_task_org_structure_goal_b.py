"""Post-5.8 Goal B org_structure — simple_task People desk hierarchy."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/simple_task/dsl/app.dsl"
USER_SEEDS = ROOT / "examples/simple_task/dsl/seeds/demo_data/User.jsonl"


def _people_desk_block() -> str:
    text = APP.read_text()
    start = text.index('workspace people_desk "People":')
    # people_desk is last workspace in app.dsl — take rest of file
    return text[start:]


def test_people_desk_declares_role_board_and_dept_before_unassigned() -> None:
    """Peer task tools show role/dept org shape before unassigned task dumps."""
    block = _people_desk_block()
    assert "by_role:" in block
    assert "display: kanban" in block
    assert "group_by: role" in block
    assert "by_department:" in block
    assert "unassigned_work:" in block
    assert "plate_by_person:" in block
    # Order: pulse → role → department → unassigned → plate
    # (cycle 1916: roster/chart voids dropped; load fills secondary fold)
    assert block.index("people_pulse:") < block.index("by_role:")
    assert block.index("by_role:") < block.index("by_department:")
    assert block.index("by_department:") < block.index("unassigned_work:")
    assert block.index("unassigned_work:") < block.index("plate_by_person:")


def test_people_desk_ux_focus_org_before_load() -> None:
    block = _people_desk_block()
    assert "focus: people_pulse, by_role, by_department, unassigned_work, plate_by_person" in block
    # empty_region@1916: no department/load bar theater on people desk
    assert "dept_mix:" not in block
    assert "load_mix:" not in block
    assert "org shape" in block.lower() or "org structure" in block.lower()


def test_user_seeds_span_multiple_departments() -> None:
    """Buyer-true org shape needs people across depts, not Engineering monoculture."""
    rows = [json.loads(line) for line in USER_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 7
    depts = {str(r.get("department") or "") for r in rows}
    assert "Engineering" in depts
    assert "Design" in depts
    assert "Product" in depts
    assert "Ops" in depts
    assert len(depts) >= 4
    # Extra IC rows must use non-STABLE UUIDs (a100… reserved personas)
    non_stable = [r for r in rows if str(r.get("id", "")).startswith("b2000000")]
    assert len(non_stable) >= 2
    for row in rows:
        assert row.get("name")
        assert row.get("department")
