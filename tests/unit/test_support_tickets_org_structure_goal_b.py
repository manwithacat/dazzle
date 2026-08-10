"""Post-5.8 Goal B org_structure — support_tickets People desk hierarchy."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/support_tickets/dsl/app.dsl"
USER_SEEDS = ROOT / "examples/support_tickets/dsl/seeds/demo_data/User.jsonl"


def _people_desk_block() -> str:
    text = APP.read_text()
    start = text.index('workspace people_desk "People":')
    end = text.index('persona admin "Administrator":', start)
    return text[start:end]


def test_user_entity_declares_department() -> None:
    text = APP.read_text()
    start = text.index('entity User "User":')
    end = text.index('entity Ticket "Support Ticket":', start)
    block = text[start:end]
    assert "department: str(50)" in block
    assert "department" in block.split("repr_fields:")[1].split("]")[0]


def test_people_desk_declares_role_board_and_dept_before_load() -> None:
    """Peer support tools show role/dept org shape before unassigned dump."""
    block = _people_desk_block()
    assert "by_role:" in block
    assert "display: kanban" in block
    assert "group_by: role" in block
    assert "by_department:" in block
    assert "unassigned_work:" in block
    assert block.index("people_pulse:") < block.index("by_role:")
    assert block.index("by_role:") < block.index("by_department:")
    assert block.index("by_department:") < block.index("roster:")
    assert block.index("roster:") < block.index("unassigned_work:")


def test_people_desk_ux_focus_org_before_load() -> None:
    block = _people_desk_block()
    assert "focus: people_pulse, by_role, by_department, roster" in block
    assert "org structure" in block.lower() or "role and department" in block.lower()


def test_manager_nav_includes_people_desk() -> None:
    text = APP.read_text()
    start = text.index("nav manager_nav:")
    end = text.index(
        "# =============================================================================", start
    )
    nav = text[start:end]
    assert "people_desk" in nav
    assert nav.index("manager_ops") < nav.index("people_desk")


def test_user_seeds_span_multiple_departments() -> None:
    """Buyer-true org shape needs staff across depts, not Support monoculture."""
    rows = [json.loads(line) for line in USER_SEEDS.read_text().splitlines() if line.strip()]
    staff = [r for r in rows if r.get("role") in ("agent", "manager")]
    assert len(staff) >= 5
    depts = {str(r.get("department") or "") for r in staff}
    assert "Support" in depts
    assert "Escalations" in depts
    assert "Billing" in depts
    assert len(depts) >= 3
    for row in staff:
        assert row.get("name")
        assert row.get("department")
