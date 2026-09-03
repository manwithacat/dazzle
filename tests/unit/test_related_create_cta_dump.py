"""Related-tab create CTAs must not dump FK-disambiguated tab labels (oral #214)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.runtime.renderers.related_queue_tab import (
    related_create_affordance,
    related_tab_from_ctx,
)
from dazzle.page.converters.template_compiler import compile_appspec_to_templates
from dazzle.render.breadcrumbs import clerk_related_create_noun
from dazzle.render.fragment.primitives.data import RelatedGroup
from dazzle.render.fragment.renderer import FragmentRenderer

SIMPLE = Path("examples/simple_task")
FIELDTEST = Path("examples/fieldtest_hub")


def test_clerk_related_create_noun_splits_pascal_and_catalog() -> None:
    spec = load_project(FIELDTEST)
    labels = {e.name: str(e.title or "") for e in spec.domain.entities if str(e.title or "")}
    assert clerk_related_create_noun("IssueNote", labels) == "Issue Note"
    assert clerk_related_create_noun("IssueNote") == "Issue Note"
    assert clerk_related_create_noun("Task") == "Task"


def test_clerk_related_create_noun_leftover_invents_no_entity() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_related_create_noun(junk) == "item"


def test_related_create_affordance_is_entity_not_fk_tab() -> None:
    href, action, label = related_create_affordance(
        {
            "label": "Task · Assigned To",
            "entity_name": "Task",
            "entity_title": "Task",
            "create_url": "/app/task/create",
            "filter_field": "assigned_to",
        },
        "u1",
    )
    assert action == "Task.create"
    assert label == "Task"
    assert "assigned_to=u1" in href
    assert "Assigned To" not in label


def test_related_create_row_renders_new_task_not_fk_tab() -> None:
    tab = related_tab_from_ctx(
        {
            "tab_id": "tab-task-assigned-to",
            "label": "Task · Assigned To",
            "entity_name": "Task",
            "entity_title": "Task",
            "create_url": "/app/task/create",
            "filter_field": "assigned_to",
            "columns": [{"key": "title", "label": "Title", "type": "text"}],
            "rows": [],
        },
        "u1",
        display="queue",
    )
    html = FragmentRenderer().render(
        RelatedGroup(
            group_id="work",
            label="Open work",
            display="queue",
            tabs=(tab,),
        )
    )
    assert "+ New Task" in html
    assert "New Task · Assigned To" not in html
    leftover = related_tab_from_ctx(
        {
            "tab_id": "tab-zzz",
            "label": "zzz · Assigned To",
            "entity_name": "zzz",
            "create_url": "/app/zzz/create",
            "filter_field": "assigned_to",
            "columns": [],
            "rows": [],
        },
        "u1",
        display="queue",
    )
    leftover_html = FragmentRenderer().render(
        RelatedGroup(
            group_id="work",
            label="Open work",
            display="queue",
            tabs=(leftover,),
        )
    )
    assert "+ New item" in leftover_html
    assert "New zzz" not in leftover_html


def test_simple_task_user_detail_dual_fk_create_is_live() -> None:
    appspec = load_project(SIMPLE)
    contexts = compile_appspec_to_templates(appspec)
    detail = contexts["/user/{id}"].detail
    assert detail is not None
    work = next(g for g in detail.related_groups if g.group_id == "group-work")
    tabs = [t for t in work.tabs if t.entity_name == "Task"]
    assert {t.label for t in tabs} == {"Task · Assigned To", "Task · Created By"}
    assert {t.entity_title for t in tabs} == {"Task"}
    for tab in tabs:
        _href, _action, noun = related_create_affordance(
            {
                "label": tab.label,
                "entity_name": tab.entity_name,
                "entity_title": tab.entity_title,
                "create_url": tab.create_url,
                "filter_field": tab.filter_field,
            },
            "u1",
        )
        assert noun == "Task", tab.label
        assert " · " not in noun
