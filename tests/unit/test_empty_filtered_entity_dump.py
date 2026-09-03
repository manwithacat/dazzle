"""Filtered list empty must not invent collection-empty theater (oral #215)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dazzle.core.project import load_project
from dazzle.http.runtime.htmx_render import _render_table_empty
from dazzle.render.breadcrumbs import (
    clerk_empty_filtered_title,
    clerk_entity_confirm_noun,
    clerk_entity_noun,
    clerk_list_empty_kind,
    entity_path_labels_from_spec,
)

FIELDTEST = Path("examples/fieldtest_hub")


class _Url:
    path = "/app/issuereport"


def _request() -> SimpleNamespace:
    return SimpleNamespace(url=_Url())


def _table(**overrides: object) -> dict:
    base: dict = {
        "entity_name": "IssueReport",
        "entity_title": "Issue Report",
        "columns": [{"key": "title", "label": "Title"}],
        "api_endpoint": "/api/issuereports",
        "table_id": "dt-issuereport",
        "empty_kind": "filtered",
        "filter_values": {"status": "done"},
        "create_url": "/app/issuereport/create",
        "empty_message": "No items found.",
    }
    base.update(overrides)
    return base


def test_clerk_empty_filtered_title_splits_pascal_and_catalog() -> None:
    spec = load_project(FIELDTEST)
    issue = next(e for e in spec.domain.entities if e.name == "IssueReport")
    assert issue.title == "Issue Report"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_noun("IssueReport", labels) == "Issue Report"
    assert clerk_entity_confirm_noun("IssueReport", labels) == "issue report"
    assert (
        clerk_empty_filtered_title("IssueReport", labels)
        == "No issue reports match the current filters."
    )
    assert (
        clerk_empty_filtered_title("IssueReport") == "No issue reports match the current filters."
    )


def test_clerk_empty_filtered_title_leftover_invents_no_collection() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_empty_filtered_title(junk) == "No items match the current filters."


def test_clerk_list_empty_kind_filters_or_search_are_filtered() -> None:
    assert clerk_list_empty_kind(filters={"status": "done"}) == "filtered"
    assert clerk_list_empty_kind(search="critical") == "filtered"
    assert clerk_list_empty_kind(filters={}, search="  ") == "collection"
    assert clerk_list_empty_kind() == "collection"


def test_htmx_filtered_empty_is_issue_reports_not_collection_theater() -> None:
    html = _render_table_empty(_table(), _request())
    assert "No issue reports match the current filters." in html
    assert 'data-dz-empty-kind="filtered"' in html
    assert "Clear filters" in html
    assert "Add one" not in html
    assert "No items found" not in html
    assert "No issuereport match the current filters." not in html
    assert "No issuereports found" not in html


def test_htmx_filtered_empty_bare_pascal_still_splits() -> None:
    html = _render_table_empty(_table(entity_title=""), _request())
    assert "No issue reports match the current filters." in html
    assert "No issuereport match the current filters." not in html


def test_htmx_filtered_empty_leftover_invents_no_collection() -> None:
    html = _render_table_empty(
        _table(entity_name="zzz", entity_title="", filter_values={"status": "zzz"}),
        _request(),
    )
    assert "No items match the current filters." in html
    assert "Add one" not in html
    assert "No zzz" not in html
