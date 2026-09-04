"""Mutation toast title must not dump generic Created/Saved/Deleted (oral #239)."""

from __future__ import annotations

import json
from pathlib import Path

from dazzle.core.project import load_project
from dazzle.http.runtime.htmx import htmx_trigger_headers
from dazzle.render.breadcrumbs import (
    clerk_delete_label,
    clerk_entity_noun,
    clerk_form_submit_label,
    clerk_mutation_toast_title,
    clerk_related_create_noun,
    entity_path_labels_from_spec,
)

SIMPLE = Path("examples/simple_task")
FIELDTEST = Path("examples/fieldtest_hub")
SIMPLE_DSL = SIMPLE / "dsl" / "app.dsl"


def _toast(headers: dict[str, str]) -> dict:
    raw = headers.get("HX-Trigger") or headers.get("hx-trigger")
    assert raw, f"missing HX-Trigger in {headers!r}"
    return json.loads(raw)["showToast"]


def test_simple_task_task_create_is_live() -> None:
    block = SIMPLE_DSL.read_text()
    listing = block.split('surface task_list "Tasks":', 1)[1].split("surface ", 1)[0]
    create = block.split('surface task_create "Create Task":', 1)[1].split("surface ", 1)[0]
    assert "uses entity Task" in listing
    assert "mode: list" in listing
    assert "uses entity Task" in create
    assert "mode: create" in create
    spec = load_project(SIMPLE)
    task = next(e for e in spec.domain.entities if e.name == "Task")
    assert task.title == "Task"


def test_clerk_mutation_toast_title_uses_entity_noun() -> None:
    assert clerk_mutation_toast_title("Task") == "Created Task"
    assert clerk_mutation_toast_title("Task", action="updated") == "Saved Task"
    assert clerk_mutation_toast_title("Task", action="deleted") == "Deleted Task"
    assert clerk_form_submit_label("Task") == "Create Task"
    assert clerk_delete_label("Task") == "Delete Task"
    spec = load_project(FIELDTEST)
    issue = next(e for e in spec.domain.entities if e.name == "IssueReport")
    assert issue.title == "Issue Report"
    labels = entity_path_labels_from_spec(spec)
    assert clerk_entity_noun("IssueReport", labels) == "Issue Report"
    assert clerk_related_create_noun("IssueReport", labels) == "Issue Report"
    assert clerk_mutation_toast_title("IssueReport", labels) == "Created Issue Report"
    assert clerk_mutation_toast_title("IssueReport") == "Created Issue Report"
    assert (
        clerk_mutation_toast_title("IssueReport", labels, action="updated") == "Saved Issue Report"
    )
    assert clerk_mutation_toast_title("Task", authored="Queued") == "Queued"


def test_clerk_mutation_toast_title_leftover_invents_no_entity() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_mutation_toast_title(junk) == "Created"
        assert clerk_mutation_toast_title(junk, {"zzz": "Issue Report"}) == "Created"
        assert clerk_mutation_toast_title(junk, action="updated") == "Saved"
        assert clerk_mutation_toast_title(junk, action="deleted") == "Deleted"
    assert clerk_mutation_toast_title("") == "Created"
    assert clerk_mutation_toast_title("record") == "Created"
    assert clerk_mutation_toast_title("item") == "Created"


def test_toast_title_is_created_task_not_created() -> None:
    toast = _toast(htmx_trigger_headers("Task", "created"))
    assert toast["title"] == "Created Task"
    assert toast["message"] == "Task was created"
    leftover = _toast(htmx_trigger_headers("zzz", "created"))
    assert leftover["title"] == "Created"
    assert leftover["title"] != "Created zzz"
    assert leftover["message"] == "zzz was created"


def test_toast_title_issue_report_is_not_schema_dump() -> None:
    spec = load_project(FIELDTEST)
    labels = entity_path_labels_from_spec(spec)
    toast = _toast(htmx_trigger_headers("IssueReport", "created", entity_labels=labels))
    assert toast["title"] == "Created Issue Report"
    assert toast["message"] == "Issue Report was created"
    assert "Created IssueReport" not in toast["title"]
    assert "Created issuereport" not in toast["title"]
    split = _toast(htmx_trigger_headers("IssueReport", "updated"))
    assert split["title"] == "Saved Issue Report"
    deleted = _toast(htmx_trigger_headers("IssueReport", "deleted", entity_labels=labels))
    assert deleted["title"] == "Deleted Issue Report"
