"""Cycle 1824 — FTS search_box result open-discovery stamps.

Agents attr-read ``display: search_box`` destinations without scraping
titles. Empty result panels stay unstamped; non-app paths skip suffix.
"""

from __future__ import annotations

from dazzle.http.runtime.fts_routes import _render_results_html
from dazzle.render.open_discovery import open_hop_label, search_open_attr_suffix


def test_search_open_attr_suffix_stamps_app_detail() -> None:
    s = search_open_attr_suffix("/app/contact/c-1")
    assert "data-dz-search-drill" in s
    assert 'data-dz-open-entity="Contact"' in s
    assert "Open Contact" in s
    assert 'data-dz-open-chain="/app/contact/c-1"' in s
    assert open_hop_label("Contact") == "Open Contact"


def test_search_open_attr_suffix_skips_home_and_non_app() -> None:
    assert search_open_attr_suffix("/app") == ""
    assert search_open_attr_suffix("/") == ""
    assert search_open_attr_suffix("/pricing") == ""
    assert search_open_attr_suffix("#results") == ""
    assert search_open_attr_suffix("") == ""


def test_render_results_html_stamps_open_discovery() -> None:
    result = {
        "items": [
            {
                "id": "e118226d-f34d-49aa-a217-50be0e2dcc33",
                "first_name": "Suzanne",
                "last_name": "Adams",
            }
        ],
        "total": 1,
        "snippet_fields": [],
    }
    body = _render_results_html("Contact", "Adams", result).body.decode()
    assert "data-dz-search-drill" in body
    assert 'data-dz-open-entity="Contact"' in body
    assert "Open Contact" in body
    assert 'href="/app/contact/e118226d-f34d-49aa-a217-50be0e2dcc33"' in body
    assert "data-dz-open-chain=" in body
    assert "Suzanne Adams" in body


def test_render_results_html_empty_unstamped() -> None:
    body = _render_results_html("Contact", "zzz", {"items": [], "total": 0}).body.decode()
    assert "No results" in body
    assert "data-dz-search-drill" not in body
    assert "data-dz-open-" not in body
