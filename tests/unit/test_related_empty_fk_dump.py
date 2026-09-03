"""Related-tab empty must not dump FK-disambiguated tab labels (oral #217)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.runtime.renderers.related_queue_tab import (
    related_tab_from_ctx,
)
from dazzle.page.converters.template_compiler import compile_appspec_to_templates
from dazzle.render.breadcrumbs import clerk_related_empty_title
from dazzle.render.fragment.primitives.data import RelatedGroup
from dazzle.render.fragment.renderer import FragmentRenderer

SIMPLE = Path("examples/simple_task")
FIELDTEST = Path("examples/fieldtest_hub")


def _empty_tab(**overrides: object):
    base: dict = {
        "tab_id": "tab-task-assigned-to",
        "label": "Task · Assigned To",
        "entity_name": "Task",
        "entity_title": "Task",
        "create_url": "/app/task/create",
        "filter_field": "assigned_to",
        "columns": [{"key": "title", "label": "Title", "type": "text"}],
        "rows": [],
    }
    base.update(overrides)
    return related_tab_from_ctx(base, "u1", display="queue")


def test_clerk_related_empty_title_splits_pascal_and_catalog() -> None:
    spec = load_project(FIELDTEST)
    labels = {e.name: str(e.title or "") for e in spec.domain.entities if str(e.title or "")}
    assert clerk_related_empty_title("IssueNote", labels) == "No issue notes found."
    assert clerk_related_empty_title("IssueNote") == "No issue notes found."
    assert clerk_related_empty_title("Task") == "No tasks found."


def test_clerk_related_empty_title_leftover_invents_no_collection() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_related_empty_title(junk) == "No items found."


def test_related_empty_queue_is_entity_not_fk_tab() -> None:
    html = FragmentRenderer().render(
        RelatedGroup(
            group_id="work",
            label="Open work",
            display="queue",
            tabs=(_empty_tab(),),
        )
    )
    assert "No tasks found." in html
    assert "task · assigned to" not in html
    leftover = _empty_tab(
        tab_id="tab-zzz",
        label="zzz · Assigned To",
        entity_name="zzz",
        entity_title="",
        create_url="/app/zzz/create",
    )
    leftover_html = FragmentRenderer().render(
        RelatedGroup(
            group_id="work",
            label="Open work",
            display="queue",
            tabs=(leftover,),
        )
    )
    assert "No items found." in leftover_html
    assert "zzz · assigned to" not in leftover_html
    assert "No zzz" not in leftover_html


def test_related_empty_table_and_cards_use_entity_noun() -> None:
    tab = _empty_tab()
    table_html = FragmentRenderer().render(
        RelatedGroup(group_id="work", label="Open work", display="table", tabs=(tab,))
    )
    cards_html = FragmentRenderer().render(
        RelatedGroup(group_id="work", label="Open work", display="status_cards", tabs=(tab,))
    )
    for html in (table_html, cards_html):
        assert "No tasks found." in html
        assert "task · assigned to" not in html


def test_simple_task_user_detail_dual_fk_empty_is_live() -> None:
    appspec = load_project(SIMPLE)
    contexts = compile_appspec_to_templates(appspec)
    detail = contexts["/user/{id}"].detail
    assert detail is not None
    work = next(g for g in detail.related_groups if g.group_id == "group-work")
    tabs = [t for t in work.tabs if t.entity_name == "Task"]
    assert {t.label for t in tabs} == {"Task · Assigned To", "Task · Created By"}
    for tab in tabs:
        rendered = related_tab_from_ctx(
            {
                "label": tab.label,
                "entity_name": tab.entity_name,
                "entity_title": tab.entity_title,
                "create_url": tab.create_url,
                "filter_field": tab.filter_field,
                "columns": [{"key": "title", "label": "Title", "type": "text"}],
                "rows": [],
            },
            "u1",
            display="queue",
        )
        assert rendered.empty_message == "No tasks found."
        assert " · " not in rendered.empty_message
        html = FragmentRenderer().render(
            RelatedGroup(
                group_id="work",
                label="Open work",
                display="queue",
                tabs=(rendered,),
            )
        )
        assert "No tasks found." in html
        assert tab.label.lower() not in html
