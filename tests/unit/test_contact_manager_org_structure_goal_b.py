"""Post-5.8 Goal B org_structure — contact_manager Companies desk hierarchy."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "examples/contact_manager/dsl/app.dsl"
CONTACT_SEEDS = ROOT / "examples/contact_manager/demo_data/Contact.jsonl"


def _companies_block() -> str:
    text = APP.read_text()
    start = text.index('workspace companies "Companies":')
    # last workspace in app.dsl — take to EOF
    return text[start:]


def test_companies_declares_title_board_and_company_before_recents() -> None:
    """Peer CRM tools show job-title / company org shape before flat recents."""
    block = _companies_block()
    assert "by_title:" in block
    assert "display: kanban" in block
    assert "group_by: job_title" in block
    assert "by_company:" in block
    assert "recent_people:" in block
    # Order: pulse → title board → company queue → flat recents
    assert block.index("company_pulse:") < block.index("by_title:")
    assert block.index("by_title:") < block.index("by_company:")
    assert block.index("by_company:") < block.index("recent_people:")


def test_companies_ux_focus_org_before_load() -> None:
    block = _companies_block()
    assert "focus: company_pulse, by_title, by_company, recent_people" in block
    assert "org structure" in block.lower()
    # Prefer kanban title board over under-fold company bar theater
    assert "company_mix:" not in block
    assert "company_chart:" not in block
    assert "display: bar_chart" not in block
    assert "as user:" in block
    assert "as admin:" in block


def test_contact_list_exposes_job_title_and_company_filters() -> None:
    text = APP.read_text()
    start = text.index('surface contact_list "Contacts":')
    end = text.index('surface contact_detail "Contact Detail":', start)
    block = text[start:end]
    assert 'field job_title "Job Title"' in block
    assert "filter: is_favorite, company, job_title" in block
    assert "search: first_name, last_name, email, company, job_title" in block


def test_nav_includes_companies_desk() -> None:
    text = APP.read_text()
    start = text.index("nav contact_nav:")
    end = text.index("# Entity for contact information", start)
    nav = text[start:end]
    assert "companies" in nav
    assert nav.index("contacts") < nav.index("companies")


def test_contact_seeds_span_titles_and_multi_person_companies() -> None:
    """Buyer-true org needs multiple job titles and multi-person accounts."""
    rows = [json.loads(line) for line in CONTACT_SEEDS.read_text().splitlines() if line.strip()]
    assert len(rows) >= 20
    titles = {str(r.get("job_title") or "") for r in rows}
    companies = {str(r.get("company") or "") for r in rows if r.get("company")}
    assert "Account Manager" in titles
    assert "Sales Director" in titles
    assert "Software Engineer" in titles
    assert len(titles) >= 5
    # Multi-person accounts — not 30 singleton company names
    from collections import Counter

    counts = Counter(str(r.get("company") or "") for r in rows if r.get("company"))
    multi = [c for c, n in counts.items() if n >= 3]
    assert len(multi) >= 4, f"expected ≥4 multi-person companies, got {counts}"
    assert "Northwind Trading" in companies or "Contoso Labs" in companies
    for row in rows:
        assert row.get("first_name")
        assert row.get("last_name")
        assert row.get("job_title")
        assert row.get("company")
