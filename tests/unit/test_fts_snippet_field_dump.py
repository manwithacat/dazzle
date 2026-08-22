"""FTS search_box must not dump schema keys as snippet labels (oral #180)."""

from __future__ import annotations

from pathlib import Path

from dazzle.http.runtime.fts_routes import _render_results_html
from dazzle.render.filters import clerk_fts_snippet_field_label


def test_contact_manager_search_box_is_live() -> None:
    block = Path("examples/contact_manager/dsl/app.dsl").read_text()
    assert "search on Contact:" in block
    search = block.split("search on Contact:", 1)[1].split("\n\n", 1)[0]
    assert "first_name" in search
    assert "last_name" in search
    assert "email" in search
    assert "company" in search
    assert "display: search_box" in block
    home = block.split('workspace home "Home":', 1)[1].split("workspace ", 1)[0]
    assert "display: search_box" in home


def test_clerk_fts_snippet_split_leftover_and_empty() -> None:
    assert clerk_fts_snippet_field_label("first_name") == "First Name"
    assert clerk_fts_snippet_field_label("job_title") == "Job Title"
    assert clerk_fts_snippet_field_label("zzz") == "zzz"
    assert clerk_fts_snippet_field_label("ghost") == "ghost"
    assert clerk_fts_snippet_field_label("") == ""
    assert clerk_fts_snippet_field_label(None) == ""


def test_snippet_field_label_is_clerk_not_schema_key() -> None:
    result = {
        "items": [
            {
                "id": "c1",
                "first_name": "Ada",
                "last_name": "Lovelace",
                "first_name__snippet": "Ada",
                "last_name__snippet": "Lovelace",
                "job_title__snippet": "Analyst",
            }
        ],
        "total": 1,
        "snippet_fields": ["first_name", "last_name", "job_title"],
    }
    body = _render_results_html("Contact", "Ada", result).body.decode()
    assert "First Name:" in body
    assert "Last Name:" in body
    assert "Job Title:" in body
    assert "first_name:" not in body
    assert "last_name:" not in body
    assert "job_title:" not in body
    assert "Ada" in body
    leftover = _render_results_html(
        "Contact",
        "zzz",
        {
            "items": [{"id": "c2", "zzz__snippet": "Ada", "ghost__snippet": "Lovelace"}],
            "total": 1,
            "snippet_fields": ["zzz", "ghost"],
        },
    ).body.decode()
    assert "zzz:" in leftover
    assert "ghost:" in leftover
    assert "Zzz:" not in leftover
    assert "Ghost:" not in leftover


def test_empty_invents_no_snippets() -> None:
    body = _render_results_html("Contact", "Ada", {"items": [], "total": 0}).body.decode()
    assert "dz-search-box-result-snippet-field" not in body
    assert "First Name:" not in body
    body2 = _render_results_html(
        "Contact",
        "Ada",
        {"items": [{"id": "c1", "first_name": "Ada"}], "total": 1, "snippet_fields": []},
    ).body.decode()
    assert "dz-search-box-result-snippet-field" not in body2
    assert "first_name:" not in body2
