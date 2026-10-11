"""FTS search empty must not dump generic 'No results' for Contact (oral #221)."""

from __future__ import annotations

from dazzle.http.runtime.fts_routes import _render_results_html
from dazzle.render.breadcrumbs import (
    clerk_empty_search_title,
    clerk_search_results_label,
)


def test_clerk_empty_search_title_leftover_invents_no_collection() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_empty_search_title(junk) == "No results"
        assert clerk_search_results_label(junk, total=2) == "results"
        assert clerk_search_results_label(junk, total=1) == "result"


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
