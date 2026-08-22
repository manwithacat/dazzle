"""display: kanban + group_by FK must not dump an empty people board (oral #169)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.runtime.workspace_region_computes import compute_kanban_columns
from dazzle.render.display_names import compute_kanban_item_columns
from dazzle.render.fragment.region import WorkspaceRegionAdapter
from dazzle.render.fragment.renderer import FragmentRenderer


class _FakeKanban:
    name = "by_assignee"
    title = "By assignee"
    display = "kanban"
    empty_message = "No assigned open tasks"


def _simple_task_by_assignee():
    spec = load_project(Path("examples/simple_task"))
    for ws in spec.workspaces:
        for region in ws.regions:
            if region.name == "by_assignee":
                return spec, region
    raise AssertionError("simple_task by_assignee missing")


def test_simple_task_by_assignee_is_kanban_assigned_to() -> None:
    spec, region = _simple_task_by_assignee()
    assert str(getattr(region.display, "value", region.display)) == "kanban"
    assert region.group_by == "assigned_to"
    task = spec.get_entity("Task")
    assert task is not None
    assert compute_kanban_columns(task, "assigned_to") == []


def test_fk_group_by_columns_use_display_names() -> None:
    ada = "a1000000-0000-4000-8000-000000000001"
    sam = "a1000000-0000-4000-8000-000000000002"
    items = [
        {
            "id": "t1",
            "title": "Ship login",
            "assigned_to": {"id": ada, "name": "Ada Lovelace"},
            "assigned_to_display": "Ada Lovelace",
        },
        {
            "id": "t2",
            "title": "Review search",
            "assigned_to": {"id": ada, "name": "Ada Lovelace"},
            "assigned_to_display": "Ada Lovelace",
        },
        {
            "id": "t3",
            "title": "Fix pagination",
            "assigned_to": sam,
            "assigned_to_display": "Sam Member",
        },
        {
            "id": "t99",
            "title": "Leftover task",
            "assigned_to": "zzz",
        },
    ]
    cols = compute_kanban_item_columns(items, "assigned_to")
    keys = [k for k, _lab in cols]
    labels = [lab for _k, lab in cols]
    assert keys == [ada, sam, "zzz"]
    assert labels == ["Ada Lovelace", "Sam Member", "zzz"]


def test_empty_items_do_not_invent_leftover_columns() -> None:
    assert compute_kanban_item_columns([], "assigned_to") == []
    assert compute_kanban_item_columns([{"id": "t1", "title": "Orphan"}], "assigned_to") == []


def test_kanban_html_renders_people_columns_not_empty() -> None:
    ada = "a1000000-0000-4000-8000-000000000001"
    items = [
        {
            "id": "t1",
            "title": "Ship login",
            "assigned_to": {"id": ada, "name": "Ada Lovelace"},
            "assigned_to_display": "Ada Lovelace",
        },
        {"id": "t99", "title": "Leftover task", "assigned_to": "zzz"},
    ]
    html = FragmentRenderer().render(
        WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
            _FakeKanban(),
            {
                "items": items,
                "group_by": "assigned_to",
                "display_key": "title",
                "empty_message": "No assigned open tasks",
            },
        )
    )
    assert "dz-kanban" in html
    assert "Ada Lovelace" in html
    assert "Ship login" in html
    assert "zzz" in html.lower()
    assert "Leftover task" in html
    assert ada not in html
    assert "No assigned open tasks" not in html
    assert "No items found." not in html


def test_declared_enum_columns_still_drop_unknown_keys() -> None:
    html = FragmentRenderer().render(
        WorkspaceRegionAdapter().build(  # type: ignore[arg-type]
            _FakeKanban(),
            {
                "items": [
                    {"id": "1", "title": "X", "status": "blocked"},
                    {"id": "2", "title": "Y", "status": "todo"},
                ],
                "kanban_columns": ["todo", "doing"],
                "group_by": "status",
                "display_key": "title",
                "empty_message": "No assigned open tasks",
            },
        )
    )
    assert "Y" in html
    assert "X" not in html
    assert "blocked" not in html
    assert "todo" in html or "Todo" in html
