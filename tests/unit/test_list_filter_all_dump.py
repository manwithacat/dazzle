"""List FilterBar All must not dump generic All (oral #232)."""

# Fragment must load before breadcrumbs (renderer ↔ breadcrumbs import cycle).
# ruff: noqa: I001

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.render.fragment import URL, FragmentRenderer
from dazzle.render.fragment.primitives import FilterColumn, ListFilterBar
from dazzle.render.breadcrumbs import clerk_filter_all_label  # noqa: E402

SIMPLE = Path("examples/simple_task")
SIMPLE_DSL = SIMPLE / "dsl" / "app.dsl"


def _render(frag: object) -> str:
    return FragmentRenderer().render(frag)  # type: ignore[arg-type]


def _bar(*columns: FilterColumn) -> ListFilterBar:
    return ListFilterBar(
        tbody_id="task-body",
        endpoint=URL("/api/tasks"),
        columns=columns,
    )


def test_simple_task_task_list_filters_are_live() -> None:
    block = SIMPLE_DSL.read_text()
    surface = block.split('surface task_list "Tasks":', 1)[1].split("surface ", 1)[0]
    assert "filter: status, priority, assigned_to" in surface
    assert 'field status "Status"' in surface
    assert 'field assigned_to "Assigned To"' in surface
    spec = load_project(SIMPLE)
    task = next(e for e in spec.domain.entities if e.name == "Task")
    assert any(f.name == "status" for f in task.fields)
    assert any(f.name == "assigned_to" for f in task.fields)


def test_clerk_filter_all_label_uses_field_noun() -> None:
    assert clerk_filter_all_label("Status") == "All Status"
    assert clerk_filter_all_label("Assigned To") == "All Assigned To"
    assert clerk_filter_all_label("Priority") == "All Priority"


def test_clerk_filter_all_label_leftover_invents_no_field() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_filter_all_label(junk) == "All"
    assert clerk_filter_all_label("") == "All"
    assert clerk_filter_all_label(None) == "All"


def test_list_filter_all_is_status_not_generic_all() -> None:
    html = _render(
        _bar(
            FilterColumn(
                key="status",
                label="Status",
                options=(("todo", "Todo"), ("done", "Done")),
            )
        )
    )
    assert '<option value="">All Status</option>' in html
    assert '<option value="">All</option>' not in html
    leftover = _render(
        _bar(
            FilterColumn(
                key="zzz",
                label="zzz",
                options=(("todo", "Todo"),),
            )
        )
    )
    assert '<option value="">All</option>' in leftover
    assert "All zzz" not in leftover


def test_list_ref_filter_all_is_assigned_to_not_generic_all() -> None:
    html = _render(
        _bar(
            FilterColumn(
                key="assigned_to",
                label="Assigned To",
                options=(),
                filter_type="ref",
                ref_api="/users",
            )
        )
    )
    assert '<option value="">All Assigned To</option>' in html
    assert '<option value="">All</option>' not in html
