"""Destructive confirm must not dump issuereport (oral #194)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.core.strings import entity_slug
from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
from dazzle.render.breadcrumbs import (
    clerk_entity_confirm_noun,
    clerk_entity_noun,
    entity_path_labels_from_spec,
)
from dazzle.render.fragment.renderer._data_row import _render_table_row

FIELDTEST = Path("examples/fieldtest_hub")
CONTACT = Path("examples/contact_manager")
_ISSUE_ID = "c3000000-0000-4000-8000-000000000001"


def _issue_row_html(*, entity_name: str = "IssueReport", entity_title: str = "") -> str:
    table = {
        "entity_name": entity_name,
        "entity_title": entity_title,
        "api_endpoint": "/api/issuereports",
        "can_delete": True,
        "can_update": False,
        "columns": [{"key": "title", "type": "text", "label": "Title"}],
    }
    item = {"id": _ISSUE_ID, "title": "Login loop"}
    return _render_table_row(table, item)


def test_fieldtest_issue_report_confirm_noun_is_live() -> None:
    spec = load_project(FIELDTEST)
    issue = next(e for e in spec.domain.entities if e.name == "IssueReport")
    assert issue.title == "Issue Report"
    assert entity_slug("IssueReport") == "issuereport"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_noun("IssueReport", labels) == "Issue Report"
    assert clerk_entity_confirm_noun("IssueReport", labels) == "issue report"
    assert clerk_entity_confirm_noun("IssueReport") == "issue report"


def test_contact_engagement_letter_confirm_noun_is_live() -> None:
    spec = load_project(CONTACT)
    letter = next(e for e in spec.domain.entities if e.name == "EngagementLetter")
    assert letter.title == "Engagement Letter"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_confirm_noun("EngagementLetter", labels) == "engagement letter"


def test_row_confirm_issue_report_not_issuereport() -> None:
    spec = load_project(FIELDTEST)
    labels = entity_path_labels_from_spec(spec)
    html = _issue_row_html(entity_title=labels["issuereport"])
    assert 'hx-confirm="Delete this issue report?"' in html
    assert 'hx-confirm="Delete this issuereport?"' not in html
    split = _issue_row_html()
    assert 'hx-confirm="Delete this issue report?"' in split
    assert 'hx-confirm="Delete this issuereport?"' not in split


def test_detail_confirm_issue_report_not_issuereport() -> None:
    adapter = FragmentSurfaceAdapter()
    actions = adapter._build_detail_actions(
        {
            "delete_url": "/_dazzle/issuereport/c3000000-0000-4000-8000-000000000001",
            "entity_name": "IssueReport",
            "entity_title": "Issue Report",
        }
    )
    confirm = getattr(actions[0], "hx_confirm", None) or ""
    assert confirm == "Delete this issue report?"
    bare = adapter._build_detail_actions(
        {
            "delete_url": "/_dazzle/issuereport/c3000000-0000-4000-8000-000000000001",
            "entity_name": "IssueReport",
        }
    )
    assert getattr(bare[0], "hx_confirm", None) == "Delete this issue report?"


def test_leftover_zzz_invents_no_entity() -> None:
    spec = load_project(FIELDTEST)
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_confirm_noun("zzz", labels) == "zzz"
    assert clerk_entity_confirm_noun("ghost", labels) == "ghost"
    html = _issue_row_html(entity_name="zzz")
    assert 'hx-confirm="Delete this zzz?"' in html
    assert "issue report" not in html.lower()
    adapter = FragmentSurfaceAdapter()
    actions = adapter._build_detail_actions(
        {"delete_url": "/x", "entity_name": "zzz", "entity_title": "Issue Report"}
    )
    # Leftover name wins; catalog must not invent Issue Report.
    assert getattr(actions[0], "hx_confirm", None) == "Delete this zzz?"
