"""FTS search empty must not dump generic 'No results' for Contact (oral #221)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.runtime.fts_routes import _render_results_html
from dazzle.render.breadcrumbs import (
    clerk_empty_search_title,
    clerk_entity_confirm_noun,
    clerk_entity_noun,
    clerk_search_results_label,
    entity_path_labels_from_spec,
)

CONTACT = Path("examples/contact_manager")
FIELDTEST = Path("examples/fieldtest_hub")
CONTACT_DSL = CONTACT / "dsl" / "app.dsl"


def test_contact_manager_search_box_is_live() -> None:
    block = CONTACT_DSL.read_text()
    assert "search on Contact:" in block
    home = block.split('workspace home "Home":', 1)[1].split("workspace ", 1)[0]
    assert "display: search_box" in home
    assert "source: Contact" in home


def test_clerk_empty_search_title_splits_pascal_and_catalog() -> None:
    spec = load_project(CONTACT)
    contact = next(e for e in spec.domain.entities if e.name == "Contact")
    assert contact.title == "Contact"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_noun("Contact", labels) == "Contact"
    assert clerk_entity_confirm_noun("Contact", labels) == "contact"
    assert clerk_empty_search_title("Contact", labels) == "No contacts match"
    assert clerk_empty_search_title("Contact") == "No contacts match"
    assert clerk_search_results_label("Contact", labels, total=1) == "contact"
    assert clerk_search_results_label("Contact", labels, total=2) == "contacts"


def test_clerk_empty_search_title_leftover_invents_no_collection() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_empty_search_title(junk) == "No results"
        assert clerk_search_results_label(junk, total=2) == "results"
        assert clerk_search_results_label(junk, total=1) == "result"


def test_fieldtest_issue_report_search_noun_is_live() -> None:
    spec = load_project(FIELDTEST)
    issue = next(e for e in spec.domain.entities if e.name == "IssueReport")
    assert issue.title == "Issue Report"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_empty_search_title("IssueReport", labels) == "No issue reports match"
    assert clerk_search_results_label("IssueReport", labels, total=42) == "issue reports"


def test_fts_empty_is_contacts_not_no_results() -> None:
    body = _render_results_html("Contact", "zzz", {"items": [], "total": 0}).body.decode()
    assert "No contacts match" in body
    assert "<em>zzz</em>" in body
    assert "No results" not in body
    assert "No contactss" not in body


def test_fts_count_is_contacts_not_results() -> None:
    result = {
        "items": [{"id": "c1", "first_name": "Ada", "last_name": "Lovelace"}],
        "total": 1,
        "snippet_fields": [],
    }
    body = _render_results_html("Contact", "Ada", result).body.decode()
    assert ">1 contact<" in body or ">1 contact</div>" in body
    assert "1 result" not in body
    many = {
        "items": [
            {"id": "c1", "first_name": "Ada"},
            {"id": "c2", "first_name": "Alan"},
        ],
        "total": 2,
        "snippet_fields": [],
    }
    html = _render_results_html("Contact", "A", many).body.decode()
    assert "2 contacts" in html
    assert "2 results" not in html


def test_fts_empty_missing_entity_stays_no_results() -> None:
    body = _render_results_html("", "zzz", {"items": [], "total": 0}).body.decode()
    assert "No results" in body
    assert "match" not in body


def test_fts_empty_leftover_invents_no_collection() -> None:
    body = _render_results_html("zzz", "Ada", {"items": [], "total": 0}).body.decode()
    assert "No results" in body
    assert "No zzz" not in body
    assert "match" not in body
    counted = _render_results_html(
        "zzz",
        "Ada",
        {"items": [{"id": "c1", "name": "Ada"}], "total": 2},
    ).body.decode()
    count = counted.split("dz-search-box-result-count", 1)[1].split("</div>", 1)[0]
    assert "2 results" in count
    assert "zzz" not in count
    assert "No zzz" not in counted.split("dz-search-box-result-count", 1)[0]
