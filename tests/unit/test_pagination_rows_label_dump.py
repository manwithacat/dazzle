"""Pagination footer must not dump generic 'rows' for Issue Report (oral #216)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.runtime.htmx_render import _render_table_pagination
from dazzle.render.breadcrumbs import (
    clerk_entity_confirm_noun,
    clerk_entity_noun,
    clerk_pagination_rows_label,
    entity_path_labels_from_spec,
)
from dazzle.render.fragment import URL, FragmentRenderer, Pagination

FIELDTEST = Path("examples/fieldtest_hub")
CONTACT = Path("examples/contact_manager")


def _table(**overrides: object) -> dict:
    base: dict = {
        "entity_name": "IssueReport",
        "entity_title": "Issue Report",
        "total": 42,
        "page_size": 10,
        "page": 2,
        "table_id": "dt-issuereport",
        "api_endpoint": "/api/issuereports",
    }
    base.update(overrides)
    return base


def test_clerk_pagination_rows_label_splits_pascal_and_catalog() -> None:
    spec = load_project(FIELDTEST)
    issue = next(e for e in spec.domain.entities if e.name == "IssueReport")
    assert issue.title == "Issue Report"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_noun("IssueReport", labels) == "Issue Report"
    assert clerk_entity_confirm_noun("IssueReport", labels) == "issue report"
    assert clerk_pagination_rows_label("IssueReport", labels, total=42) == "issue reports"
    assert clerk_pagination_rows_label("IssueReport", total=42) == "issue reports"
    assert clerk_pagination_rows_label("IssueReport", labels, total=1) == "issue report"


def test_clerk_pagination_rows_label_leftover_invents_no_collection() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_pagination_rows_label(junk, total=42) == "rows"
        assert clerk_pagination_rows_label(junk, total=1) == "row"


def test_contact_engagement_letter_pagination_noun_is_live() -> None:
    spec = load_project(CONTACT)
    letter = next(e for e in spec.domain.entities if e.name == "EngagementLetter")
    assert letter.title == "Engagement Letter"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_pagination_rows_label("EngagementLetter", labels, total=42) == "engagement letters"


def test_htmx_pagination_is_issue_reports_not_rows() -> None:
    html = _render_table_pagination(_table())
    assert "42 issue reports" in html
    assert "42 rows" not in html
    assert "42 issuereports" not in html.lower()


def test_htmx_pagination_bare_pascal_name_still_splits() -> None:
    html = _render_table_pagination(_table(entity_title=""))
    assert "42 issue reports" in html
    assert "42 rows" not in html


def test_htmx_pagination_missing_entity_stays_rows() -> None:
    html = _render_table_pagination(_table(entity_name="", entity_title=""))
    assert "42 rows" in html


def test_fragment_pagination_uses_entity_noun() -> None:
    html = FragmentRenderer().render(
        Pagination(
            region_name="issuereport",
            endpoint=URL("/api/issuereports"),
            total=42,
            page=2,
            page_size=10,
            entity_name="IssueReport",
            entity_title="Issue Report",
        )
    )
    assert "42 issue reports" in html
    assert "42 rows" not in html
