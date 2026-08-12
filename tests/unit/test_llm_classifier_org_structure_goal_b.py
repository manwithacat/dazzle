"""Post-5.8 Goal B org_structure — llm_ticket_classifier Team desk hierarchy."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/llm_ticket_classifier/dsl/app.dsl"
STAFF_SEEDS = ROOT / "examples/llm_ticket_classifier/dsl/seeds/demo_data/SupportStaff.jsonl"


def _team_desk_block() -> str:
    text = APP.read_text()
    start = text.index('workspace team_desk "Team":')
    end = text.index('persona support_agent "Support Agent":', start)
    return text[start:end]


def test_support_staff_entity_declares_department_and_job_title() -> None:
    text = APP.read_text()
    start = text.index('entity SupportStaff "Support Staff":')
    end = text.index(
        "# =============================================================================\n# Surfaces",
        start,
    )
    block = text[start:end]
    assert "department: str(50)" in block
    assert "job_title: str(80)" in block
    # Domain residual: status lifecycle (onboarding → active → offboarded)
    assert "transitions:" in block
    assert "onboarding -> active:" in block
    assert "active -> offboarded:" in block


def test_support_staff_repr_fields_are_identity_chips_not_schema_dump() -> None:
    """Cycle 1935: Team desk staff cards skip Email/Status schema dump."""
    text = APP.read_text()
    start = text.index('entity SupportStaff "Support Staff":')
    block = text[start : text.index('entity TicketDocument "Ticket Document":')]
    line = block.split("repr_fields:")[1].split("\n")[0]
    assert "name" in line and "role" in line
    assert "department" in line and "job_title" in line
    assert "email" not in line
    assert "status" not in line


def test_team_desk_declares_title_board_and_dept_before_load() -> None:
    """Peer support tools show title/dept org shape before ticket load dumps."""
    block = _team_desk_block()
    assert "by_title:" in block
    assert "display: kanban" in block
    assert "group_by: job_title" in block
    assert "by_department:" in block
    roster = "\n  people:\n    source: SupportStaff"
    ticket_load = "\n  ticket_load:\n    source: Ticket"
    assert roster in block
    assert ticket_load in block
    # Order: pulse → title board → department queue → flat roster → ticket load
    assert block.index("team_pulse:") < block.index("by_title:")
    assert block.index("by_title:") < block.index("by_department:")
    assert block.index("by_department:") < block.index(roster)
    assert block.index(roster) < block.index(ticket_load)


def test_team_desk_ux_focus_org_before_load() -> None:
    block = _team_desk_block()
    assert "focus: team_pulse, by_title, by_department, people" in block
    assert "org structure" in block.lower() or "title and department" in block.lower()
    # Prefer kanban org boards over under-fold bar/timeline theater
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block
    assert "as supervisor:" in block
    assert "as support_agent:" in block
    assert "as admin:" in block


def test_staff_list_exposes_org_fields() -> None:
    text = APP.read_text()
    start = text.index('surface staff_list "Team roster":')
    end = text.index('surface staff_detail "Team member":', start)
    block = text[start:end]
    assert 'field job_title "Job Title"' in block
    assert 'field department "Department"' in block
    assert "filter: department, job_title, role, status" in block
    assert "search: name, email, department, job_title" in block


def test_staff_detail_exposes_org_fields() -> None:
    text = APP.read_text()
    start = text.index('surface staff_detail "Team member":')
    end = text.index('surface staff_create "Add Team Member":', start)
    block = text[start:end]
    assert 'field job_title "Job Title"' in block
    assert 'field department "Department"' in block


def test_nav_includes_team_desk() -> None:
    text = APP.read_text()
    agent = text[text.index("nav agent_nav:") : text.index("nav supervisor_nav:")]
    supervisor = text[
        text.index("nav supervisor_nav:") : text.index(
            "\n# =============================================================================\n# Scenarios"
        )
    ]
    assert "team_desk" in agent
    assert "team_desk" in supervisor
    assert agent.index("priority_desk") < agent.index("team_desk")
    assert supervisor.index("support_dashboard") < supervisor.index("team_desk")
    assert supervisor.index("team_desk") < supervisor.index("classification_desk")


def test_staff_seeds_span_departments_and_titles() -> None:
    """Buyer-true support org needs multi-dept staff, not a persona monoculture."""
    rows = [json.loads(line) for line in STAFF_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 10
    depts = {str(r.get("department") or "") for r in rows}
    titles = {str(r.get("job_title") or "") for r in rows}
    assert "Frontline Support" in depts
    assert "Escalations" in depts
    assert "Billing Ops" in depts
    assert "AI Ops" in depts
    assert len(depts) >= 4
    assert "Support Supervisor" in titles
    assert "Support Agent" in titles
    assert "Escalation Lead" in titles
    assert "Billing Specialist" in titles
    # Extra IC rows use c400… (c300… reserved for persona-aligned staff)
    non_persona = [r for r in rows if str(r.get("id", "")).startswith("c4000000")]
    assert len(non_persona) >= 6
    counts = Counter(str(r.get("department") or "") for r in rows)
    multi = [d for d, n in counts.items() if n >= 2]
    assert len(multi) >= 3, f"expected multi-person depts, got {counts}"
    for row in rows:
        assert row.get("name")
        assert row.get("email")
        assert row.get("department")
        assert row.get("job_title")
