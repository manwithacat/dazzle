"""Post-5.8 Goal B org_structure — acme_billing Team desk hierarchy."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTITIES = ROOT / "examples/acme_billing/dsl/entities.dsl"
SURFACES = ROOT / "examples/acme_billing/dsl/surfaces.dsl"
USER_SEEDS = ROOT / "examples/acme_billing/dsl/seeds/demo_data/User.jsonl"


def _team_home_block() -> str:
    text = SURFACES.read_text()
    start = text.index('workspace team_home "Team":')
    end = text.index('workspace orgs_home "Organizations":', start)
    return text[start:end]


def test_user_entity_declares_department_and_job_title() -> None:
    text = ENTITIES.read_text()
    start = text.index('entity User "User":')
    end = text.index('entity Project "Project":', start)
    block = text[start:end]
    assert "department: str(50)" in block
    assert "job_title: str(80)" in block


def test_team_home_declares_title_board_and_dept_before_load() -> None:
    """Peer billing tools show title/dept org shape before membership dumps."""
    block = _team_home_block()
    assert "by_title:" in block
    assert "display: kanban" in block
    assert "group_by: job_title" in block
    assert "by_department:" in block
    people = "\n  people:\n    source: User"
    membership = "\n  membership_queue:\n    source: Membership"
    assert people in block
    assert membership in block
    # Order: pulse → title board → department queue → flat roster → membership
    assert block.index("membership_pulse:") < block.index("by_title:")
    assert block.index("by_title:") < block.index("by_department:")
    assert block.index("by_department:") < block.index(people)
    assert block.index(people) < block.index(membership)


def test_team_home_ux_focus_org_before_load() -> None:
    block = _team_home_block()
    assert "focus: membership_pulse, by_title, by_department, people" in block
    assert "org structure" in block.lower() or "title and department" in block.lower()
    # Prefer kanban org boards over under-fold bar/timeline theater
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block
    assert "as admin:" in block
    assert "as org_owner:" in block
    assert "as auditor:" in block


def test_user_list_exposes_org_fields() -> None:
    text = SURFACES.read_text()
    start = text.index('surface user_list "Users":')
    end = text.index('surface user_detail "User":', start)
    block = text[start:end]
    assert 'field job_title "Job Title"' in block
    assert 'field department "Department"' in block
    assert "filter: department, job_title, org" in block
    assert "search: name, email, department, job_title" in block


def test_user_detail_exposes_org_fields() -> None:
    text = SURFACES.read_text()
    start = text.index('surface user_detail "User":')
    end = text.index('surface user_create "Create User":', start)
    block = text[start:end]
    assert 'field job_title "Job Title"' in block
    assert 'field department "Department"' in block


def test_user_seeds_span_departments_and_titles() -> None:
    """Buyer-true billing org needs multi-dept staff, not a persona monoculture."""
    rows = [json.loads(line) for line in USER_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 12
    depts = {str(r.get("department") or "") for r in rows}
    titles = {str(r.get("job_title") or "") for r in rows}
    assert "Finance" in depts
    assert "Delivery" in depts
    assert "Platform Ops" in depts
    assert "Audit" in depts
    assert len(depts) >= 4
    assert "Org Owner" in titles
    assert "Project Analyst" in titles
    assert "Lead Auditor" in titles
    assert "Platform Admin" in titles
    # Extra IC rows use non-STABLE UUIDs (b200… reserved for IC staff)
    non_stable = [r for r in rows if str(r.get("id", "")).startswith("b2000000")]
    assert len(non_stable) >= 4
    counts = Counter(str(r.get("department") or "") for r in rows)
    multi = [d for d, n in counts.items() if n >= 2]
    assert len(multi) >= 3, f"expected multi-person depts, got {counts}"
    for row in rows:
        assert row.get("name")
        assert row.get("department")
        assert row.get("job_title")
