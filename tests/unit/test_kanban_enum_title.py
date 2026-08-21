"""Kanban must not title tasks as snake_case enum tokens (oral #138)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from dazzle.core.project import load_project
from dazzle.http.converters.entity_converter import convert_entity
from dazzle.http.runtime.workspace_columns import build_entity_columns
from dazzle.http.runtime.workspace_region_render import (
    _entity_display_field,
    _entity_text_identity_key,
    _pick_display_key,
    _set_display_key,
)
from dazzle.render.fragment.region._dispatcher import WorkspaceRegionAdapter
from dazzle.render.fragment.region._shared import format_primary_display


class _FakeKanban:
    name = "open_work"
    title = "Open work"
    empty_message = "No open tasks"


def _task_runtime_columns() -> tuple[object, list[dict[str, object]]]:
    spec = load_project(Path("examples/fieldtest_hub"))
    ir_task = spec.get_entity("Task")
    assert ir_task is not None
    runtime = convert_entity(ir_task)
    cols = build_entity_columns(runtime, spec.enums)
    return runtime, cols


def test_task_identity_is_notes_not_type_enum() -> None:
    runtime, cols = _task_runtime_columns()
    assert {c["key"] for c in cols} == {"type", "status", "assigned_to", "created_by"}
    ctx = SimpleNamespace(entity_spec=runtime)
    assert _entity_display_field(ctx) == ""
    assert _pick_display_key(cols) == ""
    assert _entity_text_identity_key(ctx) == "notes"
    adapter_ctx: dict[str, object] = {}
    _set_display_key(adapter_ctx, SimpleNamespace(columns=cols), ctx)
    assert adapter_ctx["display_key"] == "notes"


def test_kanban_title_is_notes_not_debugging() -> None:
    adapter = WorkspaceRegionAdapter()
    notes = "Swap the probe battery after outdoor walk."
    ctx = {
        "items": [
            {
                "id": "t1000000-0000-4000-8000-000000000001",
                "type": "debugging",
                "status": "in_progress",
                "notes": notes,
            }
        ],
        "columns": [
            {"key": "type", "label": "Type", "type": "badge"},
            {"key": "status", "label": "Status", "type": "badge"},
            {"key": "assigned_to", "label": "Assigned To", "type": "ref"},
            {"key": "created_by", "label": "Created By", "type": "ref"},
        ],
        "kanban_columns": ["open", "in_progress"],
        "group_by": "status",
        "display_key": "notes",
        "entity_name": "Task",
    }
    surface = adapter._build_kanban(_FakeKanban(), ctx)  # type: ignore[arg-type]
    cards = [c for col in surface.body.body.columns for c in col.cards]  # type: ignore[union-attr]
    assert len(cards) == 1
    assert cards[0].title == notes
    assert "debugging" not in cards[0].title


def test_kanban_leftover_notes_title_stays_put() -> None:
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [
            {
                "id": "task-zzz",
                "type": "debugging",
                "status": "open",
                "notes": "zzz",
            }
        ],
        "columns": [
            {"key": "type", "label": "Type", "type": "badge"},
            {"key": "status", "label": "Status", "type": "badge"},
        ],
        "kanban_columns": ["open"],
        "group_by": "status",
        "display_key": "notes",
        "entity_name": "Task",
    }
    surface = adapter._build_kanban(_FakeKanban(), ctx)  # type: ignore[arg-type]
    assert surface.body.body.columns[0].cards[0].title == "zzz"  # type: ignore[union-attr]


def test_kanban_badge_title_humanizes_snake_case() -> None:
    """If display_key stays the enum, title-case — do not dump debugging."""
    assert (
        format_primary_display(
            "debugging",
            "type",
            [{"key": "type", "type": "badge"}],
            {"type": "debugging"},
        )
        == "Debugging"
    )
    assert (
        format_primary_display(
            "hardware_replacement",
            "type",
            [{"key": "type", "type": "badge"}],
            {},
        )
        == "Hardware Replacement"
    )
    adapter = WorkspaceRegionAdapter()
    ctx = {
        "items": [
            {
                "id": "task-enum",
                "type": "debugging",
                "status": "open",
            }
        ],
        "columns": [
            {"key": "type", "label": "Type", "type": "badge"},
            {"key": "status", "label": "Status", "type": "badge"},
        ],
        "kanban_columns": ["open"],
        "group_by": "status",
        "display_key": "type",
        "entity_name": "Task",
    }
    surface = adapter._build_kanban(_FakeKanban(), ctx)  # type: ignore[arg-type]
    assert surface.body.body.columns[0].cards[0].title == "Debugging"  # type: ignore[union-attr]
