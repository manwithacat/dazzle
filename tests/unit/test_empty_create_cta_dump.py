"""Empty-list create CTA must not dump generic Add one (oral #233)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.runtime.htmx_render import _render_table_empty
from dazzle.render.breadcrumbs import (
    clerk_empty_create_cta,
    clerk_entity_noun,
    clerk_related_create_noun,
    entity_path_labels_from_spec,
)

SIMPLE = Path("examples/simple_task")
FIELDTEST = Path("examples/fieldtest_hub")
SIMPLE_DSL = SIMPLE / "dsl" / "app.dsl"


def _table(**overrides: object) -> dict:
    base: dict = {
        "entity_name": "Task",
        "entity_title": "Task",
        "columns": [{"key": "title", "label": "Title"}],
        "api_endpoint": "/api/tasks",
        "table_id": "dt-task_list",
        "empty_kind": "collection",
        "create_url": "/app/task/create",
        "empty_message": "No tasks yet. Create your first task!",
    }
    base.update(overrides)
    return base


def test_simple_task_task_list_create_is_live() -> None:
    block = SIMPLE_DSL.read_text()
    listing = block.split('surface task_list "Tasks":', 1)[1].split("surface ", 1)[0]
    create = block.split('surface task_create "Create Task":', 1)[1].split("surface ", 1)[0]
    assert "uses entity Task" in listing
    assert "mode: list" in listing
    assert "mode: create" in create
    spec = load_project(SIMPLE)
    task = next(e for e in spec.domain.entities if e.name == "Task")
    assert task.title == "Task"


def test_clerk_empty_create_cta_uses_entity_noun() -> None:
    assert clerk_empty_create_cta("Task") == "New Task"
    assert clerk_empty_create_cta("Task", {"Task": "Task"}) == "New Task"
    spec = load_project(FIELDTEST)
    issue = next(e for e in spec.domain.entities if e.name == "IssueReport")
    assert issue.title == "Issue Report"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_noun("IssueReport", labels) == "Issue Report"
    assert clerk_related_create_noun("IssueReport", labels) == "Issue Report"
    assert clerk_empty_create_cta("IssueReport", labels) == "New Issue Report"
    assert clerk_empty_create_cta("IssueReport") == "New Issue Report"


def test_clerk_empty_create_cta_leftover_invents_no_entity() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_empty_create_cta(junk) == "Add one"
    assert clerk_empty_create_cta("") == "Add one"


def test_htmx_empty_create_cta_is_new_task_not_add_one() -> None:
    html = _render_table_empty(_table(), None)
    assert 'class="dz-tr-empty-link">New Task</a>' in html
    assert ">Add one</a>" not in html
    leftover = _render_table_empty(
        _table(entity_name="zzz", entity_title="", create_url="/app/zzz/create"),
        None,
    )
    assert 'class="dz-tr-empty-link">Add one</a>' in leftover
    assert "New zzz" not in leftover


def test_htmx_empty_create_cta_issue_report_is_not_schema_dump() -> None:
    html = _render_table_empty(
        _table(
            entity_name="IssueReport",
            entity_title="Issue Report",
            create_url="/app/issuereport/create",
            empty_message="No items found.",
        ),
        None,
    )
    assert 'class="dz-tr-empty-link">New Issue Report</a>' in html
    assert ">Add one</a>" not in html
    assert "New IssueReport" not in html
    assert "New issuereport" not in html


def test_htmx_empty_without_create_url_has_no_cta() -> None:
    html = _render_table_empty(_table(create_url=""), None)
    assert "dz-tr-empty-link" not in html
    assert "Add one" not in html
    assert "New Task" not in html
