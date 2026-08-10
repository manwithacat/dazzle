"""Post-5.8 Goal B org_structure — domain_join_co Team desk hierarchy."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOMAIN = ROOT / "examples/domain_join_co/dsl/domain.dsl"
MEMBER_SEEDS = ROOT / "examples/domain_join_co/dsl/seeds/demo_data/WorkspaceMember.jsonl"


def _workspace_block(name: str) -> str:
    text = DOMAIN.read_text()
    marker = f'workspace {name} "'
    start = text.index(marker)
    rest = text[start + 1 :]
    nxt = rest.find("\nworkspace ")
    if nxt == -1:
        return text[start:]
    return text[start : start + 1 + nxt]


def test_workspace_member_entity_declares_department_and_job_title() -> None:
    text = DOMAIN.read_text()
    start = text.index('entity WorkspaceMember "Workspace Member":')
    end = text.index("# ── Surfaces", start)
    block = text[start:end]
    assert "department: str(50)" in block
    assert "job_title: str(80)" in block
    assert "workspace: ref Workspace required" in block


def test_team_home_declares_title_board_and_dept_before_load() -> None:
    """Peer directory tools show title/dept org shape before board load dumps."""
    block = _workspace_block("team_home")
    assert "by_title:" in block
    assert "display: kanban" in block
    assert "group_by: job_title" in block
    assert "by_department:" in block
    roster = "\n  people:\n    source: WorkspaceMember"
    board_load = "\n  board_load:\n    source: Announcement"
    assert roster in block
    assert board_load in block
    # Order: pulse → title board → department queue → flat roster → board load
    assert block.index("team_pulse:") < block.index("by_title:")
    assert block.index("by_title:") < block.index("by_department:")
    assert block.index("by_department:") < block.index(roster)
    assert block.index(roster) < block.index(board_load)


def test_team_home_ux_focus_org_before_load() -> None:
    block = _workspace_block("team_home")
    assert "focus: team_pulse, by_title, by_department, people" in block
    assert "org structure" in block.lower() or "title and department" in block.lower()
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block
    assert "as admin:" in block
    assert "as member:" in block


def test_workspace_member_list_exposes_org_fields() -> None:
    text = DOMAIN.read_text()
    start = text.index('surface workspace_member_list "Team roster":')
    end = text.index('surface workspace_member_detail "Workspace Member":', start)
    block = text[start:end]
    assert 'field job_title "Job Title"' in block
    assert 'field department "Department"' in block
    assert "filter: department, job_title, status" in block
    assert "search: name, email, department, job_title" in block


def test_workspace_member_detail_exposes_org_fields() -> None:
    text = DOMAIN.read_text()
    start = text.index('surface workspace_member_detail "Workspace Member":')
    end = text.index('surface workspace_member_create "Add Workspace Member":', start)
    block = text[start:end]
    assert 'field job_title "Job Title"' in block
    assert 'field department "Department"' in block


def test_nav_includes_team_home() -> None:
    text = DOMAIN.read_text()
    admin = text[text.index("nav admin_nav:") : text.index("nav member_nav:")]
    member = text[text.index("nav member_nav:") : text.index("# ── Tenant root")]
    assert "team_home" in admin
    assert "team_home" in member
    assert admin.index("home") < admin.index("team_home")
    assert admin.index("team_home") < admin.index("announce")
    assert member.index("announce") < member.index("team_home")


def test_workspace_hub_related_staff() -> None:
    text = DOMAIN.read_text()
    start = text.index('surface workspace_detail "Workspace":')
    end = text.index('workspace home "Workspace Home":', start)
    block = text[start:end]
    assert 'related staff "Staff"' in block
    assert "show: WorkspaceMember" in block


def test_member_seeds_span_departments_and_titles() -> None:
    """Buyer-true joined org needs multi-dept staff, not a 2-row persona monoculture."""
    rows = [json.loads(line) for line in MEMBER_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 10
    depts = {str(r.get("department") or "") for r in rows}
    titles = {str(r.get("job_title") or "") for r in rows}
    assert "IT" in depts
    assert "People Ops" in depts
    assert "Security" in depts
    assert "Facilities" in depts
    assert len(depts) >= 4
    assert "Workspace Admin" in titles
    assert "IT Lead" in titles
    assert "People Ops Partner" in titles
    assert "Security Analyst" in titles
    counts = Counter(str(r.get("department") or "") for r in rows)
    multi = [d for d, n in counts.items() if n >= 2]
    assert len(multi) >= 3, f"expected multi-person depts, got {counts}"
    workspaces = {str(r.get("workspace") or "") for r in rows}
    assert len(workspaces) >= 2
    for row in rows:
        assert row.get("name")
        assert row.get("email")
        assert row.get("department")
        assert row.get("job_title")
        assert str(row.get("id", "")).startswith("d5000000")
