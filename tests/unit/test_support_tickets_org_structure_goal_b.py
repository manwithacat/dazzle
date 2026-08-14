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


def test_user_entity_declares_department_and_support_tier() -> None:
    text = APP.read_text()
    start = text.index('entity User "User":')
    end = text.index('entity Ticket "Support Ticket":', start)
    block = text[start:end]
    assert "department: str(50)" in block
    assert "support_tier: enum[l1,l2,l3]=l1" in block
    repr_fields = block.split("repr_fields:")[1].split("]")[0]
    assert "department" in repr_fields
    assert "support_tier" in repr_fields


def test_people_desk_declares_tier_density_before_dept() -> None:
    """Peer Zendesk/Front put L1 frontline vs L2 escalation people before dept."""
    block = _people_desk_block()
    assert "l1_frontline:" in block
    assert "l2_escalation:" in block
    assert "support_tier = l1" in block
    assert "support_tier = l2" in block
    assert "by_department:" in block
    assert "group_by: department" in block
    assert "unassigned_work:" in block
    assert "roster:" not in block  # cycle 2052 twin prune
    # Order: pulse → L1 → L2 → role → department → load
    assert block.index("people_pulse:") < block.index("l1_frontline:")
    assert block.index("l1_frontline:") < block.index("l2_escalation:")
    assert block.index("l2_escalation:") < block.index("by_role:")
    assert block.index("by_role:") < block.index("by_department:")
    assert block.index("by_department:") < block.index("unassigned_work:")
    assert block.index("unassigned_work:") < block.index("plate_by_person:")
    # Tier metrics for routing read
    assert "l1: count(User where" in block
    assert "l2: count(User where" in block
    assert "l3: count(User where" in block


def test_people_desk_ux_focus_tier_density() -> None:
    block = _people_desk_block()
    assert "focus: people_pulse, l1_frontline, l2_escalation, by_department" in block
    assert (
        "support_tier_density" in block.lower()
        or "l1/l2" in block.lower()
        or "tier" in block.lower()
    )
    assert "twin roster" in block.lower() or "no twin" in block.lower()


def test_manager_nav_includes_people_desk() -> None:
    text = APP.read_text()
    start = text.index("nav manager_nav:")
    end = text.index(
        "# =============================================================================", start
    )
    nav = text[start:end]
    assert "people_desk" in nav
    assert nav.index("manager_ops") < nav.index("people_desk")


def test_user_seeds_span_tiers_and_departments() -> None:
    """Buyer-true org needs L1/L2/L3 staff across depts, not Support monoculture."""
    rows = [json.loads(line) for line in USER_SEEDS.read_text().splitlines() if line.strip()]
    staff = [r for r in rows if r.get("role") in ("agent", "manager")]
    assert len(staff) >= 5
    depts = {str(r.get("department") or "") for r in staff}
    assert "Support" in depts
    assert "Escalations" in depts
    assert "Billing" in depts
    assert len(depts) >= 3
    tiers = {str(r.get("support_tier") or "") for r in staff}
    assert "l1" in tiers
    assert "l2" in tiers
    assert "l3" in tiers
    l1 = [r for r in staff if r.get("support_tier") == "l1"]
    l2 = [r for r in staff if r.get("support_tier") == "l2"]
    l3 = [r for r in staff if r.get("support_tier") == "l3"]
    assert len(l1) >= 3
    assert len(l2) >= 2
    assert len(l3) >= 1
    for row in staff:
        assert row.get("name")
        assert row.get("department")
        assert row.get("support_tier") in ("l1", "l2", "l3")
