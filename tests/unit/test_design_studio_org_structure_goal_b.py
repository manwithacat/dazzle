"""Post-5.8 Goal B org_structure — design_studio Team desk hierarchy."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/design_studio/dsl/app.dsl"
USER_SEEDS = ROOT / "examples/design_studio/dsl/seeds/demo_data/User.jsonl"


def _team_desk_block() -> str:
    text = APP.read_text()
    start = text.index('workspace team_desk "Team":')
    end = text.index('\nsurface brand_list "Brands":', start)
    return text[start:end]


def test_user_entity_declares_department_and_job_title() -> None:
    text = APP.read_text()
    start = text.index('entity User "User":')
    end = text.index('entity Brand "Brand":', start)
    block = text[start:end]
    assert "department: str(50)" in block
    assert "job_title: str(80)" in block


def test_team_desk_declares_title_board_and_dept_before_load() -> None:
    """Peer creative tools show title/dept org shape before brand load dumps."""
    block = _team_desk_block()
    assert "by_title:" in block
    assert "display: kanban" in block
    assert "group_by: job_title" in block
    assert "by_department:" in block
    roster = "\n  people:\n    source: User"
    brand_load = "\n  brand_load:\n    source: Brand"
    assert roster in block
    assert brand_load in block
    # Order: pulse → title board → department queue → flat roster → brand load
    assert block.index("team_pulse:") < block.index("by_title:")
    assert block.index("by_title:") < block.index("by_department:")
    assert block.index("by_department:") < block.index(roster)
    assert block.index(roster) < block.index(brand_load)


def test_team_desk_ux_focus_org_before_load() -> None:
    block = _team_desk_block()
    assert "focus: team_pulse, by_title, by_department, people" in block
    assert "org structure" in block.lower() or "title and department" in block.lower()
    # Prefer kanban org boards over under-fold bar/timeline theater
    assert "display: bar_chart" not in block
    assert "display: timeline" not in block
    assert "as admin:" in block
    assert "as designer:" in block
    assert "as reviewer:" in block


def test_user_list_exposes_org_fields() -> None:
    text = APP.read_text()
    start = text.index('surface user_list "Team":')
    end = text.index('surface user_detail "Team member":', start)
    block = text[start:end]
    assert 'field job_title "Job Title"' in block
    assert 'field department "Department"' in block
    assert "filter: department, job_title, role" in block
    assert "search: name, email, department, job_title" in block


def test_user_detail_exposes_org_fields() -> None:
    text = APP.read_text()
    start = text.index('surface user_detail "Team member":')
    end = text.index('surface asset_list "Assets":', start)
    block = text[start:end]
    assert 'field job_title "Job Title"' in block
    assert 'field department "Department"' in block


def test_nav_includes_team_desk() -> None:
    text = APP.read_text()
    assert "team_desk" in text
    # designer + reviewer navs both list team_desk after active_campaigns
    designer = text[text.index("nav designer_nav:") : text.index("nav reviewer_nav:")]
    reviewer = text[text.index("nav reviewer_nav:") : text.index("# ── Entities")]
    assert "team_desk" in designer
    assert "team_desk" in reviewer
    assert designer.index("active_campaigns") < designer.index("team_desk")
    assert reviewer.index("active_campaigns") < reviewer.index("team_desk")


def test_user_seeds_span_departments_and_titles() -> None:
    """Buyer-true studio org needs multi-dept staff, not a 3-row persona monoculture."""
    rows = [json.loads(line) for line in USER_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 8
    depts = {str(r.get("department") or "") for r in rows}
    titles = {str(r.get("job_title") or "") for r in rows}
    assert "Creative Ops" in depts
    assert "Design Systems" in depts
    assert "Brand Strategy" in depts
    assert "Review QA" in depts
    assert len(depts) >= 4
    assert "Studio Admin" in titles
    assert "Brand Designer" in titles
    assert "Art Director" in titles
    assert "Review Lead" in titles
    # Extra IC rows use non-STABLE UUIDs (a100… reserved for personas)
    non_stable = [r for r in rows if str(r.get("id", "")).startswith("b2000000")]
    assert len(non_stable) >= 4
    counts = Counter(str(r.get("department") or "") for r in rows)
    multi = [d for d, n in counts.items() if n >= 2]
    assert len(multi) >= 3, f"expected multi-person depts, got {counts}"
    for row in rows:
        assert row.get("name")
        assert row.get("department")
        assert row.get("job_title")
