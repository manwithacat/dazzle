"""Kanban lane empty must not dump generic 'No items' (oral #223)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.render.breadcrumbs import (
    clerk_empty_kanban_lane,
    clerk_entity_confirm_noun,
    clerk_entity_noun,
    entity_path_labels_from_spec,
)
from dazzle.render.fragment import FragmentRenderer
from dazzle.render.fragment.region._builders_cards import _BuildersCardsMixin

SIMPLE = Path("examples/simple_task")
FIELDTEST = Path("examples/fieldtest_hub")
SIMPLE_DSL = SIMPLE / "dsl" / "app.dsl"


class _A(_BuildersCardsMixin):
    pass


def _region(**overrides: object) -> object:
    base: dict[str, object] = {
        "name": "tasks",
        "title": "Tasks",
        "empty_message": None,
        "source": "Task",
    }
    base.update(overrides)
    return type("R", (), base)()


def _render_kanban(region: object, ctx: dict[str, object] | None = None) -> str:
    payload: dict[str, object] = {
        "items": [{"id": "1", "title": "Ship login", "status": "todo"}],
        "kanban_columns": ["todo", "in_progress", "review", "done"],
        "group_by": "status",
        "display_key": "title",
    }
    if ctx:
        payload.update(ctx)
    return FragmentRenderer().render(_A()._build_kanban(region, payload))


def test_simple_task_board_kanban_is_live() -> None:
    block = SIMPLE_DSL.read_text()
    region = block.split("  tasks:", 1)[1].split("  by_assignee:", 1)[0]
    assert "display: kanban" in region
    assert "source: Task" in region
    assert "group_by: status" in region


def test_clerk_empty_kanban_lane_splits_pascal_and_catalog() -> None:
    spec = load_project(SIMPLE)
    task = next(e for e in spec.domain.entities if e.name == "Task")
    assert task.title == "Task"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_noun("Task", labels) == "Task"
    assert clerk_entity_confirm_noun("Task", labels) == "task"
    assert clerk_empty_kanban_lane("Task", labels) == "No tasks"
    assert clerk_empty_kanban_lane("Task") == "No tasks"


def test_clerk_empty_kanban_lane_leftover_invents_no_collection() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_empty_kanban_lane(junk) == "No items"


def test_fieldtest_issue_report_lane_is_issue_reports() -> None:
    spec = load_project(FIELDTEST)
    issue = next(e for e in spec.domain.entities if e.name == "IssueReport")
    assert issue.title == "Issue Report"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_empty_kanban_lane("IssueReport", labels) == "No issue reports"


def test_kanban_empty_lane_is_tasks_not_no_items() -> None:
    html = _render_kanban(_region())
    assert "dz-kanban-empty" in html
    assert "No tasks" in html
    assert ">No items<" not in html
    assert "No taskss" not in html
    assert "Ship login" in html


def test_kanban_empty_lane_ctx_source_entity_still_splits() -> None:
    html = _render_kanban(_region(source=""), {"source_entity": "Task"})
    assert "No tasks" in html
    assert ">No items<" not in html


def test_kanban_empty_lane_missing_entity_stays_no_items() -> None:
    html = _render_kanban(_region(source=""))
    assert ">No items<" in html
    assert "No tasks" not in html


def test_kanban_empty_lane_leftover_invents_no_collection() -> None:
    html = _render_kanban(_region(source="zzz"))
    assert ">No items<" in html
    assert "No zzz" not in html


def test_kanban_empty_lane_card_title_item_fallback_does_not_invent() -> None:
    html = _render_kanban(_region(source="Task"), {"entity_name": "Item"})
    assert "No tasks" in html
    assert ">No items<" not in html
