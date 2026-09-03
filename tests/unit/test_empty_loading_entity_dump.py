"""List fetch-error empty must not invent collection-empty theater (oral #218)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.core.project import load_project
from dazzle.http.runtime.htmx_render import _render_table_empty
from dazzle.http.runtime.page_routes import _build_dispatch_ctx
from dazzle.http.runtime.renderers.fragment_adapter import (
    FragmentSurfaceAdapter,
    _pick_empty_state,
)
from dazzle.render.breadcrumbs import (
    clerk_empty_loading_title,
    clerk_entity_confirm_noun,
    clerk_entity_noun,
    clerk_list_empty_kind,
    entity_path_labels_from_spec,
)
from dazzle.render.context import ColumnContext, TableContext
from dazzle.render.fragment import FragmentRenderer

FIELDTEST = Path("examples/fieldtest_hub")
CONTACT = Path("examples/contact_manager")


class _Surface:
    name = "issue_report_list"
    title = "Issue Board"
    mode = SurfaceMode.LIST
    entity_ref = "IssueReport"


class _RC:
    def __init__(self, table: TableContext) -> None:
        self.table = table
        self.form = None
        self.detail = None


def _table_ctx(**overrides) -> TableContext:
    base: dict = {
        "entity_name": "IssueReport",
        "entity_title": "Issue Report",
        "title": "Issue Board",
        "columns": [ColumnContext(key="title", label="Title")],
        "api_endpoint": "/api/issuereports",
        "rows": [],
        "total": 0,
        "empty_message": "No items found.",
        "empty_kind": "loading",
        "create_url": "/app/issuereport/create",
        "create_label": "New Issue Report",
    }
    base.update(overrides)
    return TableContext(**base)


def _htmx_table(**overrides: object) -> dict:
    base: dict = {
        "entity_name": "IssueReport",
        "entity_title": "Issue Report",
        "columns": [{"key": "title", "label": "Title"}],
        "api_endpoint": "/api/issuereports",
        "table_id": "dt-issuereport",
        "empty_kind": "loading",
        "create_url": "/app/issuereport/create",
        "empty_message": "No items found.",
    }
    base.update(overrides)
    return base


def _render_list(ctx: dict) -> str:
    adapter = FragmentSurfaceAdapter()
    return FragmentRenderer().render(adapter._build_list(_Surface(), ctx))


def test_clerk_empty_loading_title_splits_pascal_and_catalog() -> None:
    spec = load_project(FIELDTEST)
    issue = next(e for e in spec.domain.entities if e.name == "IssueReport")
    assert issue.title == "Issue Report"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_noun("IssueReport", labels) == "Issue Report"
    assert clerk_entity_confirm_noun("IssueReport", labels) == "issue report"
    assert clerk_empty_loading_title("IssueReport", labels) == "Couldn't load issue reports"
    assert clerk_empty_loading_title("IssueReport") == "Couldn't load issue reports"


def test_clerk_empty_loading_title_leftover_invents_no_collection() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_empty_loading_title(junk) == "Couldn't load items"


def test_contact_engagement_letter_loading_title_is_live() -> None:
    spec = load_project(CONTACT)
    letter = next(e for e in spec.domain.entities if e.name == "EngagementLetter")
    assert letter.title == "Engagement Letter"
    labels = entity_path_labels_from_spec(spec)
    assert (
        clerk_empty_loading_title("EngagementLetter", labels) == "Couldn't load engagement letters"
    )


def test_clerk_list_empty_kind_fetch_error_is_loading() -> None:
    assert clerk_list_empty_kind(fetch_errored=True) == "loading"
    assert clerk_list_empty_kind(filters={"status": "done"}, fetch_errored=True) == "loading"
    assert clerk_list_empty_kind(search="critical", fetch_errored=True) == "loading"
    assert clerk_list_empty_kind(filters={"status": "done"}) == "filtered"
    assert clerk_list_empty_kind() == "collection"


def test_htmx_loading_empty_is_issue_reports_not_schema_dump() -> None:
    html = _render_table_empty(_htmx_table(), None)
    assert "Couldn't load issue reports. Try reloading." in html
    assert 'data-dz-empty-kind="loading"' in html
    assert "Add one" not in html
    assert "Couldn't load issuereport" not in html
    assert "No items found" not in html
    assert "No issue reports found" not in html


def test_htmx_loading_empty_bare_pascal_still_splits() -> None:
    html = _render_table_empty(_htmx_table(entity_title=""), None)
    assert "Couldn't load issue reports. Try reloading." in html
    assert "Couldn't load issuereport" not in html


def test_htmx_loading_empty_leftover_invents_no_collection() -> None:
    html = _render_table_empty(
        _htmx_table(entity_name="zzz", entity_title="", create_url="/app/zzz/create"),
        None,
    )
    assert "Couldn't load items. Try reloading." in html
    assert "Add one" not in html
    assert "No zzz" not in html
    assert "Couldn't load zzz" not in html


def test_pick_empty_state_loading_does_not_invent_collection() -> None:
    title, description = _pick_empty_state(
        {
            "empty_kind": "loading",
            "entity_name": "IssueReport",
            "entity_title": "Issue Report",
            "empty_collection": "Add your first report",
            "empty_message": "No items found.",
        }
    )
    assert title == "Couldn't load issue reports"
    assert description == "Try reloading."
    assert title != "No items yet"
    assert "Add your first" not in description


def test_fragment_loading_empty_is_not_collection_theater() -> None:
    ctx = _build_dispatch_ctx(_RC(_table_ctx()), object())
    html = _render_list(ctx)
    assert "Couldn't load issue reports" in html
    assert "Try reloading." in html
    assert "No items yet" not in html
    assert "couldn't load issuereport" not in html.lower()
