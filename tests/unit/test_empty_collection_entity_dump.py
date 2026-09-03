"""Empty lists must not dump issuereports for Issue Report (oral #213)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.core.project import load_project
from dazzle.core.strings import entity_slug
from dazzle.http.runtime.page_routes import _build_dispatch_ctx
from dazzle.http.runtime.renderers.fragment_adapter import (
    FragmentSurfaceAdapter,
    _pick_empty_state,
)
from dazzle.render.breadcrumbs import (
    clerk_empty_collection_title,
    clerk_entity_confirm_noun,
    clerk_entity_noun,
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


def _table(**overrides) -> TableContext:
    base: dict = {
        "entity_name": "IssueReport",
        "entity_title": "Issue Report",
        "title": "Issue Board",
        "columns": [ColumnContext(key="title", label="Title")],
        "api_endpoint": "/api/issuereports",
        "rows": [],
        "total": 0,
        "empty_message": "",
    }
    base.update(overrides)
    return TableContext(**base)


def _render_list(ctx: dict) -> str:
    adapter = FragmentSurfaceAdapter()
    return FragmentRenderer().render(adapter._build_list(_Surface(), ctx))


def test_fieldtest_issue_report_empty_title_is_live() -> None:
    spec = load_project(FIELDTEST)
    issue = next(e for e in spec.domain.entities if e.name == "IssueReport")
    assert issue.title == "Issue Report"
    assert entity_slug("IssueReport") == "issuereport"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_noun("IssueReport", labels) == "Issue Report"
    assert clerk_entity_confirm_noun("IssueReport", labels) == "issue report"
    assert clerk_empty_collection_title("IssueReport", labels) == "No issue reports found"
    assert clerk_empty_collection_title("IssueReport") == "No issue reports found"


def test_contact_engagement_letter_empty_title_is_live() -> None:
    spec = load_project(CONTACT)
    letter = next(e for e in spec.domain.entities if e.name == "EngagementLetter")
    assert letter.title == "Engagement Letter"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_empty_collection_title("EngagementLetter", labels) == "No engagement letters found"


def test_pick_empty_state_splits_pascal_entity() -> None:
    title, _ = _pick_empty_state({"empty_kind": "collection", "entity_name": "IssueReport"})
    assert title == "No issue reports found"
    titled, _ = _pick_empty_state(
        {
            "empty_kind": "collection",
            "entity_name": "IssueReport",
            "entity_title": "Issue Report",
        }
    )
    assert titled == "No issue reports found"


def test_pick_empty_state_leftover_invents_no_collection() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        title, _ = _pick_empty_state({"empty_kind": "collection", "entity_name": junk})
        assert title == "No items yet", junk
        assert clerk_empty_collection_title(junk) == "No items yet"


def test_list_renders_issue_report_not_issuereports() -> None:
    ctx = _build_dispatch_ctx(_RC(_table()), object())
    assert ctx["entity_name"] == "IssueReport"
    html = _render_list(ctx)
    assert "No issue reports found" in html
    assert "No issuereports found" not in html
    assert "No Issuereports found" not in html


def test_list_bare_pascal_name_still_splits() -> None:
    ctx = _build_dispatch_ctx(_RC(_table(entity_title="")), object())
    html = _render_list(ctx)
    assert "No issue reports found" in html
    assert "No issuereports found" not in html
