"""Related-tab dual-FK labels must not dump schema keys (oral #183)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.page.converters.template_compiler import compile_appspec_to_templates
from dazzle.render.filters import clerk_related_tab_fk_label
from dazzle.render.fragment.primitives.data import RelatedGroup, RelatedTab
from dazzle.render.fragment.renderer import FragmentRenderer

SIMPLE = Path("examples/simple_task")


def test_simple_task_user_detail_dual_fk_is_live() -> None:
    block = (SIMPLE / "dsl" / "app.dsl").read_text()
    task = block.split('entity Task "Task":', 1)[1].split("entity ", 1)[0]
    assert "assigned_to: ref User" in task
    assert "created_by: ref User" in task
    surface = block.split('surface user_detail "Team Member Overview":', 1)[1].split("surface ", 1)[
        0
    ]
    assert "show: Task" in surface
    assert "display: queue" in surface


def test_clerk_related_tab_fk_leftover_and_empty() -> None:
    assert clerk_related_tab_fk_label("assigned_to") == "Assigned To"
    assert clerk_related_tab_fk_label("created_by") == "Created By"
    assert clerk_related_tab_fk_label("billing_company") == "Billing Company"
    assert clerk_related_tab_fk_label("zzz") == "zzz"
    assert clerk_related_tab_fk_label("ghost") == "ghost"
    assert clerk_related_tab_fk_label("") == ""
    assert clerk_related_tab_fk_label(None) == ""


def test_simple_task_user_detail_tabs_are_clerk_not_schema_key() -> None:
    appspec = load_project(SIMPLE)
    contexts = compile_appspec_to_templates(appspec)
    detail = contexts["/user/{id}"].detail
    assert detail is not None
    work = next(g for g in detail.related_groups if g.group_id == "group-work")
    labels = {t.label for t in work.tabs if t.entity_name == "Task"}
    assert labels == {"Task · Assigned To", "Task · Created By"}
    assert "Task · assigned to" not in labels
    assert "Task · created by" not in labels


def test_related_queue_tab_strip_is_clerk_not_schema_key() -> None:
    html = FragmentRenderer().render(
        RelatedGroup(
            group_id="work",
            label="Open work",
            display="queue",
            tabs=(
                RelatedTab(
                    tab_id="tab-task-assigned-to",
                    label="Task · Assigned To",
                    headers=("Title",),
                    rows=(("Ship dual-open",),),
                ),
                RelatedTab(
                    tab_id="tab-task-created-by",
                    label="Task · Created By",
                    headers=("Title",),
                    rows=(("Review notes",),),
                ),
            ),
        )
    )
    assert "Task · Assigned To" in html
    assert "Task · Created By" in html
    assert "assigned to" not in html
    leftover = FragmentRenderer().render(
        RelatedGroup(
            group_id="work",
            label="Open work",
            display="queue",
            tabs=(
                RelatedTab(
                    tab_id="tab-task-zzz",
                    label="Task · zzz",
                    headers=("Title",),
                    rows=(),
                ),
                RelatedTab(
                    tab_id="tab-task-ghost",
                    label="Task · ghost",
                    headers=("Title",),
                    rows=(),
                ),
            ),
        )
    )
    assert "Task · zzz" in leftover
    assert "Task · ghost" in leftover
    assert "Zzz" not in leftover
    assert "Ghost" not in leftover


def test_empty_fk_invents_no_suffix() -> None:
    assert clerk_related_tab_fk_label("") == ""
    assert clerk_related_tab_fk_label("   ") == ""
