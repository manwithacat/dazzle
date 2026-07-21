"""FTS search_box HTML labels (cycle 1280 — no UUID titles for Contact rows)."""

from __future__ import annotations

from dazzle.http.runtime.fts_routes import _render_results_html


def test_contact_row_label_uses_first_last_name() -> None:
    result = {
        "items": [
            {
                "id": "e118226d-f34d-49aa-a217-50be0e2dcc33",
                "first_name": "Suzanne",
                "last_name": "Adams",
                "email": "suzanne.7916@example.test",
            }
        ],
        "total": 1,
        "snippet_fields": [],
    }
    resp = _render_results_html("Contact", "Adams", result)
    body = resp.body.decode()
    assert "Suzanne Adams" in body
    assert "e118226d-f34d-49aa-a217-50be0e2dcc33" not in body.split("result-title")[1][:80]


def test_falls_back_to_email_when_no_name() -> None:
    result = {
        "items": [{"id": "x", "email": "solo@example.test"}],
        "total": 1,
    }
    body = _render_results_html("Contact", "solo", result).body.decode()
    assert "solo@example.test" in body


def test_empty_query_shows_no_results() -> None:
    body = _render_results_html("Contact", "zzz", {"items": [], "total": 0}).body.decode()
    assert "No results" in body
    assert "zzz" in body
