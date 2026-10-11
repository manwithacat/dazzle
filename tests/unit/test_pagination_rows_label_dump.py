"""Pagination footer must not dump generic 'rows' for Issue Report (oral #216)."""

from __future__ import annotations

from dazzle.http.runtime.htmx_render import _render_table_pagination
from dazzle.render.breadcrumbs import (
    clerk_pagination_rows_label,
)
from dazzle.render.fragment import URL, FragmentRenderer, Pagination


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


def test_clerk_pagination_rows_label_leftover_invents_no_collection() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_pagination_rows_label(junk, total=42) == "rows"
        assert clerk_pagination_rows_label(junk, total=1) == "row"


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
