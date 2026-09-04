"""Form submit must not dump generic Create/Save (oral #234)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dazzle.core import ir
from dazzle.core.project import load_project
from dazzle.http.runtime.page_routes import _build_dispatch_ctx
from dazzle.http.runtime.renderers.fragment_adapter import FragmentSurfaceAdapter
from dazzle.render.breadcrumbs import (
    clerk_entity_noun,
    clerk_form_submit_label,
    clerk_related_create_noun,
    entity_path_labels_from_spec,
)
from dazzle.render.context import FieldContext, FormContext
from dazzle.render.fragment import FragmentRenderer

SIMPLE = Path("examples/simple_task")
FIELDTEST = Path("examples/fieldtest_hub")
SIMPLE_DSL = SIMPLE / "dsl" / "app.dsl"


def _form(**overrides: object) -> FormContext:
    base: dict[str, object] = {
        "entity_name": "Task",
        "title": "Create Task",
        "fields": [FieldContext(name="title", label="Title", field_type="string")],
        "action_url": "/api/tasks",
        "method": "post",
        "mode": "create",
    }
    base.update(overrides)
    return FormContext(**base)  # type: ignore[arg-type]


def _surface(*, edit: bool = False) -> ir.SurfaceSpec:
    if edit:
        return ir.SurfaceSpec(
            name="task_edit",
            title="Edit Task",
            entity_ref="Task",
            mode=ir.SurfaceMode.EDIT,
        )
    return ir.SurfaceSpec(
        name="task_create",
        title="Create Task",
        entity_ref="Task",
        mode=ir.SurfaceMode.CREATE,
    )


def _html(form: FormContext, surface: ir.SurfaceSpec, catalog: dict[str, str] | None = None) -> str:
    render_ctx = SimpleNamespace(
        form=form,
        table=None,
        detail=None,
        entity_path_labels=catalog or {},
    )
    ctx = _build_dispatch_ctx(render_ctx, surface, services=None)
    return FragmentRenderer().render(
        FragmentSurfaceAdapter()._build_form(surface, ctx, mode=surface.mode)
    )


def test_simple_task_task_create_is_live() -> None:
    block = SIMPLE_DSL.read_text()
    listing = block.split('surface task_list "Tasks":', 1)[1].split("surface ", 1)[0]
    create = block.split('surface task_create "Create Task":', 1)[1].split("surface ", 1)[0]
    assert "uses entity Task" in listing
    assert "mode: list" in listing
    assert "mode: create" in create
    spec = load_project(SIMPLE)
    task = next(e for e in spec.domain.entities if e.name == "Task")
    assert task.title == "Task"


def test_clerk_form_submit_label_uses_entity_noun() -> None:
    assert clerk_form_submit_label("Task") == "Create Task"
    assert clerk_form_submit_label("Task", edit=True) == "Save Task"
    spec = load_project(FIELDTEST)
    issue = next(e for e in spec.domain.entities if e.name == "IssueReport")
    assert issue.title == "Issue Report"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_noun("IssueReport", labels) == "Issue Report"
    assert clerk_related_create_noun("IssueReport", labels) == "Issue Report"
    assert clerk_form_submit_label("IssueReport", labels) == "Create Issue Report"
    assert clerk_form_submit_label("IssueReport") == "Create Issue Report"
    assert clerk_form_submit_label("IssueReport", labels, edit=True) == "Save Issue Report"


def test_clerk_form_submit_label_leftover_invents_no_entity() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_form_submit_label(junk) == "Create"
        assert clerk_form_submit_label(junk, edit=True) == "Save"
    assert clerk_form_submit_label("") == "Create"
    assert clerk_form_submit_label("", edit=True) == "Save"


def test_dispatch_form_submit_is_create_task_not_create() -> None:
    html = _html(_form(), _surface())
    assert ">Create Task</button>" in html
    assert 'type="submit"' in html
    leftover = _html(_form(entity_name="zzz", title="Create zzz"), _surface())
    assert ">Create</button>" in leftover
    assert "Create zzz" not in leftover


def test_dispatch_form_submit_issue_report_is_not_schema_dump() -> None:
    html = _html(
        _form(entity_name="IssueReport", title="Create Issue Report"),
        ir.SurfaceSpec(
            name="issue_report_create",
            title="Create Issue Report",
            entity_ref="IssueReport",
            mode=ir.SurfaceMode.CREATE,
        ),
        catalog={"IssueReport": "Issue Report"},
    )
    assert ">Create Issue Report</button>" in html
    assert ">Create</button>" not in html
    assert "Create IssueReport" not in html
    assert "Create issuereport" not in html


def test_dispatch_edit_form_submit_is_save_task() -> None:
    html = _html(_form(mode="edit", title="Edit Task"), _surface(edit=True))
    assert ">Save Task</button>" in html
    leftover = _html(
        _form(entity_name="zzz", title="Edit zzz", mode="edit"),
        _surface(edit=True),
    )
    assert ">Save</button>" in leftover
    assert "Save zzz" not in leftover
