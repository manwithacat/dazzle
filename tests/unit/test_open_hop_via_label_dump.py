"""Open-via hop phrases must not dump lowercase schema keys (oral #231)."""

from __future__ import annotations

from pathlib import Path

from dazzle.core.project import load_project
from dazzle.render.filters import clerk_entity_card_field_label
from dazzle.render.fragment.primitives import RowCapabilities
from dazzle.render.fragment.region._row_links import field_label_from_via
from dazzle.render.fragment.renderer._data_row import render_data_row
from dazzle.render.open_discovery import open_hop_label

SIMPLE = Path("examples/simple_task")
SIMPLE_DSL = SIMPLE / "dsl" / "app.dsl"


def test_simple_task_task_list_dual_open_is_live() -> None:
    block = SIMPLE_DSL.read_text()
    surface = block.split('surface task_list "Tasks":', 1)[1].split("surface ", 1)[0]
    assert "open: Task via id | User via assigned_to | User via created_by" in surface
    assert 'field assigned_to "Assigned To"' in surface
    task = block.split('entity Task "Task":', 1)[1].split("entity ", 1)[0]
    assert "assigned_to: ref User" in task


def test_clerk_open_hop_via_splits_pascal_and_catalog() -> None:
    spec = load_project(SIMPLE)
    task = next(e for e in spec.domain.entities if e.name == "Task")
    assert any(f.name == "assigned_to" for f in task.fields)
    assert clerk_entity_card_field_label("assigned_to") == "Assigned To"
    assert clerk_entity_card_field_label("created_by") == "Created By"
    assert open_hop_label("User", "assigned_to") == "Open User via Assigned To"
    assert open_hop_label("User", "created_by") == "Open User via Created By"
    assert field_label_from_via("assigned_to") == "Assigned To"
    assert open_hop_label("Task", "id") == "Open Task"
    assert open_hop_label("Company", "company") == "Open Company"


def test_clerk_open_hop_via_leftover_invents_no_relation() -> None:
    for junk in ("zzz", "ghost", "2abc"):
        assert clerk_entity_card_field_label(junk) == junk
        assert open_hop_label("User", junk) == f"Open User via {junk}"
        assert field_label_from_via(junk) == junk
    assert open_hop_label("User", "") == "Open User"
    assert field_label_from_via("") == ""


def test_data_row_hop_phrase_is_assigned_to_not_schema_dump() -> None:
    html = render_data_row(
        [{"key": "title", "type": "str"}],
        {"id": "t1", "title": "Ship dual-open", "assigned_to": "u-abc"},
        RowCapabilities(drill=True),
        detail_url_template="/app/task/{id}",
        detail_url_candidates=(
            "/app/task/{id}",
            "/app/user/{assigned_to}",
        ),
        detail_url_fallback_template="/app/task/{id}",
        entity_name="Task",
        api_endpoint="/api/tasks",
    )
    assert 'data-dz-open-via="assigned_to"' in html
    assert 'title="Open User via Assigned To"' in html
    assert 'data-dz-open-label="Open User via Assigned To"' in html
    assert "via assigned to" not in html
    leftover = render_data_row(
        [{"key": "title", "type": "str"}],
        {"id": "t1", "title": "Ship dual-open", "zzz": "u-abc"},
        RowCapabilities(drill=True),
        detail_url_template="/app/task/{id}",
        detail_url_candidates=(
            "/app/task/{id}",
            "/app/user/{zzz}",
        ),
        detail_url_fallback_template="/app/task/{id}",
        entity_name="Task",
        api_endpoint="/api/tasks",
    )
    assert 'data-dz-open-via="zzz"' in leftover
    assert "Open User via zzz" in leftover
    assert "Open User via Zzz" not in leftover
