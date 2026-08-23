"""Download filenames must not dump EngagementLetter (oral #195)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.core.strings import entity_slug
from dazzle.http.runtime.workspace_csv import render_entity_list_csv
from dazzle.render.breadcrumbs import (
    clerk_entity_download_stem,
    clerk_entity_noun,
    entity_path_labels_from_spec,
)
from dazzle.signing.routes import _signed_pdf_filename

CONTACT = Path("examples/contact_manager")
SUPPORT = Path("examples/support_tickets")
FIELDTEST = Path("examples/fieldtest_hub")
_LETTER_ID = "a1000000-0000-4000-8000-000000000001"


def test_contact_engagement_letter_download_stem_is_live() -> None:
    spec = load_project(CONTACT)
    letter = next(e for e in spec.domain.entities if e.name == "EngagementLetter")
    assert letter.title == "Engagement Letter"
    assert entity_slug("EngagementLetter") == "engagementletter"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_noun("EngagementLetter", labels) == "Engagement Letter"
    assert clerk_entity_download_stem("EngagementLetter", labels) == "engagement-letter"
    assert clerk_entity_download_stem("EngagementLetter") == "engagement-letter"


def test_support_sla_waiver_download_stem_is_live() -> None:
    spec = load_project(SUPPORT)
    waiver = next(e for e in spec.domain.entities if e.name == "SlaWaiver")
    assert waiver.title == "SLA Waiver"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_download_stem("SlaWaiver", labels) == "sla-waiver"


def test_fieldtest_issue_report_download_stem_is_live() -> None:
    spec = load_project(FIELDTEST)
    issue = next(e for e in spec.domain.entities if e.name == "IssueReport")
    assert issue.title == "Issue Report"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_download_stem("IssueReport", labels) == "issue-report"


def test_signed_pdf_filename_engagement_letter_not_pascal() -> None:
    spec = load_project(CONTACT)
    letter = next(e for e in spec.domain.entities if e.name == "EngagementLetter")
    name = _signed_pdf_filename(letter, _LETTER_ID)
    assert name == f"engagement-letter-{_LETTER_ID}.pdf"
    assert "EngagementLetter" not in name
    signed = _signed_pdf_filename(letter, _LETTER_ID, signed=True)
    assert signed == f"engagement-letter-{_LETTER_ID}-signed.pdf"


def test_entity_list_csv_filename_engagement_letter_not_pascal() -> None:
    columns = [{"key": "title", "label": "Title", "type": "text"}]
    resp = render_entity_list_csv([{"title": "Q3 retainer"}], columns, "EngagementLetter")
    cd = resp.headers["content-disposition"]
    assert 'filename="engagement-letter.csv"' in cd
    assert "EngagementLetter.csv" not in cd


def test_leftover_zzz_invents_no_entity() -> None:
    spec = load_project(CONTACT)
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_download_stem("zzz", labels) == "zzz"
    assert clerk_entity_download_stem("ghost", labels) == "ghost"
    resp = render_entity_list_csv(
        [{"title": "x"}],
        [{"key": "title", "label": "Title", "type": "text"}],
        "zzz",
    )
    assert 'filename="zzz.csv"' in resp.headers["content-disposition"]
    assert "engagement-letter.csv" not in resp.headers["content-disposition"]
