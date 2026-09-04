"""Detail back must not dump generic ← Back (oral #237)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.ir.surfaces import SurfaceMode
from dazzle.core.project import load_project
from dazzle.http.runtime.page_routes import _build_dispatch_ctx
from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
from dazzle.render.breadcrumbs import (
    clerk_back_label,
    clerk_delete_label,
    clerk_entity_noun,
    clerk_related_create_noun,
    entity_path_labels_from_spec,
)
from dazzle.render.context import DetailContext, FieldContext
from dazzle.render.fragment import FragmentRenderer

SIMPLE = Path("examples/simple_task")
FIELDTEST = Path("examples/fieldtest_hub")
SIMPLE_DSL = SIMPLE / "dsl" / "app.dsl"


class _Surface:
    name = "task_detail"
    title = "Task Detail"
    mode = SurfaceMode.VIEW
    related_groups: list = []


class _RC:
    def __init__(self, detail: DetailContext) -> None:
        self.detail = detail
        self.form = None
        self.table = None


def _detail(**overrides: object) -> DetailContext:
    base: dict[str, object] = {
        "entity_name": "Task",
        "title": "Task Detail",
        "fields": [FieldContext(name="title", label="Title")],
        "item": {"id": "abc", "title": "Buy ingredients"},
        "back_url": "/app/task",
        "delete_url": "/_dazzle/tasks/abc",
    }
    base.update(overrides)
    return DetailContext(**base)  # type: ignore[arg-type]


def _html(detail: DetailContext) -> str:
    ctx = _build_dispatch_ctx(_RC(detail), _Surface())
    return FragmentRenderer().render(FragmentSurfaceAdapter()._build_view(_Surface(), ctx))


def test_simple_task_task_detail_is_live() -> None:
    block = SIMPLE_DSL.read_text()
    listing = block.split('surface task_list "Tasks":', 1)[1].split("surface ", 1)[0]
    detail = block.split('surface task_detail "Task Detail":', 1)[1].split("surface ", 1)[0]
    assert "uses entity Task" in listing
    assert "mode: list" in listing
    assert "uses entity Task" in detail
    assert "mode: view" in detail
    spec = load_project(SIMPLE)
    task = next(e for e in spec.domain.entities if e.name == "Task")
    assert task.title == "Task"


def test_clerk_back_label_uses_entity_noun() -> None:
    assert clerk_back_label("Task") == "← Back to Tasks"
    assert clerk_delete_label("Task") == "Delete Task"
    spec = load_project(FIELDTEST)
    issue = next(e for e in spec.domain.entities if e.name == "IssueReport")
    assert issue.title == "Issue Report"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_noun("IssueReport", labels) == "Issue Report"
    assert clerk_related_create_noun("IssueReport", labels) == "Issue Report"
    assert clerk_back_label("IssueReport", labels) == "← Back to Issue Reports"
    assert clerk_back_label("IssueReport") == "← Back to Issue Reports"


def test_clerk_back_label_leftover_invents_no_entity() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_back_label(junk) == "← Back"
        assert clerk_back_label(junk, {"zzz": "Issue Report"}) == "← Back"
    assert clerk_back_label("") == "← Back"
    assert clerk_back_label("record") == "← Back"
    assert clerk_back_label("item") == "← Back"


def test_dispatch_back_is_back_to_tasks_not_back() -> None:
    html = _html(_detail())
    assert ">← Back to Tasks</a>" in html
    leftover = _html(_detail(entity_name="zzz", title="zzz Detail"))
    assert ">← Back</a>" in leftover
    assert "Back to zzz" not in leftover
    assert "← Back to Tasks" not in leftover


def test_dispatch_back_issue_report_is_not_schema_dump() -> None:
    html = _html(
        _detail(
            entity_name="IssueReport",
            title="Issue Report Detail",
            back_url="/app/issue-report",
        )
    )
    assert ">← Back to Issue Reports</a>" in html
    assert ">← Back</a>" not in html
    assert "Back to IssueReport" not in html
    assert "Back to issuereport" not in html
